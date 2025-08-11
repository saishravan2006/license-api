from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pymongo import MongoClient
import random
import string
import os

app = FastAPI()

# ===== MongoDB Connection =====
MONGO_URL = os.getenv("MONGO_URL", "your-mongo-url-here")
client = MongoClient(MONGO_URL)
db = client["license_db"]
licenses = db["licenses"]

# ===== Templates =====
templates = Jinja2Templates(directory="templates")

# ===== License Generator =====
def generate_license_key():
    return "-".join(
        "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        for _ in range(4)
    )

# ===== Routes =====
@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>License API is running</h1>"

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    license_list = list(licenses.find({}, {"_id": 0}))
    return templates.TemplateResponse("admin.html", {"request": request, "licenses": license_list})

@app.post("/admin/add", response_class=HTMLResponse)
async def add_license(request: Request):
    new_license = generate_license_key()
    licenses.insert_one({"license_key": new_license, "hwid": None, "status": "unused"})
    license_list = list(licenses.find({}, {"_id": 0}))
    return templates.TemplateResponse("admin.html", {"request": request, "licenses": license_list})

# ===== API Endpoint for Validation =====
@app.post("/api/validate")
async def validate_license(data: dict):
    license_key = data.get("license_key")
    hwid = data.get("hwid")

    lic = licenses.find_one({"license_key": license_key})
    if not lic:
        return {"status": "error", "message": "License key not found"}

    if lic["hwid"] is None:
        licenses.update_one({"license_key": license_key}, {"$set": {"hwid": hwid, "status": "active"}})
        return {"status": "success", "message": "License activated"}
    elif lic["hwid"] == hwid:
        return {"status": "success", "message": "License already active for this device"}
    else:
        return {"status": "error", "message": "License already bound to another device"}

@app.post("/api/logout")
async def logout_license(data: dict):
    license_key = data.get("license_key")
    hwid = data.get("hwid")

    lic = licenses.find_one({"license_key": license_key})
    if lic and lic["hwid"] == hwid:
        licenses.update_one({"license_key": license_key}, {"$set": {"hwid": None, "status": "unused"}})
        return {"status": "success", "message": "License released"}
    return {"status": "error", "message": "Invalid license or HWID"}
