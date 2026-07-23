import uuid
import secrets
from fastapi import APIRouter, HTTPException
from firebase_admin import firestore
from database import db
from schemas import AppCreateRequest, AppDeleteRequest, WebhookSaveRequest
 

router = APIRouter(tags=["Apps"])

def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list):
            return res[0][0].value
        return res[0].value
    except Exception:
        return 0

@router.post("/apps/create")
def create_app(data: AppCreateRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller_doc = next(seller_query, None)
    

    if not seller_doc:
        seller_doc = db.collection('sellers').document(data.ownerid).get()
        if not seller_doc.exists:
            raise HTTPException(status_code=404, detail=f"Seller {data.ownerid} not found")
    
    seller_data = seller_doc.to_dict()
    group = seller_data.get('seller_group', 0)
    

    current_apps_count = get_secure_count(db.collection('applications').where('ownerid', '==', data.ownerid).count())

    if group == 0 and current_apps_count >= 2:
        raise HTTPException(status_code=400, detail="Free Developer Limit: Max 2 Apps. Upgrade to Silver or Gold for more!")
    elif group == 1 and current_apps_count >= 10:
        raise HTTPException(status_code=400, detail="Silver Developer Limit: Max 10 Apps. Upgrade to Gold for unlimited apps!")

    
    appid = str(uuid.uuid4())
    app_secret = secrets.token_hex(16)
    
    db.collection('applications').add({
        'appid': appid,
        'app_secret': app_secret,
        'name': data.app_name,
        'ownerid': data.ownerid,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    
    return {"status": "success", "appid": appid, "app_secret": app_secret}

@router.post("/apps/list")
def list_apps(data: dict):
    ownerid = data.get("ownerid")
    apps_ref = db.collection('applications').where('ownerid', '==', ownerid).stream()
    apps_list = []
    for doc in apps_ref:
        d = doc.to_dict()
        user_agg = db.collection('users').where('appid', '==', d['appid']).count()
        lic_agg = db.collection('licenses').where('appid', '==', d['appid']).count()
        user_count = get_secure_count(user_agg)
        lic_count = get_secure_count(lic_agg)
        apps_list.append({
            "name": d['name'], 
            "appid": d['appid'], 
            "app_secret": d['app_secret'],
            "webhook_config": d.get('webhook_config', {}),
            "user_count": user_count,
            "license_count": lic_count
        })
    return {"status": "success", "apps": apps_list}

@router.post("/apps/delete")
def delete_app(data: AppDeleteRequest):

    apps = db.collection('applications').where('appid', '==', data.appid).limit(1).stream()
    app_doc = next(apps, None)
    
    if not app_doc:
        raise HTTPException(status_code=404, detail="App not found")


    batch = db.batch()
    users = db.collection('users').where('appid', '==', data.appid).stream()
    count = 0
    
    for u in users:
        batch.delete(u.reference)
        count += 1

        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0
            

    batch.delete(app_doc.reference)
    batch.commit()
    
    return {"status": "success"}

@router.post("/apps/webhook/save")
def save_webhook(data: WebhookSaveRequest):
    apps = db.collection('applications').where('appid', '==', data.appid).limit(1).stream()
    found = False
    for a in apps:
        a.reference.update({
            'webhook_config': {
                'url': data.webhook_url,
                'enabled': data.enabled,
                'show_hwid': data.show_hwid,
                'show_app': data.show_app,
                'show_ip': data.show_ip,
                'show_expiry': data.show_expiry,
                'error_enabled': data.error_enabled,
                'error_webhook_url': data.error_webhook_url
            }
        })
        found = True
    if found: return {"status": "success"}
    raise HTTPException(status_code=404, detail="App not found")
