from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Request
from database import db
from schemas import ApiLoginRequest
from utils import send_discord_webhook, send_discord_error_webhook, log_err, parse_expiry
import time

router = APIRouter(tags=["API"])

_blacklist_cache = {}
_blacklist_ts = {}
_CACHE_TTL = 60

def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list):
            return res[0][0].value
        return res[0].value
    except Exception as e:
        log_err(f"Error getting count: {e}")
        return 0

def is_ip_blacklisted(ownerid, ip):
    now = time.time()
    if ownerid not in _blacklist_ts or (now - _blacklist_ts[ownerid]) > _CACHE_TTL:
        try:
            docs = db.collection('blacklisted_ips').where('ownerid', '==', ownerid).stream()
            _blacklist_cache[ownerid] = {d.to_dict().get('ip') for d in docs}
            _blacklist_ts[ownerid] = now
        except Exception as e:
            log_err(f"Blacklist cache error: {e}")
            return False
    return ip in _blacklist_cache.get(ownerid, set())

def invalidate_blacklist_cache(ownerid):
    _blacklist_cache.pop(ownerid, None)
    _blacklist_ts.pop(ownerid, None)


def save_auth_log(ownerid, appid, app_name, username, auth_type, ip, hwid, status, reason=""):
    try:
        db.collection('logs').add({
            'ownerid': ownerid,
            'appid': appid,
            'app_name': app_name,
            'username': username,
            'auth_type': auth_type,
            'ip': ip,
            'hwid': hwid,
            'status': status,
            'reason': reason,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        log_err(f"Log save error: {e}")

def update_user_last_login(user_doc_ref, hwid, client_ip):
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        user_doc_ref.update({'hwid': hwid, 'last_login': now_iso, 'last_ip': client_ip})
    except Exception as e:
        log_err(f"Update last login error: {e}")

@router.post("/api/1.0/user_login")
async def user_login(data: ApiLoginRequest, request: Request, bg_tasks: BackgroundTasks):
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).where('app_secret', '==', data.app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    if not app_doc_ref:
        return {"success": False, "message": "Invalid application details."}
    app_data = app_doc_ref.to_dict()
    wh_config = app_data.get('webhook_config', {})
    x_forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.client.host

    def queue_error(reason):
        bg_tasks.add_task(save_auth_log, data.ownerid, app_data['appid'], app_data['name'], data.username, "user", client_ip, data.hwid, "failed", reason)
        bg_tasks.add_task(
            send_discord_error_webhook,
            wh_config.get('url'),
            {'username': data.username, 'hwid': data.hwid},
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
        user_agg = db.collection('users').where('appid', '==', app_data['appid']).count()
        user_count = get_secure_count(user_agg)
        if user_count > 12:
            queue_error("Developer limit exceeded. Authentication suspended.")
            return {"success": False, "message": "Developer limit exceeded. Authentication suspended."}
    elif group == 1:
        user_agg = db.collection('users').where('appid', '==', app_data['appid']).count()
        user_count = get_secure_count(user_agg)
        if user_count > 24:
            queue_error("Developer limit exceeded. Authentication suspended.")
            return {"success": False, "message": "Developer limit exceeded. Authentication suspended."}

    users = db.collection('users').where('username', '==', data.username).where('appid', '==', app_data['appid']).limit(1).stream()
    user_doc = next(users, None)
    if user_doc is None:
        queue_error("Invalid credentials.")
        return {"success": False, "message": "Invalid credentials."}

    u_data = user_doc.to_dict()
    if u_data['password'] != data.password:
        queue_error("Invalid credentials.")
        return {"success": False, "message": "Invalid credentials."}

    if u_data.get('is_paused', False):
        queue_error("Account is paused.")
        return {"success": False, "message": "Account is currently paused."}

    try:
        expiry_date = parse_expiry(u_data['expires_at'])
        if datetime.now(timezone.utc) > expiry_date:
            queue_error("Key expired.")
            return {"success": False, "message": "Key expired."}
    except Exception as e:
        log_err(f"Expiry check error: {e}")
        queue_error("Error verifying subscription status.")
        return {"success": False, "message": "Error verifying subscription status."}

    is_hwid_locked = u_data.get('hwid_locked', True)
    if is_hwid_locked:
        if u_data.get('hwid') is None:
            u_data['hwid'] = data.hwid
        elif u_data['hwid'] != data.hwid:
            queue_error("HWID mismatch.")
            return {"success": False, "message": "HWID mismatch."}
    else:
        u_data['hwid'] = data.hwid

    bg_tasks.add_task(update_user_last_login, user_doc.reference, u_data['hwid'], client_ip)
    bg_tasks.add_task(save_auth_log, data.ownerid, app_data['appid'], app_data['name'], data.username, "user", client_ip, u_data['hwid'], "success", "")

    if wh_config.get('enabled') and wh_config.get('url'):
        bg_tasks.add_task(send_discord_webhook, wh_config['url'], u_data, wh_config, app_data['name'], client_ip)

    return {"success": True, "message": "Login successful.", "info": {"expires": u_data['expires_at']}}
