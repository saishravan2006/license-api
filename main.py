from fastapi import FastAPI, Depends, HTTPException, status, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from datetime import datetime
import secrets
import certifi
import random
import string

# =======================
# CONFIG
# =======================
MONGO_URI = "your-mongodb-uri"
DB_NAME = "license_db"
COLLECTION_NAME = "licenses"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"  # hardcoded

# =======================
# INIT
# =======================
app = FastAPI()
security = HTTPBasic()

client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
db = client[DB_NAME]
licenses_collection = db[COLLECTION_NAME]


# =======================
# AUTH FUNCTION
# =======================
def get_current_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# =======================
# MODELS
# =======================
class ActivateRequest(BaseModel):
    license_key: str
    hwid: str


# =======================
# HELPER: LICENSE GENERATOR
# =======================
def generate_license_key(length=16):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


# =======================
# ADMIN ENDPOINTS
# =======================
@app.post("/admin/add_license")
async def add_license(owner: str = Form(...), admin: str = Depends(get_current_admin)):
    license_key = generate_license_key()
    await licenses_collection.insert_one({
        "license_key": license_key,
        "owner": owner,
        "hwid": None,
        "created_at": datetime.utcnow(),
        "activated": False
    })
    return {"message": "License created", "license_key": license_key}


# =======================
# USER ENDPOINTS
# =======================
@app.post("/activate_license")
async def activate_license(data: ActivateRequest):
    license_doc = await licenses_collection.find_one({"license_key": data.license_key})
    if not license_doc:
        raise HTTPException(status_code=404, detail="License not found")

    if license_doc.get("activated") and license_doc.get("hwid") != data.hwid:
        raise HTTPException(status_code=400, detail="License already used on another device")

    await licenses_collection.update_one(
        {"license_key": data.license_key},
        {"$set": {"hwid": data.hwid, "activated": True}}
    )
    return {"message": "License activated successfully"}


@app.get("/")
async def home():
    return {"message": "License API is running"}
