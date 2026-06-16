from datetime import datetime
from fastapi import APIRouter

router = APIRouter(tags=["Health"])

@router.api_route("/", methods=["GET", "HEAD"])
def health_check():
    return {"status": "active", "timestamp": datetime.utcnow().isoformat()}
