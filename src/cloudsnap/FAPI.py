from fastapi import FastAPI, UploadFile,HTTPException, Depends, Request, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uuid
from typing import Annotated, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from dotenv import load_dotenv
import os
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from .S3Bucket import upload_file, delete_file
from PIL import Image
import io
import json

from .db import ShutdownDB, get_session, Photo, Comment

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename='logs'
)
logger = logging.getLogger(__name__)

load_dotenv()

BUCKET_NAME = os.getenv("BUCKET_NAME")
CLOUDFRONT_DOMAIN = os.getenv("CLOUDFRONT_DOMAIN")

ALLOWED_TYPES = set(os.getenv("ALLOWED_TYPES", "").split(","))
EXTENSION_MAP = json.loads(os.getenv("EXTENSION_MAP", "{}"))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 0))

if not BUCKET_NAME or not CLOUDFRONT_DOMAIN or not ALLOWED_TYPES or not EXTENSION_MAP or not MAX_FILE_SIZE:
    raise RuntimeError("Failed to fetch credentials from environment (.env), check FAPI.py and .env")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting server lifespan")
    yield
    logger.info("Stopping server lifespan")
    await ShutdownDB()

app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:8080",
    "http://localhost:8501"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
# https://fastapi.tiangolo.com/tutorial/sql-databases/

def build_photo_url(s3_key: str) -> str:
    if not CLOUDFRONT_DOMAIN:
        raise RuntimeError("CLOUDFRONT_DOMAIN not mentioned")
    return f"https://{CLOUDFRONT_DOMAIN}/{s3_key}"

# ------------------------------------
class PhotoOut(BaseModel):
    id: int
    caption: Optional[str]
    url: str


class CommentIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


class CommentOut(BaseModel):
    id: int
    text: str
# -------------------------------------

@app.post("/uploadfile/", response_model=PhotoOut)
@limiter.limit("5/minute")
async def create_upload_file(
        request: Request,
        file: UploadFile,
        session: SessionDep,
        caption: Annotated[str, Form(max_length=2200)]
    ):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    contents = await file.read(MAX_FILE_SIZE + 1)
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large")
    await file.seek(0)

    FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

    try:
        img_check = Image.open(io.BytesIO(contents))
        detected_format = img_check.format
        img_check.verify()
    except Exception:
        raise HTTPException(status_code=415, detail="File is not a valid image")

    content_type = FORMAT_TO_MIME.get(detected_format)
    if content_type is None:
        raise HTTPException(status_code=415, detail="Unsupported image format")

    extension = EXTENSION_MAP.get(content_type, "bin")
    safe_key = f"{uuid.uuid4()}.{extension}"

    success = await upload_file(file.file, BUCKET_NAME, safe_key, content_type=content_type)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to upload file")

    photo = Photo(s3_key=safe_key, caption=caption)
    session.add(photo)

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await delete_file(BUCKET_NAME, safe_key)
        raise HTTPException(status_code=500, detail="Failed to save photo record")
    await session.refresh(photo)

    return PhotoOut(id=photo.id, caption=photo.caption, url=build_photo_url(photo.s3_key))


@app.get("/photos", response_model=List[PhotoOut])
async def list_photos(session: SessionDep,
                      limit: int = Query(default=20, ge=1, le=100),
                      offset: int = Query(default=0, ge=0),
                      ):

    result = await session.execute(
        select(Photo).order_by(Photo.create_date.desc()).limit(limit).offset(offset)
    )
    photos = result.scalars().all()
    return [PhotoOut(id=p.id, caption=p.caption, url=build_photo_url(p.s3_key)) for p in photos]


@app.post("/photos/{photo_id}/comments", response_model=CommentOut)
@limiter.limit("5/minute")
async def add_comment(request: Request, photo_id: int, comment: CommentIn, session: SessionDep):
    photo = await session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    new_comment = Comment(photo_id=photo_id, text=comment.text)
    session.add(new_comment)
    await session.commit()
    await session.refresh(new_comment)
    return CommentOut(id=new_comment.id, text=new_comment.text)


@app.get("/photos/{photo_id}/comments", response_model=List[CommentOut])
async def get_comments(photo_id: int,
                       session: SessionDep,
                       limit: int = Query(default=20, ge=1, le=100),
                       offset: int = Query(default=0, ge=0),
                       ):
    photo = await session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    result = await session.execute(
        select(Comment).where(Comment.photo_id == photo_id).order_by(Comment.created_at).limit(limit).offset(offset)
    )
    comments = result.scalars().all()
    return [CommentOut(id=c.id, text=c.text) for c in comments]

@app.get("/health")
async def health_check(session: SessionDep):
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")


