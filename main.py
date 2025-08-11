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

@app.post("/add_license")
async def add_license(key: str = Form(...), hwid: Optional[str] = Form(None)):
    existing = await collection.find_one({"key": key})
    if existing:
        # prevent duplicate
        return RedirectResponse(url="/admin", status_code=303)
    await collection.insert_one({"key": key, "hwid": hwid or None, "activated": bool(hwid)})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/delete_license/{license_id}")
async def delete_license(license_id: str):
    try:
        _id = ObjectId(license_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    await collection.delete_one({"_id": _id})
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/verify/{key}/{hwid}")
async def verify_license(key: str, hwid: str):
    lic = await collection.find_one({"key": key})
    if not lic:
        return {"status": "invalid"}
    if lic.get("hwid"):
        if lic.get("hwid") == hwid:
            return {"status": "valid"}
        else:
            return {"status": "hwid_mismatch"}
    # bind hwid
    await collection.update_one({"_id": lic["_id"]}, {"$set": {"hwid": hwid, "activated": True}})
    return {"status": "valid"}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
