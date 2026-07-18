"""GET /api/status — 메인 현황 카드용 (MAIN-201/202/203, D-13, D-20).

읽기 전용. 빈자리 수·만석 여부·오늘 방문 수를 한 번에 내려준다.
- available_seats / is_full: reservations_core가 lazy 만료(D-11)까지 반영해 계산.
- today_visitors: D-20 정의대로 "당일(KST) approved 인증 수".
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Verification
from app.reservations_core import count_available, is_full
from app.timeutil import today_kst_str

router = APIRouter()


@router.get("/api/status")
def get_status(db: Session = Depends(get_db)) -> dict[str, int | bool]:
    # count_available/is_full은 각각 expire_stale를 거쳐 만료 예약을 정리한 뒤 계산한다(D-11).
    available_seats = count_available(db)

    # D-20: 오늘 방문 수 = 당일(KST) approved 인증 수.
    # created_at(UTC)이 아니라 verify_date(KST 'YYYY-MM-DD')가 하루 경계 기준(D-01).
    # rejected·다른 날짜는 제외된다.
    today_visitors = (
        db.query(Verification)
        .filter(
            Verification.status == "approved",
            Verification.verify_date == today_kst_str(),
        )
        .count()
    )

    return {
        "available_seats": available_seats,
        "today_visitors": today_visitors,
        "is_full": is_full(db),
    }
