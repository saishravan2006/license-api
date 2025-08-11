import os
import certifi
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from typing import Optional

# Configuration: hardcoded URI (as requested). You can override with MONGO_URI env var if you want later.
MONGO_URI = os.environ.get("MONGO_URI") or "mongodb+srv://saishravan554:Stark123@cluster0.6hjlboi.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = os.environ.get("DB_NAME") or "license_db"
COLLECTION_NAME = os.environ.get("COLLECTION_NAME") or "licenses"

# Ensure folders exist
if not os.path.exists("static"):
    os.makedirs("static", exist_ok=True)
if not os.path.exists("templates"):
    os.makedirs("templates", exist_ok=True)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Connect to MongoDB with explicit CA bundle to avoid TLS handshake issues
mongo_client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

def doc_to_dict(doc):
    if not doc:
        return None
    d = dict(doc)
    _id = d.pop("_id", None)
    if _id is not None:
        d["id"] = str(_id)
    return d

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/admin")

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    docs = []
    cursor = collection.find({})
    async for doc in cursor:
        docs.append(doc_to_dict(doc))
    return templates.TemplateResponse("admin.html", {"request": request, "licenses": docs})


import random
import string
from pydantic import BaseModel

def generate_license_key(length=16):
    """Generate a random license key like 'AB12-CD34-EF56-GH78'."""
    chars = string.ascii_uppercase + string.digits
    key = '-'.join(
        ''.join(random.choice(chars) for _ in range(4))
        for _ in range(length // 4)
    )
    return key

@app.post("/admin/add_license")
async def admin_add_license():
    license_key = generate_license_key()
    await collection.insert_one({
        "key": license_key,
        "hwid": None,
        "activated": False
    })
    return {"license_key": license_key, "status": "created"}

class ActivationRequest(BaseModel):
    license_key: str
    hwid: str

@app.post("/activate_license")
async def activate_license(data: ActivationRequest):
    license_doc = await collection.find_one({"key": data.license_key})
    if not license_doc:
        raise HTTPException(status_code=404, detail="Invalid license key")
    
    if license_doc.get("activated"):
        raise HTTPException(status_code=400, detail="License already activated")

    await collection.update_one(
        {"key": data.license_key},
        {"$set": {"hwid": data.hwid, "activated": True}}
    )
    return {"status": "activated", "license_key": data.license_key}
