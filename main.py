from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pymongo import MongoClient
from bson.objectid import ObjectId
import random, string

app = FastAPI()

# MongoDB connection
MONGO_URI = "YOUR_MONGODB_URI"
client = MongoClient(MONGO_URI)
db = client["license_db"]
licenses_col = db["licenses"]

# Static files & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Admin credentials (hardcoded)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password"

# In-memory session
logged_in_users = set()

class LicenseValidationRequest(BaseModel):
    license_key: str
    hwid: str

def generate_license_key():
    parts = ["".join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(4)]
    return "-".join(parts)

@app.get("/", response_class=HTMLResponse)
async def root():
    return {"message": "License API is running"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        logged_in_users.add(request.client.host)
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    if request.client.host not in logged_in_users:
        return RedirectResponse("/login")
    licenses = list(licenses_col.find())
    return templates.TemplateResponse("admin.html", {"request": request, "licenses": licenses})

@app.post("/admin/add_license")
async def add_license(request: Request):
    if request.client.host not in logged_in_users:
        return RedirectResponse("/login")
    new_license = {
        "license_key": generate_license_key(),
        "hwid": None,
        "status": "inactive"
    }
    licenses_col.insert_one(new_license)
    return RedirectResponse("/admin", status_code=302)

@app.post("/api/validate")
async def validate_license(data: LicenseValidationRequest):
    lic = licenses_col.find_one({"license_key": data.license_key})
    if not lic:
        return {"status": "error", "message": "License not found"}

    if lic["hwid"] is None:
        licenses_col.update_one({"_id": lic["_id"]}, {"$set": {"hwid": data.hwid, "status": "active"}})
        return {"status": "success", "message": "License activated"}

    if lic["hwid"] != data.hwid:
        return {"status": "error", "message": "HWID mismatch"}

    return {"status": "success", "message": "License validated"}

@app.post("/api/logout")
async def logout_license(data: LicenseValidationRequest):
    lic = licenses_col.find_one({"license_key": data.license_key, "hwid": data.hwid})
    if not lic:
        return {"status": "error", "message": "License not found or HWID mismatch"}
    licenses_col.update_one({"_id": lic["_id"]}, {"$set": {"hwid": None, "status": "inactive"}})
    return {"status": "success", "message": "License released"}
