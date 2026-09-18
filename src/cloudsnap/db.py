from __future__ import annotations

import datetime
from typing import List, AsyncGenerator

from sqlalchemy import ForeignKey, String, DateTime
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import selectinload
from dotenv import load_dotenv
import os

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")

from typing import Optional

class Base(AsyncAttrs, DeclarativeBase):
    pass


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    s3_key: Mapped[str] = mapped_column(String, unique=True)
    caption: Mapped[Optional[str]] = mapped_column(String(2200))
    create_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    comments: Mapped[List[Comment]] = relationship(
        back_populates="photo",
        cascade="all, delete-orphan",
        order_by="Comment.created_at",
    )



class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    photo: Mapped["Photo"] = relationship(back_populates="comments")

engine = create_async_engine(DB_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def ShutdownDB() -> None:
    await engine.dispose()

