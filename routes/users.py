from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from database import db
from schemas import EndUserCreateRequest, UserListRequest, UserDeleteRequest, UserUpdateAction

router = APIRouter(tags=["Users"])

def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list): return res[0][0].value
        return res[0].value
    except Exception: return 0

@router.post("/users/create")
def create_end_user(data: EndUserCreateRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller_doc = next(seller_query, None)
    

    if not seller_doc:
        seller_doc = db.collection('sellers').document(data.ownerid).get()
        if not seller_doc.exists:
            raise HTTPException(status_code=404, detail="Seller error: not found")
            
    seller_data = seller_doc.to_dict()
    group = seller_data.get('seller_group', 0)
    
    if group != 2:
        current_app_users = get_secure_count(db.collection('users').where('appid', '==', data.appid).count())
            
        if current_app_users >= 24:
            plan_name = "Silver Developer" if group == 1 else "Free Developer"
            raise HTTPException(status_code=400, detail=f"{plan_name} Limit: Max 24 users per app. Upgrade to Gold for unlimited users!")

    dupes = db.collection('users').where('appid', '==', data.appid).where('username', '==', data.username).limit(1).stream()
    for _ in dupes: raise HTTPException(status_code=400, detail="Username exists")

    if data.expire_str:
        expires = datetime.strptime(data.expire_str, "%Y-%m-%dT%H:%M")
    elif data.days == 0: 
        expires = datetime(9999, 12, 31)
    else: 
        expires = datetime.utcnow() + timedelta(days=data.days)

    db.collection('users').add({
        'appid': data.appid,
        'username': data.username,
        'password': data.password,
        'expires_at': expires.isoformat(),
        'hwid': None
    })
    return {"status": "success"}

@router.post("/users/list")
def list_users(data: UserListRequest):
    users = db.collection('users').where('appid', '==', data.appid).stream()
    u_list = [{"id": d.id, **d.to_dict()} for d in users]
    return {"status": "success", "users": u_list}

@router.post("/users/delete")
def delete_user(data: UserDeleteRequest):
    db.collection('users').document(data.user_id).delete()
    return {"status": "success"}

@router.post("/users/action")
def user_action(data: UserUpdateAction):
    doc_ref = db.collection('users').document(data.user_id)
    doc = doc_ref.get()
    
    if not doc.exists: 
        raise HTTPException(status_code=404, detail="User not found")
    
    updates = {}

    if data.action == "reset_hwid":
        updates['hwid'] = None
    
    elif data.action == "toggle_lock":
        updates['hwid_locked'] = data.lock_state

    elif data.action == "set_expiry":
        if data.expire_str:
            updates['expires_at'] = data.expire_str

    if updates:
        doc_ref.update(updates)
        return {"status": "success"}
    
    return {"status": "no_change"}
