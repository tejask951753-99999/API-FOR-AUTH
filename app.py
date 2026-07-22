import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

from database import db


from routes.auth import router as auth_router
from routes.apps import router as apps_router
from routes.users import router as users_router
from routes.licenses import router as licenses_router
from routes.api import router as api_router
from routes.admin import router as admin_router
from routes.health import router as health_router
from routes.reseller import router as reseller_router


app.include_router(auth_router)
app.include_router(apps_router)
app.include_router(users_router)
app.include_router(licenses_router)
app.include_router(api_router)
app.include_router(admin_router)
app.include_router(health_router)
app.include_router(reseller_router)

