from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="SIH26168 Member 6 Prototype Backend")
api_router = APIRouter(prefix="/api")


# ---------- StatusCheck (kept from starter) ----------
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


# ---------- Member 4 offline .roadpack catalog (metadata only) ----------
# Mirrors the .roadpack manifest fields consumed by Member 6's RegionSelector.
# The prototype ships these as constants so the app never needs internet
# to enumerate provisioned regions.
class RoadPackRegion(BaseModel):
    regionId: str
    name: str
    minLatDeg: float
    maxLatDeg: float
    minLonDeg: float
    maxLonDeg: float
    version: str
    source: str  # "demo" | "provisioned"


CATALOG: List[RoadPackRegion] = [
    RoadPackRegion(
        regionId="demo-sandbox",
        name="Demo Sandbox (0,0)",
        minLatDeg=-0.5, maxLatDeg=0.5, minLonDeg=-0.5, maxLonDeg=0.5,
        version="0.1.0", source="demo",
    ),
    RoadPackRegion(
        regionId="in-bengaluru",
        name="Bengaluru",
        minLatDeg=12.80, maxLatDeg=13.15, minLonDeg=77.45, maxLonDeg=77.80,
        version="1.0.0", source="provisioned",
    ),
    RoadPackRegion(
        regionId="in-vizag",
        name="Visakhapatnam",
        minLatDeg=17.60, maxLatDeg=17.85, minLonDeg=83.15, maxLonDeg=83.40,
        version="1.0.0", source="provisioned",
    ),
    RoadPackRegion(
        regionId="in-delhi",
        name="Delhi NCR",
        minLatDeg=28.40, maxLatDeg=28.90, minLonDeg=76.90, maxLonDeg=77.50,
        version="1.0.0", source="provisioned",
    ),
]


class RegionResolveResponse(BaseModel):
    active: Optional[RoadPackRegion]
    outOfCoverage: bool
    count: int


@api_router.get("/")
async def root():
    return {"service": "member6-prototype", "pipeline": "Android→M2→M1→M3→M4→M5→JNI→M6"}


@api_router.get("/roadpacks", response_model=List[RoadPackRegion])
async def list_roadpacks():
    """Return provisioned + demo .roadpack region metadata. Offline-safe."""
    return CATALOG


@api_router.get("/roadpacks/resolve", response_model=RegionResolveResponse)
async def resolve_region(lat: float, lon: float):
    """Server-side mirror of Member 6's RegionSelector for cross-checking."""
    for r in CATALOG:
        if r.minLatDeg <= lat <= r.maxLatDeg and r.minLonDeg <= lon <= r.maxLonDeg:
            return RegionResolveResponse(active=r, outOfCoverage=False, count=len(CATALOG))
    return RegionResolveResponse(active=None, outOfCoverage=True, count=len(CATALOG))


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.dict())
    doc = status_obj.model_dump()
    await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    return [StatusCheck(**s) for s in status_checks]


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
