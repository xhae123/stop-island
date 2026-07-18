"""좌석/만료 공용 헬퍼 — seats·status·admin 라우터가 read-only로 쓴다.

예약 쓰기 경로(POST /api/reserve)는 reserve 라우터가 소유한다. 이 모듈은 조회 측:
좌석 상태 계산과 lazy 만료(D-11)만 담당한다.

만료 정책(D-11): expires_at을 지난 active 예약은 조회 시점에 'expired'로 정리한다.
따라서 좌석 상태를 읽는 모든 진입점은 expire_stale를 먼저 호출한다.
expire_stale가 commit하는 것은 의도된 동작 — 조회 경로라도 만료 정리는 영속되어야
status API의 빈자리 수가 정확해진다.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Reservation, Seat


def expire_stale(db: Session) -> int:
    """expires_at이 현재(UTC) 이전인 active 예약을 전부 'expired'로 전환하고 commit한다.

    반환값: 만료 처리된 예약 수. lazy 만료(D-11)의 실행 단위.
    """
    now = datetime.utcnow()
    stale = (
        db.query(Reservation)
        .filter(Reservation.status == "active", Reservation.expires_at < now)
        .all()
    )
    for reservation in stale:
        reservation.status = "expired"
    db.commit()
    return len(stale)


def active_reservation(db: Session, seat_id: str) -> Reservation | None:
    """해당 좌석의 현재 active 예약을 반환한다(없으면 None). 조회 전 만료 정리를 수행한다."""
    expire_stale(db)
    return (
        db.query(Reservation)
        .filter(Reservation.seat_id == seat_id, Reservation.status == "active")
        .first()
    )


def seat_status(db: Session) -> list[dict]:
    """좌석별 상태를 id 오름차순으로 반환한다. 조회 전 만료 정리를 수행한다.

    각 항목: { id, label, capacity, position_label, status }
    status: is_open=false면 'closed', active 예약 있으면 'taken', 아니면 'available'.
    """
    expire_stale(db)

    # active 예약 좌석 집합을 한 번에 모아 좌석 수(6개)만큼 개별 쿼리하지 않는다.
    active_seat_ids = {
        row.seat_id
        for row in db.query(Reservation.seat_id)
        .filter(Reservation.status == "active")
        .all()
    }

    result: list[dict] = []
    for seat in db.query(Seat).order_by(Seat.id).all():
        if not seat.is_open:
            status = "closed"
        elif seat.id in active_seat_ids:
            status = "taken"
        else:
            status = "available"
        result.append(
            {
                "id": seat.id,
                "label": seat.label,
                "capacity": seat.capacity,
                "position_label": seat.position_label,
                "status": status,
            }
        )
    return result


def count_available(db: Session) -> int:
    """상태가 'available'인 좌석 수. status API의 빈자리 수(D-13)에 쓰인다."""
    return sum(1 for seat in seat_status(db) if seat["status"] == "available")


def is_full(db: Session) -> bool:
    """빈자리가 0이면 True(D-13 만석 보조 문구용)."""
    return count_available(db) == 0
