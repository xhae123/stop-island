"""좌석 현황 조회 — GET /api/seats (RSV-201/202/203).

좌석 상태 계산은 reservations_core.seat_status가 단일 진실이다. 이 라우터는
그 결과를 그대로 내보내기만 한다. seat_status는 응답 계산 전에 expire_stale를
호출해 만료(D-11)를 lazy 반영하므로, 방금 만료된 좌석도 available로 정확히 보인다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.reservations_core import seat_status

router = APIRouter()


@router.get("/api/seats")
def list_seats(db: Session = Depends(get_db)) -> list[dict]:
    # 좌석별 { id, label, capacity, position_label, status(available|taken|closed) }.
    # is_open=false는 'closed', active 예약 보유는 'taken', 나머지는 'available'.
    return seat_status(db)
