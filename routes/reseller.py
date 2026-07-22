import uuid
import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
from google.cloud.firestore_v1.base_query import FieldFilter
from database import db
from schemas import (
    ResellerInviteRequest,
    ResellerAcceptRequest,
    ResellerDeclineRequest,
    ResellerListRequest,
    ResellerDeleteRequest,
    ResellerUpdateLimitsRequest,
    ResellerLicenseCreateRequest,
    ResellerLicenseListRequest,
    ResellerLicenseActionRequest,
    ResellerCancelInviteRequest,
    ResellerUserCreateRequest,
    ResellerUserListRequest,
    ResellerUserActionRequest
)
from utils import parse_expiry

router = APIRouter(tags=["Resellers"])

def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list):
            return res[0][0].value
        return res[0].value
    except Exception:
        return 0

def get_reseller_counts(db, appid: str, email: str) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    email_lower = email.lower()

    lic_ref = db.collection('licenses').where(filter=FieldFilter('appid', '==', appid)).where(filter=FieldFilter('created_by', '==', email_lower))
    today_lic_agg = lic_ref.where(filter=FieldFilter('created_at', '>=', today_start)).count()
    month_lic_agg = lic_ref.where(filter=FieldFilter('created_at', '>=', month_start)).count()

    user_ref = db.collection('users').where(filter=FieldFilter('appid', '==', appid)).where(filter=FieldFilter('created_by', '==', email_lower))
    today_users_agg = user_ref.where(filter=FieldFilter('created_at', '>=', today_start)).count()
    month_users_agg = user_ref.where(filter=FieldFilter('created_at', '>=', month_start)).count()

    today_lic = get_secure_count(today_lic_agg)
    month_lic = get_secure_count(month_lic_agg)
    today_users = get_secure_count(today_users_agg)
    month_users = get_secure_count(month_users_agg)

    return {
        "today_licenses": today_lic,
        "month_licenses": month_lic,
        "today_users": today_users,
        "month_users": month_users,
        "today_total": today_lic + today_users,
        "month_total": month_lic + month_users
    }

@router.post("/reseller/invite")
def invite_reseller(data: ResellerInviteRequest):
    seller_query = db.collection('sellers').where(filter=FieldFilter('ownerid', '==', data.ownerid)).limit(1).get()
    if not seller_query:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    seller_group = seller_query[0].to_dict().get('seller_group', 0)
    if seller_group != 2:
        raise HTTPException(status_code=403, detail="Only Gold Plan members can invite resellers. Please upgrade your developer plan.")

    apps = db.collection('applications').where(filter=FieldFilter('ownerid', '==', data.ownerid)).where(filter=FieldFilter('appid', '==', data.appid)).limit(1).get()
    if not apps:
        raise HTTPException(status_code=404, detail="Application not found or not owned by you")
    app_name = apps[0].to_dict().get('name')

    resellers = db.collection('resellers').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', data.appid)).limit(1).get()
    if resellers:
        raise HTTPException(status_code=400, detail="Reseller already active for this application")

    pending = db.collection('reseller_invitations').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', data.appid)).where(filter=FieldFilter('status', '==', 'pending')).limit(1).get()
    if pending:
        raise HTTPException(status_code=400, detail="There is already a pending invitation for this email address")

    invite_id = str(uuid.uuid4())
    db.collection('reseller_invitations').document(invite_id).set({
        'id': invite_id,
        'email': data.email.lower(),
        'appid': data.appid,
        'app_name': app_name,
        'ownerid': data.ownerid,
        'daily_limit': data.daily_limit,
        'monthly_limit': data.monthly_limit,
        'can_create_users': data.can_create_users,
        'can_delete_users': data.can_delete_users,
        'can_create_license': data.can_create_license,
        'can_delete_license': data.can_delete_license,
        'can_reset_hwid': data.can_reset_hwid,
        'can_update_expiry': data.can_update_expiry,
        'status': 'pending',
        'created_at': datetime.now(timezone.utc).isoformat()
    })

    frontend_origin = os.environ.get("FRONTEND_URL")
    if not frontend_origin:
        frontend_origin = data.frontend_origin.rstrip('/') if data.frontend_origin else "https://lynxauth.qzz.io"
        if "localhost" in frontend_origin or "127.0.0.1" in frontend_origin:
            frontend_origin = "https://lynxauth.qzz.io"
    else:
        frontend_origin = frontend_origin.rstrip('/')
        
    invite_url = f"{frontend_origin}/panel.html?invite_id={invite_id}"
    
    return {"status": "success", "invite_id": invite_id, "invite_url": invite_url}

@router.post("/reseller/accept")
def accept_reseller(data: ResellerAcceptRequest):
    invite_ref = db.collection('reseller_invitations').document(data.invite_id)
    invite = invite_ref.get()
    if not invite.exists:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    invite_data = invite.to_dict()
    if invite_data.get('status') != 'pending':
        raise HTTPException(status_code=400, detail="Invitation already processed")
    
    if invite_data.get('email') != data.email.lower():
        raise HTTPException(status_code=400, detail="This invitation belongs to a different email address")

    invite_ref.update({'status': 'accepted'})

    resellers = db.collection('resellers').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', invite_data['appid'])).limit(1).get()
    if not resellers:
        db.collection('resellers').add({
            'email': data.email.lower(),
            'appid': invite_data['appid'],
            'ownerid': invite_data['ownerid'],
            'daily_limit': invite_data['daily_limit'],
            'monthly_limit': invite_data['monthly_limit'],
            'can_create_users': invite_data.get('can_create_users', True),
            'can_delete_users': invite_data.get('can_delete_users', True),
            'can_create_license': invite_data.get('can_create_license', True),
            'can_delete_license': invite_data.get('can_delete_license', True),
            'can_reset_hwid': invite_data.get('can_reset_hwid', True),
            'can_update_expiry': invite_data.get('can_update_expiry', True),
            'created_at': datetime.now(timezone.utc).isoformat()
        })

    return {"status": "success"}

@router.post("/reseller/decline")
def decline_reseller(data: ResellerDeclineRequest):
    invite_ref = db.collection('reseller_invitations').document(data.invite_id)
    invite = invite_ref.get()
    if not invite.exists:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    invite_data = invite.to_dict()
    if invite_data.get('email') != data.email.lower():
        raise HTTPException(status_code=400, detail="Unauthorized")

    invite_ref.update({'status': 'declined'})
    return {"status": "success"}

@router.post("/reseller/list_invites")
def list_invites(data: ResellerListRequest):
    invites = db.collection('reseller_invitations').where(filter=FieldFilter('ownerid', '==', data.ownerid)).stream()
    return {"status": "success", "invitations": [i.to_dict() for i in invites]}

@router.post("/reseller/list")
def list_resellers(data: ResellerListRequest):
    query = db.collection('resellers').where(filter=FieldFilter('ownerid', '==', data.ownerid))
    if data.appid:
        query = query.where(filter=FieldFilter('appid', '==', data.appid))
    
    resellers = query.stream()
    res_list = []
    
    for r in resellers:
        rd = r.to_dict()
        app_doc = db.collection('applications').where(filter=FieldFilter('appid', '==', rd['appid'])).limit(1).get()
        app_name = app_doc[0].to_dict().get('name') if app_doc else "Unknown App"
        
        counts = get_reseller_counts(db, rd['appid'], rd['email'])
                    
        res_list.append({
            "id": r.id,
            "email": rd["email"],
            "appid": rd["appid"],
            "app_name": app_name,
            "daily_limit": rd["daily_limit"],
            "monthly_limit": rd["monthly_limit"],
            "can_create_users": rd.get("can_create_users", True),
            "can_delete_users": rd.get("can_delete_users", True),
            "can_create_license": rd.get("can_create_license", True),
            "can_delete_license": rd.get("can_delete_license", True),
            "can_reset_hwid": rd.get("can_reset_hwid", True),
            "can_update_expiry": rd.get("can_update_expiry", True),
            "keys_created_today": counts["today_total"],
            "keys_created_this_month": counts["month_total"],
            "created_at": rd.get("created_at")
        })
        
    return {"status": "success", "resellers": res_list}

@router.post("/reseller/delete")
def delete_reseller(data: ResellerDeleteRequest):
    res_ref = db.collection('resellers').document(data.reseller_id)
    res = res_ref.get()
    if not res.exists:
        raise HTTPException(status_code=404, detail="Reseller not found")
    
    rd = res.to_dict()
    if rd.get('ownerid') != data.ownerid:
        raise HTTPException(status_code=403, detail="Unauthorized")

    res_ref.delete()
    return {"status": "success"}

@router.post("/reseller/update_limits")
def update_limits(data: ResellerUpdateLimitsRequest):
    seller_query = db.collection('sellers').where(filter=FieldFilter('ownerid', '==', data.ownerid)).limit(1).get()
    if not seller_query:
        raise HTTPException(status_code=404, detail="Seller profile not found")
    seller_group = seller_query[0].to_dict().get('seller_group', 0)
    if seller_group != 2:
        raise HTTPException(status_code=403, detail="Only Gold Plan members can manage resellers. Please upgrade your developer plan.")

    res_ref = db.collection('resellers').document(data.reseller_id)
    res = res_ref.get()
    if not res.exists:
        raise HTTPException(status_code=404, detail="Reseller not found")
    
    rd = res.to_dict()
    if rd.get('ownerid') != data.ownerid:
        raise HTTPException(status_code=403, detail="Unauthorized")

    res_ref.update({
        'daily_limit': data.daily_limit,
        'monthly_limit': data.monthly_limit,
        'can_create_users': data.can_create_users,
        'can_delete_users': data.can_delete_users,
        'can_create_license': data.can_create_license,
        'can_delete_license': data.can_delete_license,
        'can_reset_hwid': data.can_reset_hwid,
        'can_update_expiry': data.can_update_expiry
    })
    return {"status": "success"}

@router.post("/reseller/licenses/create")
def reseller_create_license(data: ResellerLicenseCreateRequest):
    resellers = db.collection('resellers').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', data.appid)).limit(1).get()
    if not resellers:
        raise HTTPException(status_code=403, detail="Unauthorized reseller access")
    
    res_data = resellers[0].to_dict()
    if not res_data.get('can_create_license', True):
        raise HTTPException(status_code=403, detail="You do not have permission to generate license keys")
    
    counts = get_reseller_counts(db, data.appid, data.email.lower())

    if res_data['daily_limit'] > 0 and counts["today_total"] >= res_data['daily_limit']:
        raise HTTPException(status_code=400, detail="Daily key creation limit reached")
    if res_data['monthly_limit'] > 0 and counts["month_total"] >= res_data['monthly_limit']:
        raise HTTPException(status_code=400, detail="Monthly key creation limit reached")

    dupes = db.collection('licenses').where(filter=FieldFilter('appid', '==', data.appid)).where(filter=FieldFilter('license_key', '==', data.license_key)).limit(1).stream()
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
        'created_by': data.email.lower(),
        'created_at': datetime.now(timezone.utc).isoformat()
    })

    return {"status": "success"}

@router.post("/reseller/licenses/list")
def reseller_list_licenses(data: ResellerLicenseListRequest):
    resellers = db.collection('resellers').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', data.appid)).limit(1).get()
    if not resellers:
        raise HTTPException(status_code=403, detail="Unauthorized reseller access")
    
    licenses = db.collection('licenses').where(filter=FieldFilter('appid', '==', data.appid)).where(filter=FieldFilter('created_by', '==', data.email.lower())).stream()
    l_list = [{"id": d.id, **d.to_dict()} for d in licenses]
    return {"status": "success", "licenses": l_list}

@router.post("/reseller/licenses/action")
def reseller_license_action(data: ResellerLicenseActionRequest):
    doc_ref = db.collection('licenses').document(data.license_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="License not found")
    
    lic_data = doc.to_dict()
    if lic_data.get('created_by') != data.email.lower():
        raise HTTPException(status_code=403, detail="Unauthorized to manage this license")

    resellers = db.collection('resellers').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', lic_data['appid'])).limit(1).get()
    if not resellers:
        raise HTTPException(status_code=403, detail="Unauthorized reseller access")
    res_data = resellers[0].to_dict()

    if data.action == "delete" and not res_data.get('can_delete_license', True):
        raise HTTPException(status_code=403, detail="You do not have permission to delete license keys")
    if data.action == "reset_hwid" and not res_data.get('can_reset_hwid', True):
        raise HTTPException(status_code=403, detail="You do not have permission to reset HWID")
    if data.action == "set_expiry" and not res_data.get('can_update_expiry', True):
        raise HTTPException(status_code=403, detail="You do not have permission to update expiry duration")

    updates = {}
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
    elif data.action == "pause" or (data.action == "toggle_pause" and not lic_data.get('is_paused', False)):
        if lic_data.get('is_paused', False):
            raise HTTPException(status_code=400, detail="License is already paused")
        now = datetime.now(timezone.utc)
        exp_str = lic_data.get('expires_at')
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
    elif data.action == "resume" or (data.action == "toggle_pause" and lic_data.get('is_paused', False)):
        if not lic_data.get('is_paused', False):
            raise HTTPException(status_code=400, detail="License is not paused")
        now = datetime.now(timezone.utc)
        rem_sec = lic_data.get('remaining_seconds', -1)
        updates['is_paused'] = False
        updates['paused_at'] = None
        updates['remaining_seconds'] = None
        if rem_sec and rem_sec > 0:
            new_exp = now + timedelta(seconds=rem_sec)
            updates['expires_at'] = new_exp.isoformat()
    elif data.action == "delete":
        doc_ref.delete()
        return {"status": "success"}

    if updates:
        doc_ref.update(updates)
        return {"status": "success"}
    return {"status": "no_change"}

@router.get("/reseller/invite_details/{invite_id}")
def get_invite_details(invite_id: str):
    invite_ref = db.collection('reseller_invitations').document(invite_id)
    invite = invite_ref.get()
    if not invite.exists:
        raise HTTPException(status_code=404, detail="Invitation not found")
    invite_data = invite.to_dict()
    
    owner_email = "Unknown Seller"
    seller_query = db.collection('sellers').where(filter=FieldFilter('ownerid', '==', invite_data.get('ownerid'))).limit(1).get()
    if seller_query:
        owner_email = seller_query[0].to_dict().get('email', 'Unknown')
        
    return {
        "status": "success",
        "email": invite_data.get("email"),
        "app_name": invite_data.get("app_name"),
        "owner_email": owner_email,
        "daily_limit": invite_data.get("daily_limit"),
        "monthly_limit": invite_data.get("monthly_limit"),
        "status": invite_data.get("status")
    }

@router.post("/reseller/invite/cancel")
def cancel_invite(data: ResellerCancelInviteRequest):
    invite_ref = db.collection('reseller_invitations').document(data.invite_id)
    invite = invite_ref.get()
    if not invite.exists:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    invite_data = invite.to_dict()
    if invite_data.get('ownerid') != data.ownerid:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    invite_ref.delete()
    return {"status": "success"}

@router.post("/reseller/users/create")
def reseller_create_user(data: ResellerUserCreateRequest):
    resellers = db.collection('resellers').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', data.appid)).limit(1).get()
    if not resellers:
        raise HTTPException(status_code=403, detail="Unauthorized reseller access")
    
    res_data = resellers[0].to_dict()
    if not res_data.get('can_create_users', True):
        raise HTTPException(status_code=403, detail="You do not have permission to create users directly")

    counts = get_reseller_counts(db, data.appid, data.email.lower())

    if res_data['daily_limit'] > 0 and counts["today_total"] >= res_data['daily_limit']:
        raise HTTPException(status_code=400, detail="Daily creation limit reached")
    if res_data['monthly_limit'] > 0 and counts["month_total"] >= res_data['monthly_limit']:
        raise HTTPException(status_code=400, detail="Monthly creation limit reached")

    dupes = db.collection('users').where(filter=FieldFilter('appid', '==', data.appid)).where(filter=FieldFilter('username', '==', data.username)).limit(1).stream()
    for _ in dupes:
        raise HTTPException(status_code=400, detail="Username already exists")

    if data.expire_str:
        try:
            expires = parse_expiry(data.expire_str)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif data.days == 0:
        expires = datetime(9999, 12, 31, tzinfo=timezone.utc)
    else:
        expires = datetime.now(timezone.utc) + timedelta(days=data.days)

    db.collection('users').add({
        'appid': data.appid,
        'username': data.username,
        'password': data.password,
        'expires_at': expires.isoformat(),
        'hwid': None,
        'hwid_locked': False,
        'created_by': data.email.lower(),
        'created_at': datetime.now(timezone.utc).isoformat()
    })

    return {"status": "success"}

@router.post("/reseller/users/list")
def reseller_list_users(data: ResellerUserListRequest):
    resellers = db.collection('resellers').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', data.appid)).limit(1).get()
    if not resellers:
        raise HTTPException(status_code=403, detail="Unauthorized reseller access")
    
    users = db.collection('users').where(filter=FieldFilter('appid', '==', data.appid)).where(filter=FieldFilter('created_by', '==', data.email.lower())).stream()
    u_list = [{"id": d.id, **d.to_dict()} for d in users]
    return {"status": "success", "users": u_list}

@router.post("/reseller/users/action")
def reseller_user_action(data: ResellerUserActionRequest):
    doc_ref = db.collection('users').document(data.user_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = doc.to_dict()
    if user_data.get('created_by') != data.email.lower():
        raise HTTPException(status_code=403, detail="Unauthorized to manage this user")

    resellers = db.collection('resellers').where(filter=FieldFilter('email', '==', data.email.lower())).where(filter=FieldFilter('appid', '==', user_data['appid'])).limit(1).get()
    if not resellers:
        raise HTTPException(status_code=403, detail="Unauthorized reseller access")
    res_data = resellers[0].to_dict()

    if data.action == "delete" and not res_data.get('can_delete_users', True):
        raise HTTPException(status_code=403, detail="You do not have permission to delete users")
    if data.action == "reset_hwid" and not res_data.get('can_reset_hwid', True):
        raise HTTPException(status_code=403, detail="You do not have permission to reset HWID")
    if data.action == "set_expiry" and not res_data.get('can_update_expiry', True):
        raise HTTPException(status_code=403, detail="You do not have permission to update user expiry duration")

    updates = {}
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
    elif data.action == "pause" or (data.action == "toggle_pause" and not user_data.get('is_paused', False)):
        if user_data.get('is_paused', False):
            raise HTTPException(status_code=400, detail="User is already paused")
        now = datetime.now(timezone.utc)
        exp_str = user_data.get('expires_at')
        rem_sec = -1
        if exp_str:
            exp_date = parse_expiry(exp_str)
            if exp_date.year != 9999:
                rem_sec = int((exp_date - now).total_seconds())
                if rem_sec <= 0:
                    raise HTTPException(status_code=400, detail="Cannot pause an expired user")
        updates['is_paused'] = True
        updates['paused_at'] = now.isoformat()
        updates['remaining_seconds'] = rem_sec
    elif data.action == "resume" or (data.action == "toggle_pause" and user_data.get('is_paused', False)):
        if not user_data.get('is_paused', False):
            raise HTTPException(status_code=400, detail="User is not paused")
        now = datetime.now(timezone.utc)
        rem_sec = user_data.get('remaining_seconds', -1)
        updates['is_paused'] = False
        updates['paused_at'] = None
        updates['remaining_seconds'] = None
        if rem_sec and rem_sec > 0:
            new_exp = now + timedelta(seconds=rem_sec)
            updates['expires_at'] = new_exp.isoformat()
    elif data.action == "delete":
        doc_ref.delete()
        return {"status": "success"}

    if updates:
        doc_ref.update(updates)
        return {"status": "success"}
    return {"status": "no_change"}
