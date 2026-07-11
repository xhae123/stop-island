import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Shop(Base):
    __tablename__ = "shops"

    id = Column(String, primary_key=True)  # 슬러그. 예: 'cafe-a'
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # cafe | restaurant | bookstore | bar | craft
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Seat(Base):
    __tablename__ = "seats"

    id = Column(String, primary_key=True)  # 예: 'a1'
    label = Column(String, nullable=False)  # 예: 'A1'
    capacity = Column(Integer, nullable=False)
    position_label = Column(String, nullable=True)
    is_open = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(String, primary_key=True, default=gen_uuid)
    device_id = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    shop_id = Column(String, ForeignKey("shops.id"), nullable=True)
    method = Column(String, nullable=False)  # 'photo' | 'manual'
    status = Column(String, nullable=False, default="pending")  # pending | approved | rejected
    token = Column(String, unique=True, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # NOTE: 원본 스키마는 (device_id, created_at::date) UNIQUE로 1일 1회 제한을 걸지만
    # SQLite는 표현식 기반 UNIQUE 제약을 지원하지 않아서 애플리케이션 레벨(라우터)에서 체크한다.

    __table_args__ = (
        Index("idx_verifications_device_date", "device_id", "created_at"),
        Index("idx_verifications_status", "status"),
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True, default=gen_uuid)
    seat_id = Column(String, ForeignKey("seats.id"), nullable=False)
    verify_token = Column(String, ForeignKey("verifications.token"), nullable=False)
    status = Column(String, nullable=False, default="active")  # active | expired | cancelled
    reserved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_reservations_seat_active", "seat_id"),
        Index("idx_reservations_expires", "expires_at"),
    )


class GuestbookEntry(Base):
    __tablename__ = "guestbook_entries"

    id = Column(String, primary_key=True, default=gen_uuid)
    content = Column(String, nullable=False)  # 최대 500자. 검증은 라우터에서.
    rating = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_guestbook_rating_range"),
        Index("idx_guestbook_created", "created_at"),
    )


class GuestbookShopTag(Base):
    __tablename__ = "guestbook_shop_tags"

    entry_id = Column(
        String, ForeignKey("guestbook_entries.id", ondelete="CASCADE"), primary_key=True
    )
    shop_id = Column(String, ForeignKey("shops.id"), primary_key=True)
