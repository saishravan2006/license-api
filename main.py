# main.py
import os
import certifi
import random
import string
from datetime import datetime
from typing import Optional

from fastapi import (
    FastAPI,
    Request,
    Form,
    HTTPException,
    status,
)
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.sessions import SessionMiddleware

# -----------------------
# CONFIG - edit these
# -----------------------
# Hardcoded admin credentials (kept in code as you asked)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"

# MongoDB URI - set to your MongoDB connection string.
# You can hardcode here or provide via environment variable.
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = os.environ.get("DB_NAME") or "license_db"
COLLECTION_NAME = os.environ.get("COLLECTION_NAME") or "licenses"

# Session secret for session middleware (in production, use a secure long secret)
SESSION_SECRET = os.environ.get("SESSION_SECRET") or "replace-with-a-long-secret"

# -----------------------
# APP INIT
# -----------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# templates directory - ensure your templates are at ./templates/login.html and ./templates/admin.html
templates = Jinja2Templates(directory="templates")

# optionally serve a "static" folder if your admin html references CSS/JS there
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# -----------------------
# MONGO INIT
# -----------------------
# Use certifi to ensure proper TLS CA bundle
mongo_client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# -----------------------
# Helpers
# -----------------------
def generate_license_key(grouped=True, length=16):
    """
    Generate a random license key.
    If grouped=True, returns keys like AB12-CD34-EF56-GH78 (groups of 4 separated by '-').
    Otherwise returns a continuous string of length characters.
    """
    chars = string.ascii_uppercase + string.digits
    if not grouped:
        return ''.join(random.choice(chars) for _ in range(length))
    groups = []
    group_size = 4
    num_groups = length // group_size
    for _ in range(num_groups):
        groups.append(''.join(random.choice(chars) for _ in range(group_size)))
    return '-'.join(groups)

def license_doc_to_dict(doc):
    if not doc:
        return None
    d = dict(doc)
    d["_id"] = str(d.get("_id"))  # to make it JSON serializable for templates if needed
    # convert datetimes if present
    if isinstance(d.get("created_at"), datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d

def require_login(request: Request):
    """Raises HTTPException(401) if not logged in via session."""
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

# -----------------------
# Pydantic models
# -----------------------
class ActivateRequest(BaseModel):
    license_key: str
    hwid: str

# -----------------------
# Routes: Login / Logout / Admin
# -----------------------
@app.get("/login")
async def login_get(request: Request):
    """
    Render the login HTML. The template should POST to /login with form fields:
      - username
      - password
    We found login.html in your ZIP; ensure it expects those names.
    """
    # if already logged in, redirect to admin
    if request.session.get("logged_in"):
        return RedirectResponse(url="/admin")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Process login form. Hardcoded credentials are used.
    On success, set session["logged_in"] and redirect to /admin.
    On failure, re-render login.html with an error message.
    """
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session["logged_in"] = True
        # optional: store username
        request.session["username"] = username
        return RedirectResponse(url="/admin", status_code=303)
    # fail: show login page with error (template should display the 'error' variable)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/admin")
async def admin_page(request: Request):
    """
    Admin dashboard. Renders templates/admin.html with current licenses.
    The template should include an "Add New License" button which calls POST /admin/add_license (AJAX or form).
    """
    try:
        require_login(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)

    # fetch licenses from DB (most recent first)
    cursor = collection.find().sort("created_at", -1)
    docs = []
    async for doc in cursor:
        docs.append(license_doc_to_dict(doc))
    return templates.TemplateResponse("admin.html", {"request": request, "licenses": docs})

# -----------------------
# Admin action: generate & store license
# -----------------------
@app.post("/admin/add_license")
async def admin_add_license(request: Request, owner: Optional[str] = Form(None)):
    """
    Generate a license key, store it in MongoDB and return JSON.
    Owner is optional (form field); you can pass owner via form if you want.
    Requires admin login (session).
    """
    try:
        require_login(request)
    except HTTPException:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    # generate a grouped key like XXXX-XXXX-XXXX-XXXX
    license_key = generate_license_key(grouped=True, length=16)

    doc = {
        "license_key": license_key,
        "owner": owner or None,
        "hwid": None,
        "activated": False,
        "created_at": datetime.utcnow(),
    }
    await collection.insert_one(doc)
    return {"status": "created", "license_key": license_key}

# -----------------------
# Endpoint for device activation
# -----------------------
@app.post("/activate_license")
async def activate_license(payload: ActivateRequest):
    """
    Device (client) should POST JSON:
    {
      "license_key": "XXXX-XXXX-XXXX-XXXX",
      "hwid": "device-hwid-string"
    }
    This will check the license, set hwid and activated=True and return success or error.
    """
    license_doc = await collection.find_one({"license_key": payload.license_key})
    if not license_doc:
        raise HTTPException(status_code=404, detail="Invalid license key")

    if license_doc.get("activated"):
        # If already activated to same hwid, allow; otherwise forbid
        if license_doc.get("hwid") == payload.hwid:
            return {"status": "already_activated", "license_key": payload.license_key}
        raise HTTPException(status_code=400, detail="License already activated on another device")

    # activate license
    await collection.update_one(
        {"license_key": payload.license_key},
        {"$set": {"hwid": payload.hwid, "activated": True, "activated_at": datetime.utcnow()}}
    )
    return {"status": "activated", "license_key": payload.license_key}

# -----------------------
# Optional: endpoint to list a license (JSON)
# -----------------------
@app.get("/admin/licenses/{license_key}")
async def get_license_detail(request: Request, license_key: str):
    try:
        require_login(request)
    except HTTPException:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    doc = await collection.find_one({"license_key": license_key})
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    return license_doc_to_dict(doc)

# -----------------------
# Root / healthcheck
# -----------------------
@app.get("/")
async def root():
    return {"message": "License API is running"}

# -----------------------
# If running directly: uvicorn main:app --reload
# -----------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
