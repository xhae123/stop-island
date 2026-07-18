"""초기 시드 데이터 — 좌석 6개 + 예시 상점.

멱등(idempotent): 이미 존재하는 row는 건너뛴다. 앱 부트·테스트 셋업에서 안전하게 반복 호출 가능.
상점은 예시값(실제 데이터는 8월 확정). 좌석은 A1~B3 6개(A3/B3만 4인).
"""

from sqlalchemy.orm import Session

from app.models import Seat, Shop

# (id, label, capacity, position_label)
_SEATS: list[tuple[str, str, int, str | None]] = [
    ("a1", "A1", 2, None),
    ("a2", "A2", 2, None),
    ("a3", "A3", 4, "창가 자리"),
    ("b1", "B1", 2, None),
    ("b2", "B2", 2, None),
    ("b3", "B3", 4, None),
]

# (id, name, category, sort_order)
_SHOPS: list[tuple[str, str, str, int]] = [
    ("makgeolli-gyebo", "막걸리계보", "bar", 1),
    ("jojunyoung", "조준영 목공방", "craft", 2),
]


def seed(db: Session) -> None:
    """좌석·상점 시드를 멱등하게 삽입한다. 이미 있는 id는 스킵."""
    for seat_id, label, capacity, position_label in _SEATS:
        if db.get(Seat, seat_id) is None:
            db.add(
                Seat(
                    id=seat_id,
                    label=label,
                    capacity=capacity,
                    position_label=position_label,
                )
            )

    for shop_id, name, category, sort_order in _SHOPS:
        if db.get(Shop, shop_id) is None:
            db.add(
                Shop(
                    id=shop_id,
                    name=name,
                    category=category,
                    sort_order=sort_order,
                )
            )

    db.commit()
