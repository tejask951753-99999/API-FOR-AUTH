import os
import sys
import json
import firebase_admin
from firebase_admin import credentials, firestore
from utils import log_err, log_success

try:

    env_creds = os.environ.get("SERVICE_ACCOUNT_JSON")
    
    if env_creds:
        cred_dict = json.loads(env_creds)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        log_success("Connected to Firebase via Environment Variable!")
        

    elif os.path.exists("serviceAccountKey.json"):
        with open("serviceAccountKey.json", "r") as f:
            cred_dict = json.load(f)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        log_success("Connected to Firebase Firestore via local JSON!")
        
    else:
        log_err("Firebase credentials not found (Env Var or JSON).")
        sys.exit(1)
        
except Exception as e:
    log_err(f"Failed to connect to Firebase: {e}")
    sys.exit(1)
