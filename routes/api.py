from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Request
from database import db
from schemas import ApiLoginRequest
from utils import send_discord_webhook, log_err

router = APIRouter(tags=["API"])

@router.post("/api/1.0/user_login")
async def user_login(data: ApiLoginRequest, request: Request, bg_tasks: BackgroundTasks):
    # 1. Fetch App
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).where('app_secret', '==', data.app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    if not app_doc_ref: 
        return {"success": False, "message": "Invalid application details."}
    app_data = app_doc_ref.to_dict()

    # 2. Fetch User
    users = db.collection('users').where('username', '==', data.username).where('appid', '==', app_data['appid']).limit(1).stream()
    user_doc = next(users, None)
    if user_doc is None: 
        return {"success": False, "message": "Invalid credentials."}
    
    u_data = user_doc.to_dict()
    if u_data['password'] != data.password: 
        return {"success": False, "message": "Invalid credentials."}

    # 3. Expiry Check
    try:
        expiry_date = datetime.fromisoformat(u_data['expires_at'])
        if datetime.utcnow() > expiry_date:
            return {"success": False, "message": "Your subscription has expired."}
    except Exception as e:
        log_err(f"Expiry check error: {e}")
        return {"success": False, "message": "Error verifying subscription status."}
    
    # 4. HWID Logic
    is_hwid_locked = u_data.get('hwid_locked', True)

    if is_hwid_locked:
        if u_data.get('hwid') is None:
            user_doc.reference.update({'hwid': data.hwid})
            u_data['hwid'] = data.hwid 
        elif u_data['hwid'] != data.hwid:
            return {"success": False, "message": "HWID mismatch."}
    else:
        user_doc.reference.update({'hwid': data.hwid})
        u_data['hwid'] = data.hwid
    
    # 5. Discord Webhook Notification
    wh_config = app_data.get('webhook_config', {})
    if wh_config.get('enabled') and wh_config.get('url'):
        x_forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.client.host
        bg_tasks.add_task(send_discord_webhook, wh_config['url'], u_data, wh_config, app_data['name'], client_ip)

    return {"success": True, "message": "Login successful.", "info": {"expires": u_data['expires_at']}}


@router.get("/api/1.0/reset_hwid")
async def reset_hwid(username: str, ownerid: str, app_secret: str):
    # 1. Fetch App
    apps = db.collection('applications').where('ownerid', '==', ownerid).where('app_secret', '==', app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    if not app_doc_ref:
        return {"status": "error", "success": False, "message": "Invalid application details."}
    app_data = app_doc_ref.to_dict()

    # 2. Fetch User
    users = db.collection('users').where('username', '==', username).where('appid', '==', app_data['appid']).limit(1).stream()
    user_doc = next(users, None)
    if user_doc is None:
        return {"status": "error", "success": False, "message": "User not found."}
    
    # 3. Reset HWID in Firestore
    user_doc.reference.update({'hwid': None})
    
    return {"status": "success", "success": True, "message": "HWID reset successfully."}


# ---- নতুন যুক্ত করা রাউট (HWID দেখার জন্য) ----
@router.get("/api/1.0/get_hwid")
async def get_hwid(username: str, ownerid: str, app_secret: str):
    # 1. Fetch App
    apps = db.collection('applications').where('ownerid', '==', ownerid).where('app_secret', '==', app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    if not app_doc_ref:
        return {"status": "error", "success": False, "message": "Invalid application details."}
    app_data = app_doc_ref.to_dict()

    # 2. Fetch User
    users = db.collection('users').where('username', '==', username).where('appid', '==', app_data['appid']).limit(1).stream()
    user_doc = next(users, None)
    if user_doc is None:
        return {"status": "error", "success": False, "message": "User not found."}
    
    u_data = user_doc.to_dict()
    current_hwid = u_data.get('hwid') # ডাটাবেজ থেকে HWID নেওয়া হচ্ছে
    
    return {
        "status": "success", 
        "success": True, 
        "username": username,
        "hwid": current_hwid  # যদি HWID না থাকে তবে null/None দেখাবে
    }
