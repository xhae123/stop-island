import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)

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
    """영수증 인증. D-02/D-05/D-06 반영.

    핵심 결정(03-verify.md):
    - pending 상태 폐기. 판정은 POST /api/verify 안에서 동기적으로 끝나고
      status는 최종값('approved'|'rejected')으로만 INSERT된다.
    - review성 판정(confidence 미달, fuzzy 경계선)은 승인으로 승격하고
      needs_audit=True로 기록한다(D-05). 사용자는 감사 플래그를 알 수 없다.
    - 실패(rejected/retry) 시도도 전부 row로 남긴다(통계·어뷰징 추적·감사 참고).
      API 응답의 'retry'는 DB상 'rejected' + reason_code로 구분한다.
    """

    __tablename__ = "verifications"

    id = Column(String, primary_key=True, default=gen_uuid)
    device_id = Column(String, nullable=False)  # D-07. 익명 식별자(X-Device-Id)
    image_url = Column(String, nullable=True)  # photo 경로 원본 저장 위치. manual이면 null
    image_hash = Column(String, nullable=True)  # 중복 검출용(승인번호 None 폴백 키)
    shop_id = Column(String, ForeignKey("shops.id"), nullable=True)
    method = Column(String, nullable=False)  # 'photo' | 'manual'
    status = Column(String, nullable=False)  # 'approved' | 'rejected' (2값 — pending 없음)
    needs_audit = Column(Boolean, nullable=False, default=False)  # D-05 사후감사 플래그
    reason_code = Column(String, nullable=True)  # 판정 사유 코드(03-verify.md reason_code 표)
    confidence = Column(Float, nullable=True)  # OCR confidence(감사 참고)
    ocr_store_name = Column(String, nullable=True)  # OCR이 읽은 상호명(감사 참고)
    ocr_date = Column(String, nullable=True)  # OCR이 읽은 영수증 날짜(감사 참고)
    approval_number = Column(String, nullable=True)  # 영수증 승인번호(중복 검출 1순위 키)
    token = Column(String, unique=True, nullable=True)  # approved일 때만 발급. 예약에 사용
    # verify_date: 판정 시각의 KST 날짜 'YYYY-MM-DD'. D-01 하루 경계 키.
    # created_at(UTC)이 아니라 이 컬럼이 1일 1회·당일 방문 수의 기준이다.
    verify_date = Column(String, nullable=False)
    verified_at = Column(DateTime, nullable=True)  # approved 확정 시각
    audited_at = Column(DateTime, nullable=True)  # 감사 완료 시각. 미감사면 null
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        # D-06: 1일 1회 제한을 DB 레벨에서 직렬화한다. approved만 유니크 —
        # rejected/retry 재시도는 무제한이고, 감사 무효화(rejected 전환) 후 재인증도 허용된다.
        # 동시 제출(VF-901)은 이 부분 유니크 INSERT가 원자적 관문 역할을 한다.
        Index(
            "uq_verif_device_day_approved",
            "device_id",
            "verify_date",
            unique=True,
            sqlite_where=text("status='approved'"),
        ),
        # 재진입 복원(GET /api/verify/status)·통계용 일반 조회 인덱스
        Index("idx_verifications_device_date", "device_id", "verify_date"),
        Index("idx_verifications_status", "status"),
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True, default=gen_uuid)
    seat_id = Column(String, ForeignKey("seats.id"), nullable=False)
    verify_token = Column(String, ForeignKey("verifications.token"), nullable=False)
    # device_id: 예약 소유 검증용(D-10 내 예약 조회, RSV-801 자리 비우기 권한).
    # verify_token만으로도 추적 가능하지만, 소유 검증을 토큰 노출 없이 하려고 별도 저장한다.
    device_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")  # active | expired | cancelled
    reserved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # reserved_at + 2시간(D-11)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        # RSV-502 / SYS-401: 좌석당 active 예약은 최대 1건. 이 부분 유니크가
        # 동시 예약의 원자적 관문이다 — reserve 라우터가 INSERT 후 IntegrityError를
        # 잡아 409 SEAT_TAKEN으로 응답한다. 애플리케이션 레벨 체크만으로는 race를 못 막는다.
        Index(
            "uq_reservation_seat_active",
            "seat_id",
            unique=True,
            sqlite_where=text("status='active'"),
        ),
        Index("idx_reservations_expires", "expires_at"),
    )


class GuestbookEntry(Base):
    __tablename__ = "guestbook_entries"

    id = Column(String, primary_key=True, default=gen_uuid)
    content = Column(String, nullable=False)  # 최대 500자. 검증은 라우터에서(D-18)
    rating = Column(Integer, nullable=True)  # 1~5 또는 null(D-17)
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
