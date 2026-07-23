from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from database import db
from schemas import (
    LicenseCreateRequest,
    LicenseListRequest,
    LicenseDeleteRequest,
    LicenseActionRequest,
    ApiLicenseLoginRequest
)
from utils import send_discord_webhook, send_discord_error_webhook, log_err, parse_expiry
from routes.api import is_ip_blacklisted, save_auth_log
import time

router = APIRouter(tags=["Licenses"])

def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list):
            return res[0][0].value
        return res[0].value
    except Exception as e:
        log_err(f"Error getting count: {e}")
        return 0

@router.post("/licenses/create")
def create_license(data: LicenseCreateRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller_doc = next(seller_query, None)
    if not seller_doc:
        seller_doc = db.collection('sellers').document(data.ownerid).get()
        if not seller_doc.exists:
            raise HTTPException(status_code=404, detail="Seller error: not found")

    dupes = db.collection('licenses').where('appid', '==', data.appid).where('license_key', '==', data.license_key).limit(1).stream()
    for _ in dupes:
        raise HTTPException(status_code=400, detail="License key already exists")

    if data.expire_str:
        try:
            expires = parse_expiry(data.expire_str)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif data.days == 0:
        expires = datetime(9999, 12, 31, tzinfo=timezone.utc)
    else:
        expires = datetime.now(timezone.utc) + timedelta(days=data.days)

    db.collection('licenses').add({
        'appid': data.appid,
        'license_key': data.license_key,
        'expires_at': expires.isoformat(),
        'hwid': None,
        'hwid_locked': False,
        'created_by': 'owner',
        'created_at': datetime.now(timezone.utc).isoformat()
    })
    return {"status": "success"}

@router.post("/licenses/list")
def list_licenses(data: LicenseListRequest):
    licenses = db.collection('licenses').where('appid', '==', data.appid).stream()
    l_list = [{"id": d.id, **d.to_dict()} for d in licenses]
    return {"status": "success", "licenses": l_list}

@router.post("/licenses/delete")
def delete_license(data: LicenseDeleteRequest):
    db.collection('licenses').document(data.license_id).delete()
    return {"status": "success"}

@router.post("/licenses/action")
def license_action(data: LicenseActionRequest):
    doc_ref = db.collection('licenses').document(data.license_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="License not found")
    updates = {}
    l_data = doc.to_dict()
    if data.action == "reset_hwid":
        updates['hwid'] = None
    elif data.action == "toggle_lock":
        updates['hwid_locked'] = data.lock_state
    elif data.action == "set_expiry":
        if data.expire_str:
            try:
                updates['expires_at'] = parse_expiry(data.expire_str).isoformat()
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
    elif data.action == "pause" or (data.action == "toggle_pause" and not l_data.get('is_paused', False)):
        if l_data.get('is_paused', False):
            raise HTTPException(status_code=400, detail="License is already paused")
        now = datetime.now(timezone.utc)
        exp_str = l_data.get('expires_at')
        rem_sec = -1
        if exp_str:
            exp_date = parse_expiry(exp_str)
            if exp_date.year != 9999:
                rem_sec = int((exp_date - now).total_seconds())
                if rem_sec <= 0:
                    raise HTTPException(status_code=400, detail="Cannot pause an expired license")
        updates['is_paused'] = True
        updates['paused_at'] = now.isoformat()
        updates['remaining_seconds'] = rem_sec
    elif data.action == "resume" or (data.action == "toggle_pause" and l_data.get('is_paused', False)):
        if not l_data.get('is_paused', False):
            raise HTTPException(status_code=400, detail="License is not paused")
        now = datetime.now(timezone.utc)
        rem_sec = l_data.get('remaining_seconds', -1)
        updates['is_paused'] = False
        updates['paused_at'] = None
        updates['remaining_seconds'] = None
        if rem_sec and rem_sec > 0:
            new_exp = now + timedelta(seconds=rem_sec)
            updates['expires_at'] = new_exp.isoformat()
    if updates:
        doc_ref.update(updates)
        return {"status": "success"}
    return {"status": "no_change"}

def update_license_last_login(lic_doc_ref, hwid, client_ip):
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        lic_doc_ref.update({'hwid': hwid, 'last_login': now_iso, 'last_ip': client_ip})
    except Exception as e:
        log_err(f"Update license last login error: {e}")

@router.post("/api/1.0/license_login")
async def license_login(data: ApiLicenseLoginRequest, request: Request, bg_tasks: BackgroundTasks):
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).where('app_secret', '==', data.app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    if not app_doc_ref:
        return {"success": False, "message": "Invalid application details."}
    app_data = app_doc_ref.to_dict()
    wh_config = app_data.get('webhook_config', {})
    x_forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.client.host
    display_key = f"License: {data.license_key[:8]}..."

    def queue_error(reason):
        bg_tasks.add_task(save_auth_log, data.ownerid, app_data['appid'], app_data['name'], display_key, "license", client_ip, data.hwid, "failed", reason)
        bg_tasks.add_task(
            send_discord_error_webhook,
            wh_config.get('url'),
            {'username': display_key, 'hwid': data.hwid},
            wh_config,
            app_data['name'],
            client_ip,
            reason
        )

    if is_ip_blacklisted(data.ownerid, client_ip):
        queue_error("IP address is blacklisted.")
        return {"success": False, "message": "IP address is blacklisted."}

    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).get()
    if not seller_query:
        queue_error("Invalid developer account.")
        return {"success": False, "message": "Invalid developer account."}
    seller_doc = seller_query[0]
    seller_data = seller_doc.to_dict()
    group = seller_data.get('seller_group', 0)
    plan_expires_at = seller_data.get('plan_expires_at')
    if plan_expires_at:
        try:
            expiry_date = datetime.fromisoformat(plan_expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expiry_date:
                seller_doc.reference.update({'seller_group': 0, 'plan_expires_at': None})
                group = 0
        except Exception:
            pass
    if group == 0:
        lic_agg = db.collection('licenses').where('appid', '==', app_data['appid']).count()
        lic_count = get_secure_count(lic_agg)
        if lic_count > 12:
            queue_error("Developer limit exceeded. Authentication suspended.")
            return {"success": False, "message": "Developer limit exceeded. Authentication suspended."}
    elif group == 1:
        lic_agg = db.collection('licenses').where('appid', '==', app_data['appid']).count()
        lic_count = get_secure_count(lic_agg)
        if lic_count > 24:
            queue_error("Developer limit exceeded. Authentication suspended.")
            return {"success": False, "message": "Developer limit exceeded. Authentication suspended."}

    licenses = db.collection('licenses').where('license_key', '==', data.license_key).where('appid', '==', app_data['appid']).limit(1).stream()
    lic_doc = next(licenses, None)
    if lic_doc is None:
        queue_error("Invalid license key.")
        return {"success": False, "message": "Invalid license key."}
    l_data = lic_doc.to_dict()

    if l_data.get('is_paused', False):
        queue_error("License is paused.")
        return {"success": False, "message": "License key is currently paused."}

    try:
        expiry_date = parse_expiry(l_data['expires_at'])
        if datetime.now(timezone.utc) > expiry_date:
            queue_error("License expired.")
            return {"success": False, "message": "License expired."}
    except Exception as e:
        log_err(f"License expiry check error: {e}")
        queue_error("Error verifying license status.")
        return {"success": False, "message": "Error verifying license status."}

    is_hwid_locked = l_data.get('hwid_locked', False)
    if is_hwid_locked:
        if l_data.get('hwid') is None:
            l_data['hwid'] = data.hwid
        elif l_data['hwid'] != data.hwid:
            queue_error("HWID mismatch.")
            return {"success": False, "message": "HWID mismatch."}
    else:
        l_data['hwid'] = data.hwid

    bg_tasks.add_task(update_license_last_login, lic_doc.reference, l_data['hwid'], client_ip)
    bg_tasks.add_task(save_auth_log, data.ownerid, app_data['appid'], app_data['name'], display_key, "license", client_ip, l_data['hwid'], "success", "")

    if wh_config.get('enabled') and wh_config.get('url'):
        u_data_mapped = {
            'username': display_key,
            'expires_at': l_data['expires_at'],
            'hwid': l_data['hwid']
        }
        bg_tasks.add_task(send_discord_webhook, wh_config['url'], u_data_mapped, wh_config, app_data['name'], client_ip)

    return {"success": True, "message": "Login successful.", "info": {"expires": l_data['expires_at']}}

