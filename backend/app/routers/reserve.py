"""테이블 예약 확정 — POST /api/reserve (RSV-501/502/503/504/505/506, SYS-401).

핵심 방어 규약:
- 토큰 검증(RSV-503): verify_token은 존재·approved·오늘(KST) 발급이어야 한다.
  하나라도 어긋나면 401 TOKEN_EXPIRED — 프론트는 /verify로 보낸다(D-14).
- 멱등/더블탭(RSV-504/506/703, RSV-105): 이 토큰에 이미 active 예약이 있으면
  새 row를 만들지 않고 409 ALREADY_RESERVED + 기존 reservation_id를 돌려준다.
  프론트는 이를 실패가 아니라 "이미 예약됨"으로 보고 완료 화면으로 간다(동시 active 1건 — D-08).
- 좌석 선점(RSV-502/SYS-401): status='active' 부분 유니크 인덱스에 INSERT가 부딪히면
  IntegrityError → 409 SEAT_TAKEN. 애플리케이션 선(先)체크가 아니라 DB 제약이
  "정확히 한 명만 승자"를 보장하는 원자적 관문이다(SQLite 단일 writer 직렬화).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_device_id, raise_api
from app.models import Reservation, Seat, Verification
from app.reservations_core import expire_stale
from app.timeutil import today_kst_str

router = APIRouter()

# 예약 유효 시간 2시간(D-11). reserved_at + 이 값이 expires_at.
RESERVATION_TTL = timedelta(hours=2)


class ReserveRequest(BaseModel):
    # seat_id·verify_token은 필수. 누락 시 FastAPI가 422로 막는다(프론트 정상 경로엔 없음).
    seat_id: str
    verify_token: str


def _now_utc() -> datetime:
    # 저장은 UTC-naive(D-01: 판정은 KST, 저장은 UTC 통일). expire_stale와 같은 기준.
    # SYS-203(자정에 걸친 예약) 테스트가 시각을 주입할 수 있도록 함수로 분리한다.
    return datetime.utcnow()


def _seat_payload(seat: Seat) -> dict:
    # 예약 완료 화면(D-09)이 좌석을 그릴 수 있는 최소 정보. QR 토큰은 없다(D-09).
    return {
        "id": seat.id,
        "label": seat.label,
        "capacity": seat.capacity,
        "position_label": seat.position_label,
    }


@router.post("/api/reserve")
def create_reservation(
    body: ReserveRequest,
    db: Session = Depends(get_db),
    device_id: str = Depends(get_device_id),
):
    # 1) 토큰 검증(RSV-101/103/503). 두 실패를 코드로 구분한다(둘 다 401, 프론트는 /verify로):
    #    - 자격 자체가 없음(토큰 미존재) → TOKEN_NOT_FOUND (RSV-101/103: 직접 진입·자격 없음)
    #    - 자격이 낡음(존재하나 non-approved이거나 어제 발급) → TOKEN_EXPIRED (RSV-503: 만료 자격)
    verification = (
        db.query(Verification)
        .filter(Verification.token == body.verify_token)
        .first()
    )
    if verification is None:
        raise_api(401, "TOKEN_NOT_FOUND", "인증 정보가 없어요. 영수증으로 먼저 인증해주세요.")
    if (
        verification.status != "approved"
        or verification.verify_date != today_kst_str()
    ):
        # approved가 아니거나(rejected·감사 무효화) 당일이 아닌 토큰 = 낡은 자격.
        raise_api(401, "TOKEN_EXPIRED", "인증이 만료되었어요. 오늘 영수증으로 다시 인증해주세요.")

    # 만료 정리를 먼저 돌려야 (a) 이 토큰의 지난 예약이 expired로 정리돼 재예약이 열리고
    # (RSV-702), (b) 방금 만료된 좌석이 available이 된다(RSV-604). expire_stale는 commit한다.
    expire_stale(db)

    # 2) 멱등 관문(RSV-504/506/703/105). 이 토큰이 이미 active 예약을 쥐고 있으면
    #    새로 만들지 않고 기존 예약을 409 ALREADY_RESERVED + reservation_id로 돌려준다.
    existing = (
        db.query(Reservation)
        .filter(
            Reservation.verify_token == body.verify_token,
            Reservation.status == "active",
        )
        .first()
    )
    if existing is not None:
        # 에러 봉투에 reservation_id를 함께 실어야 프론트가 완료 화면으로 복구한다(RSV-506 📌).
        # ApiError는 code/message만 담으므로 여기서만 JSONResponse를 직접 만든다.
        return JSONResponse(
            status_code=409,
            content={
                "error": {"code": "ALREADY_RESERVED", "message": "이미 예약돼 있어요."},
                "reservation_id": existing.id,
            },
        )

    # 3) 좌석 존재 확인. 없는 좌석 id면 FK IntegrityError가 SEAT_TAKEN으로 오인되므로
    #    먼저 명시적으로 404를 낸다(정상 UI 경로엔 없는 경계 방어).
    seat = db.get(Seat, body.seat_id)
    if seat is None:
        raise_api(404, "SEAT_NOT_FOUND", "존재하지 않는 좌석이에요.")

    # 4) INSERT. 좌석당 active 1건 부분 유니크에 부딪히면 선점당한 것(RSV-502/SYS-401).
    now = _now_utc()
    reservation = Reservation(
        seat_id=seat.id,
        verify_token=body.verify_token,
        device_id=device_id,
        status="active",
        reserved_at=now,
        expires_at=now + RESERVATION_TTL,
    )
    db.add(reservation)
    try:
        db.commit()
    except IntegrityError:
        # 부분 유니크 위반 = 이미 누가 이 좌석을 선점. row는 만들어지지 않는다.
        db.rollback()
        raise_api(409, "SEAT_TAKEN", "아쉽지만 방금 다른 분이 먼저 예약했어요.")

    db.refresh(reservation)
    return {
        "reservation_id": reservation.id,
        "seat": _seat_payload(seat),
        "expires_at": reservation.expires_at.replace(tzinfo=timezone.utc).isoformat(),
    }
