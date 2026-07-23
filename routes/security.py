from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from database import db
from schemas import (
    LogListRequest,
    LogClearRequest,
    BlacklistAddRequest,
    BlacklistRemoveRequest,
    BlacklistListRequest
)
from routes.api import invalidate_blacklist_cache

router = APIRouter(tags=["Security & Logs"])

@router.post("/logs/list")
def list_logs(data: LogListRequest):
    query = db.collection('logs').where('ownerid', '==', data.ownerid)
    if data.appid:
        query = query.where('appid', '==', data.appid)
    
    docs = query.stream()
    logs_list = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        logs_list.append(item)
    
    logs_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return {"status": "success", "logs": logs_list[:200]}

@router.post("/logs/clear")
def clear_logs(data: LogClearRequest):
    query = db.collection('logs').where('ownerid', '==', data.ownerid)
    if data.appid:
        query = query.where('appid', '==', data.appid)
    
    docs = query.stream()
    for d in docs:
        d.reference.delete()
    
    return {"status": "success"}

@router.post("/security/blacklist/add")
def add_blacklist_ip(data: BlacklistAddRequest):
    ip_clean = data.ip.strip()
    if not ip_clean:
        raise HTTPException(status_code=400, detail="Invalid IP address")
    
    existing = db.collection('blacklisted_ips').where('ownerid', '==', data.ownerid).where('ip', '==', ip_clean).limit(1).get()
    if existing:
        return {"status": "success", "message": "IP is already blacklisted"}
    
    db.collection('blacklisted_ips').add({
        'ownerid': data.ownerid,
        'ip': ip_clean,
        'reason': data.reason or "Manual Blacklist",
        'created_at': datetime.now(timezone.utc).isoformat()
    })
    invalidate_blacklist_cache(data.ownerid)
    return {"status": "success", "message": "IP successfully blacklisted"}

@router.post("/security/blacklist/remove")
def remove_blacklist_ip(data: BlacklistRemoveRequest):
    ip_clean = data.ip.strip()
    docs = db.collection('blacklisted_ips').where('ownerid', '==', data.ownerid).where('ip', '==', ip_clean).stream()
    found = False
    for d in docs:
        d.reference.delete()
        found = True
    
    if not found:
        raise HTTPException(status_code=404, detail="IP not found in blacklist")

    invalidate_blacklist_cache(data.ownerid)
    return {"status": "success", "message": "IP unblacklisted successfully"}

@router.post("/security/blacklist/list")
def list_blacklist_ips(data: BlacklistListRequest):
    docs = db.collection('blacklisted_ips').where('ownerid', '==', data.ownerid).stream()
    ip_list = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        ip_list.append(item)
    
    ip_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return {"status": "success", "blacklisted_ips": ip_list}
