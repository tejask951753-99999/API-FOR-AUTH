import os
import secrets
from fastapi import APIRouter, HTTPException
from database import db
from schemas import (
    AdminSearchRequest, 
    AdminUpdateRequest, 
    AdminPublishUpdate,
    AdminSiteLinksRequest,
    AdminSiteLinksUpdateRequest,
    AdminVerifyRequest,
    AdminSellersRequest,
    AdminUsersRequest,
    AdminCodesRequest,
    AdminCodeGenerateRequest,
    AdminCleanRequest,
    AdminCodeActionRequest,
    AdminAppsRequest,
    AdminEmailsRequest,
    AdminEmailAddRequest,
    AdminEmailRemoveRequest,
    AdminResellerDeleteRequest
)
from datetime import datetime
 

router = APIRouter(tags=["Admin"])
SITE_LINKS_DOC_ID = "site_links"
DEFAULT_SITE_LINKS = {
    "discord_url": "https://dsc.gg/lynx-modz",
    "github_url": "https://github.com/Lynxmodzz"
}

def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list):
            return res[0][0].value
        return res[0].value
    except Exception:
        return 0

try:
    if os.path.exists("admin_Secret.txt"):
        with open("admin_Secret.txt", "r") as f:
            ADMIN_SECRET = f.read().strip()
    elif os.path.exists("../admin_Secret.txt"):
        with open("../admin_Secret.txt", "r") as f:
            ADMIN_SECRET = f.read().strip()
    else:
        ADMIN_SECRET = "fusion_admin_secret"
except Exception:
    ADMIN_SECRET = "fusion_admin_secret"



def get_site_links_payload():
    doc = db.collection('settings').document(SITE_LINKS_DOC_ID).get()
    payload = DEFAULT_SITE_LINKS.copy()
    if doc.exists:
        data = doc.to_dict() or {}
        payload["discord_url"] = data.get("discord_url") or DEFAULT_SITE_LINKS["discord_url"]
        payload["github_url"] = data.get("github_url") or DEFAULT_SITE_LINKS["github_url"]
    return payload

@router.post("/admin/stats")
def get_admin_stats(data: AdminVerifyRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
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

@router.post("/admin/verify")
def verify_admin(data: AdminVerifyRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    if data.email:
        if data.email != "mxa@gmail.com":
            admin_doc = db.collection('admin_users').document(data.email).get()
            if not admin_doc.exists:
                raise HTTPException(status_code=403, detail="Email not authorized for admin access")
    return {"status": "success"}

@router.post("/admin/sellers")
def list_sellers(data: AdminSellersRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    sellers = db.collection('sellers').stream()
    s_list = []
    for s in sellers:
        d = s.to_dict()
        app_agg = db.collection('applications').where('ownerid', '==', d.get('ownerid')).count()
        app_count = get_secure_count(app_agg)
        s_list.append({
            "email": d.get("email"),
            "ownerid": d.get("ownerid"),
            "coins": d.get("coins", 0),
            "seller_group": d.get("seller_group", 0),
            "plan_expires_at": d.get("plan_expires_at"),
            "app_count": app_count
        })
    return {"status": "success", "sellers": s_list}

@router.post("/admin/users")
def list_users(data: AdminUsersRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    users = db.collection('users').stream()
    u_list = []
    apps_cache = {}
    apps = db.collection('applications').stream()
    for app in apps:
        ad = app.to_dict()
        apps_cache[ad['appid']] = {"name": ad['name'], "ownerid": ad['ownerid']}
    sellers_cache = {}
    sellers = db.collection('sellers').stream()
    for sel in sellers:
        sd = sel.to_dict()
        sellers_cache[sd['ownerid']] = sd.get('email')
    for u in users:
        ud = u.to_dict()
        appid = ud.get("appid")
        app_info = apps_cache.get(appid, {"name": "Unknown App", "ownerid": None})
        owner_email = sellers_cache.get(app_info["ownerid"], "Unknown Seller")
        u_list.append({
            "id": u.id,
            "username": ud.get("username"),
            "password": ud.get("password"),
            "appid": appid,
            "app_name": app_info["name"],
            "owner_email": owner_email,
            "expires_at": ud.get("expires_at"),
            "hwid": ud.get("hwid"),
            "hwid_locked": ud.get("hwid_locked", True)
        })
    return {"status": "success", "users": u_list}

@router.post("/admin/apps")
def list_apps(data: AdminAppsRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    apps = db.collection('applications').stream()
    a_list = []
    sellers_cache = {}
    sellers = db.collection('sellers').stream()
    for sel in sellers:
        sd = sel.to_dict()
        sellers_cache[sd['ownerid']] = sd.get('email', 'Unknown')
    for app in apps:
        ad = app.to_dict()
        owner_email = sellers_cache.get(ad.get("ownerid"), "Unknown")
        user_agg = db.collection('users').where('appid', '==', ad.get("appid")).count()
        user_count = get_secure_count(user_agg)
        a_list.append({
            "appid": ad.get("appid"),
            "name": ad.get("name"),
            "ownerid": ad.get("ownerid"),
            "owner_email": owner_email,
            "user_count": user_count,
            "created_at": ad.get("created_at"),
            "webhook_config": ad.get("webhook_config", {})
        })
    return {"status": "success", "apps": a_list}

@router.post("/admin/emails")
def list_admin_emails(data: AdminEmailsRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    emails = db.collection('admin_users').stream()
    e_list = [{"email": e.id} for e in emails]
    return {"status": "success", "emails": e_list}

@router.post("/admin/add_email")
def add_admin_email(data: AdminEmailAddRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    db.collection('admin_users').document(data.email).set({"added_at": datetime.now().isoformat()})
    return {"status": "success"}

@router.post("/admin/remove_email")
def remove_admin_email(data: AdminEmailRemoveRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    db.collection('admin_users').document(data.email).delete()
    return {"status": "success"}

@router.post("/admin/codes")
def list_codes(data: AdminCodesRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    codes = db.collection('gift_codes').stream()
    c_list = [{"id": c.id, **c.to_dict()} for c in codes]
    return {"status": "success", "codes": c_list}

@router.post("/admin/generate_code")
def generate_code(data: AdminCodeGenerateRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    prefix = data.prefix.upper() if data.prefix else "FUSION"
    code_str = f"{prefix}-" + "-".join("".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(4)) for _ in range(3))
    db.collection('gift_codes').add({
        "code": code_str,
        "tier": data.tier,
        "duration_days": data.duration_days,
        "max_uses": data.max_uses,
        "use_count": 0,
        "used": False,
        "used_by": None,
        "used_at": None,
        "created_at": datetime.now().isoformat()
    })
    return {"status": "success", "code": code_str}

@router.post("/admin/clean_ghost_data")
def clean_ghost_data(data: AdminCleanRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    sellers = db.collection('sellers').stream()
    seller_ids = {s.to_dict().get("ownerid") for s in sellers if s.to_dict().get("ownerid")}
    apps = db.collection('applications').stream()
    app_ids = set()
    apps_to_delete = []
    for app in apps:
        ad = app.to_dict()
        if ad.get("ownerid") not in seller_ids:
            apps_to_delete.append(app.reference)
        else:
            app_ids.add(ad.get("appid"))
    for ref in apps_to_delete:
        ref.delete()
    users = db.collection('users').stream()
    users_to_delete = []
    for u in users:
        ud = u.to_dict()
        if ud.get("appid") not in app_ids:
            users_to_delete.append(u.reference)
    for ref in users_to_delete:
        ref.delete()
    licenses = db.collection('licenses').stream()
    licenses_to_delete = []
    for l in licenses:
        ld = l.to_dict()
        if ld.get("appid") not in app_ids:
            licenses_to_delete.append(l.reference)
    for ref in licenses_to_delete:
        ref.delete()
    return {
        "status": "success",
        "cleaned_apps": len(apps_to_delete),
        "cleaned_users": len(users_to_delete),
        "cleaned_licenses": len(licenses_to_delete)
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
            "seller_group": data.seller_group
        })
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Seller not found")

@router.post("/admin/publish_update")
def publish_update(data: AdminPublishUpdate):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    update_ref = db.collection('updates').document()
    update_ref.set({
        "message": data.message,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": datetime.now().timestamp()
    })
    return {"status": "success", "message": "Update published!"}

@router.post("/admin/site_links")
def get_admin_site_links(data: AdminSiteLinksRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return {"status": "success", **get_site_links_payload()}

@router.post("/admin/site_links/save")
def save_admin_site_links(data: AdminSiteLinksUpdateRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    discord_url = (data.discord_url or "").strip()
    github_url = (data.github_url or "").strip()
    if not discord_url or not github_url:
        raise HTTPException(status_code=400, detail="Both links are required")
    db.collection('settings').document(SITE_LINKS_DOC_ID).set({
        "discord_url": discord_url,
        "github_url": github_url,
        "updated_at": datetime.now().isoformat()
    }, merge=True)
    return {"status": "success", "message": "Links updated", "discord_url": discord_url, "github_url": github_url}

@router.get("/public/updates")
def get_updates():
    updates_query = db.collection('updates').order_by('timestamp', direction='DESCENDING').limit(10).stream()
    updates = []
    for u in updates_query:
        updates.append(u.to_dict())
    return {"status": "success", "updates": updates}

@router.get("/public/site_links")
def get_public_site_links():
    return {"status": "success", **get_site_links_payload()}

@router.post("/admin/action_code")
def action_code(data: AdminCodeActionRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    doc_ref = db.collection('gift_codes').document(data.code_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Code not found")
    if data.action == "delete":
        code_data = doc.to_dict()
        used_by = code_data.get("used_by")
        if used_by:
            seller_query = db.collection('sellers').where('ownerid', '==', used_by).limit(1).stream()
            seller = next(seller_query, None)
            if seller:
                seller.reference.update({'seller_group': 0, 'plan_expires_at': None})
        doc_ref.delete()
    elif data.action == "toggle_status":
        d = doc.to_dict()
        disabled = d.get("disabled", False)
        doc_ref.update({"disabled": not disabled})
    return {"status": "success"}

@router.post("/admin/resellers")
def admin_list_resellers(data: AdminVerifyRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    resellers_stream = db.collection('resellers').stream()
    resellers_list = []
    for r in resellers_stream:
        rd = r.to_dict()
        appid = rd.get('appid')
        ownerid = rd.get('ownerid')
        app_name = "Unknown App"
        app_doc = db.collection('applications').where('appid', '==', appid).limit(1).get()
        if app_doc:
            app_name = app_doc[0].to_dict().get('name', 'Unknown App')
        dev_email = "Unknown Dev"
        dev_doc = db.collection('sellers').where('ownerid', '==', ownerid).limit(1).get()
        if dev_doc:
            dev_email = dev_doc[0].to_dict().get('email', 'Unknown Dev')
        resellers_list.append({
            "id": r.id,
            "email": rd.get("email"),
            "appid": appid,
            "app_name": app_name,
            "ownerid": ownerid,
            "dev_email": dev_email,
            "daily_limit": rd.get("daily_limit", 0),
            "monthly_limit": rd.get("monthly_limit", 0),
            "can_create_users": rd.get("can_create_users", True),
            "can_delete_users": rd.get("can_delete_users", True),
            "can_create_license": rd.get("can_create_license", True),
            "can_delete_license": rd.get("can_delete_license", True),
            "can_reset_hwid": rd.get("can_reset_hwid", True),
            "can_update_expiry": rd.get("can_update_expiry", True),
            "created_at": rd.get("created_at")
        })
    return {"status": "success", "resellers": resellers_list}

@router.post("/admin/resellers/delete")
def admin_delete_resellers(data: AdminResellerDeleteRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    reseller_ids = [reseller_id for reseller_id in (data.reseller_ids or []) if reseller_id]
    if not reseller_ids:
        raise HTTPException(status_code=400, detail="No resellers selected")
    deleted = 0
    for reseller_id in reseller_ids:
        res_ref = db.collection('resellers').document(reseller_id)
        if res_ref.get().exists:
            res_ref.delete()
            deleted += 1
    return {"status": "success", "deleted": deleted}
