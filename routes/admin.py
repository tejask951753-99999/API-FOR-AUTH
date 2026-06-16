from fastapi import APIRouter, HTTPException
from database import db
from schemas import AdminSearchRequest, AdminUpdateRequest, AdminPublishUpdate
from datetime import datetime

router = APIRouter(tags=["Admin"])

def get_secure_count(agg):
    try:
        res = agg.get()
        # [load=patern:load, list]
        if isinstance(res[0], list):
            return res[0][0].value
        return res[0].value
    except Exception as e:
        print(f"Count Error: {e}")
        return 0

@router.post("/admin/stats")
def get_admin_stats():

    sellers_count = get_secure_count(db.collection('sellers').count())
    users_count = get_secure_count(db.collection('users').count())


    silver_count = get_secure_count(db.collection('sellers').where('seller_group', '==', 1).count())
    gold_count = get_secure_count(db.collection('sellers').where('seller_group', '==', 2).count())


    apps_count = get_secure_count(db.collection('applications').count())

    return {
        "status": "success",
        "sellers": sellers_count,
        "users": users_count,
        "gold": gold_count,
        "silver": silver_count,
        "apps": apps_count 
    }

@router.post("/admin/search_seller")
def admin_search(data: AdminSearchRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller = next(seller_query, None)
    

    if not seller:
        seller = db.collection('sellers').document(data.ownerid).get()
        if not seller.exists:
            return {"status": "success", "found": False}
    
    d = seller.to_dict()
    app_agg = db.collection('applications').where('ownerid', '==', d.get('ownerid')).count()
    app_count = get_secure_count(app_agg)

    return {
        "status": "success",
        "found": True,
        "data": {
            "email": d.get('email'),
            "ownerid": d.get('ownerid'),
            "coins": d.get('coins', 0),
            "seller_group": d.get('seller_group', 0),
            "app_count": app_count 
        }
    }

@router.post("/admin/update_seller")
def admin_update(data: AdminUpdateRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller = next(seller_query, None)
    
    if seller:
        seller.reference.update({
            "seller_group": data.seller_group,
            "coins": data.coins
        })
        return {"status": "success"}
    
    raise HTTPException(status_code=404, detail="Seller not found")

@router.post("/admin/publish_update")
def publish_update(data: AdminPublishUpdate):
    # if data.secret_key == os.getenv(admin_secret)
    if data.secret_key != "lynx_admin_secret":
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    update_ref = db.collection('updates').document()
    update_ref.set({
        "message": data.message,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": datetime.now().timestamp()
    })
    return {"status": "success", "message": "Update published!"}

@router.get("/public/updates")
def get_updates():
    updates_query = db.collection('updates').order_by('timestamp', direction='DESCENDING').limit(10).stream()
    updates = []
    for u in updates_query:
        updates.append(u.to_dict())
    return {"status": "success", "updates": updates}
