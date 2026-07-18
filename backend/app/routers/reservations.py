"""내 예약 조회·자리 비우기 — GET/DELETE /api/reservations/{id} (RSV-601/602/801/802).

소유 검증(D-10, RSV-801/802): row의 device_id와 요청 헤더 X-Device-Id를 대조한다.
불일치면 403 FORBIDDEN — reservation_id를 추측·공유해도 남의 예약을 볼 수 없다.

만료 반영(D-11): 두 핸들러 모두 expire_stale를 먼저 돌려 lazy 만료를 반영한다.
따라서 카운트다운 0 도달 후 재조회(RSV-604)나 스윕 없이도 상태가 정확하다.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_device_id, raise_api
from app.models import Reservation, Seat
from app.reservations_core import expire_stale

router = APIRouter()


def _load_owned(db: Session, reservation_id: str, device_id: str) -> Reservation:
    """예약을 로드하고 소유 검증까지 마친 뒤 반환한다.

    - 없으면 404 NOT_FOUND(RSV-803: 프론트는 조용히 localStorage id를 지운다).
    - 타 기기면 403 FORBIDDEN(RSV-801/802). 존재는 하되 소유가 아님을 구분해 알린다.
    """
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise_api(404, "NOT_FOUND", "예약을 찾을 수 없어요.")
    if reservation.device_id != device_id:
        raise_api(403, "FORBIDDEN", "예약을 찾을 수 없어요.")
    return reservation


def _remaining_seconds(reservation: Reservation) -> int:
    # 남은 시간은 서버 expires_at 기준으로만 계산한다(클라이언트 시계 불신 — D-01).
    # active가 아니면 0. active여도 경계를 지났으면 음수 방지로 0으로 깎는다.
    if reservation.status != "active":
        return 0
    delta = (reservation.expires_at - datetime.utcnow()).total_seconds()
    return max(0, int(delta))


@router.get("/api/reservations/{reservation_id}")
def get_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    device_id: str = Depends(get_device_id),
) -> dict:
    # lazy 만료를 먼저 반영해야 지난 active가 expired로 정확히 보인다(RSV-604/SYS-101).
    expire_stale(db)
    reservation = _load_owned(db, reservation_id, device_id)
    db.refresh(reservation)

    seat = db.get(Seat, reservation.seat_id)
    return {
        "reservation_id": reservation.id,
        "status": reservation.status,  # active | expired | cancelled
        "seat": {
            "id": seat.id,
            "label": seat.label,
            "capacity": seat.capacity,
            "position_label": seat.position_label,
        },
        # expires_at은 naive UTC로 저장됨 → UTC-aware ISO(+00:00)로 내보내야 프론트가
        # 로컬 시간으로 오해하지 않는다. 표시는 프론트가 Asia/Seoul로 변환(D-01).
        "expires_at": reservation.expires_at.replace(tzinfo=timezone.utc).isoformat(),
        "remaining_seconds": _remaining_seconds(reservation),
    }


@router.delete("/api/reservations/{reservation_id}")
def cancel_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    device_id: str = Depends(get_device_id),
) -> dict:
    # 취소·만료 스윕 경합(RSV-606): 먼저 만료 정리를 돌린다. 그 사이 스윕이 expired로
    # 바꿨다면 아래에서 active가 아니게 되어 멱등 200으로 흘러간다(expired를 덮어쓰지 않음).
    expire_stale(db)
    reservation = _load_owned(db, reservation_id, device_id)
    db.refresh(reservation)

    # active만 cancelled로 전환. 이미 expired/cancelled면 그대로 두고 멱등 200(RSV-606).
    # cancelled로 바꾸는 순간 좌석의 active 예약이 사라져 좌석이 즉시 available이 된다.
    if reservation.status == "active":
        reservation.status = "cancelled"
        db.commit()
        db.refresh(reservation)

    return {"reservation_id": reservation.id, "status": reservation.status}
