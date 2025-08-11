import os
import certifi
from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from typing import Optional
from starlette.middleware.sessions import SessionMiddleware

# ---- Hardcoded admin credentials ----
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"

# MongoDB config (only for licenses)
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = os.environ.get("DB_NAME") or "license_db"
COLLECTION_NAME = os.environ.get("COLLECTION_NAME") or "licenses"

# Ensure folders exist
if not os.path.exists("static"):
    os.makedirs("static", exist_ok=True)
if not os.path.exists("templates"):
    os.makedirs("templates", exist_ok=True)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="super-secret-session-key")  # session for login
templates = Jinja2Templates(directory="templates")

# MongoDB connection
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

# ---- Login Routes ----
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session["logged_in"] = True
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

# Dependency to require login
def require_login(request: Request):
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/admin")

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    require_login(request)
    docs = []
    cursor = collection.find({})
    async for doc in cursor:
        docs.append(doc_to_dict(doc))
    return templates.TemplateResponse("admin.html", {"request": request, "licenses": docs})

# ---- License generation & activation ----
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
async def admin_add_license(request: Request):
    require_login(request)
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
