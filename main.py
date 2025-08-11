from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from bson import ObjectId
from pymongo import MongoClient
import uuid
import secrets

app = FastAPI()

# MongoDB connection
client = MongoClient("mongodb+srv://saishravan554:stark123@cluster0.6hjlboi.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["license_db"]
licenses_col = db["licenses"]

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin", status_code=302)
        response.set_cookie(key="auth", value="true")
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    if request.cookies.get("auth") != "true":
        return RedirectResponse(url="/")
    licenses = list(licenses_col.find())
    return templates.TemplateResponse("admin.html", {"request": request, "licenses": licenses})

@app.post("/generate")
async def generate_license(request: Request):
    if request.cookies.get("auth") != "true":
        return RedirectResponse(url="/")
    new_license = {
        "license_key": f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}",
        "hwid": None
    }
    licenses_col.insert_one(new_license)
    return RedirectResponse(url="/admin", status_code=302)

@app.post("/revoke/{license_id}")
async def revoke_license(request: Request, license_id: str):
    if request.cookies.get("auth") != "true":
        return RedirectResponse(url="/")
    licenses_col.delete_one({"_id": ObjectId(license_id)})
    return RedirectResponse(url="/admin", status_code=302)

@app.post("/api/validate")
async def validate_license(data: dict):
    license_key = data.get("license_key")
    hwid = data.get("hwid")
    license_entry = licenses_col.find_one({"license_key": license_key})
    if not license_entry:
        return {"status": "error", "message": "License not found"}
    if license_entry.get("hwid") and license_entry["hwid"] != hwid:
        return {"status": "error", "message": "License already in use"}
    licenses_col.update_one({"_id": license_entry["_id"]}, {"$set": {"hwid": hwid}})
    return {"status": "success", "message": "License validated"}

@app.post("/api/logout")
async def logout_license(data: dict):
    license_key = data.get("license_key")
    hwid = data.get("hwid")
    licenses_col.update_one({"license_key": license_key, "hwid": hwid}, {"$set": {"hwid": None}})
    return {"status": "success", "message": "License released"}
