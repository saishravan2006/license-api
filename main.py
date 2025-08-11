import os
import asyncio
import certifi
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.templating import Jinja2Templates

# --- Load environment variables ---
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("❌ MONGO_URI environment variable not set!")

# --- MongoDB connection ---
mongo_client = AsyncIOMotorClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=10000
)
db = mongo_client["licenses_db"]  # Change to your actual DB name

# --- FastAPI app ---
app = FastAPI()

# Static & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# --- Test DB connection on startup ---
@app.on_event("startup")
async def startup_db_client():
    try:
        await mongo_client.server_info()
        print("✅ Connected to MongoDB successfully")
    except Exception as e:
        print("❌ MongoDB connection failed:", e)
        raise e


@app.on_event("shutdown")
async def shutdown_db_client():
    mongo_client.close()


# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    admin = await db.admins.find_one({"username": username, "password": password})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return RedirectResponse(url="/admin", status_code=302)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    licenses = await db.licenses.find().to_list(length=100)
    return templates.TemplateResponse("admin.html", {"request": request, "licenses": licenses})


@app.post("/admin/add_license")
async def add_license(license_key: str = Form(...), owner: str = Form(...)):
    await db.licenses.insert_one({"license_key": license_key, "owner": owner})
    return RedirectResponse(url="/admin", status_code=302)


@app.get("/health")
async def health_check():
    try:
        await mongo_client.server_info()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "details": str(e)}


# --- Run locally ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
