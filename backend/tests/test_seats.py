"""GET /api/seats — 좌석 현황 표시 (RSV-201/202/203).

seat_status의 순수 로직은 스모크에서 검증됐고, 여기선 HTTP 엔드포인트가
그 상태를 available|taken|closed 3종으로 정확히 내보내는지 확인한다.
"""

from datetime import datetime, timedelta

from app.models import Reservation, Seat, Verification
from app.timeutil import today_kst_str


def _approve_token(db, token: str, device_id: str) -> None:
    # 예약 row는 verify_token FK가 있어(PRAGMA foreign_keys=ON) 승인 인증이 선행돼야 한다.
    db.add(
        Verification(
            device_id=device_id,
            method="manual",
            status="approved",
            needs_audit=True,
            token=token,
            verify_date=today_kst_str(),
            verified_at=datetime.utcnow(),
        )
    )
    db.commit()


def _reserve(db, seat_id: str, token: str, device_id: str, *, minutes: int = 120) -> None:
    now = datetime.utcnow()
    db.add(
        Reservation(
            seat_id=seat_id,
            verify_token=token,
            device_id=device_id,
            status="active",
            reserved_at=now,
            expires_at=now + timedelta(minutes=minutes),
        )
    )
    db.commit()


def _by_id(rows: list[dict]) -> dict[str, dict]:
    return {row["id"]: row for row in rows}


def test_seats_all_available_on_seed(client):
    # RSV-201(부분): 시드 직후 6석 전부 available. 그리드 기본 상태.
    resp = client.get("/api/seats")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 6
    assert all(row["status"] == "available" for row in rows)


def test_seats_mixed_states(client, db_session):
    # RSV-201: A1 taken(active 예약), B2 closed(is_open=false), 나머지 available.
    _approve_token(db_session, "tok-a1", "dev-a1")
    _reserve(db_session, "a1", "tok-a1", "dev-a1")
    db_session.get(Seat, "b2").is_open = False
    db_session.commit()

    rows = _by_id(client.get("/api/seats").json())
    assert rows["a1"]["status"] == "taken"
    assert rows["b2"]["status"] == "closed"
    assert rows["a2"]["status"] == "available"
    assert rows["a3"]["status"] == "available"
    # a3는 4인석 + 창가 라벨이 그대로 실려야 완료/선택 화면이 그린다.
    assert rows["a3"]["capacity"] == 4
    assert rows["a3"]["position_label"] == "창가 자리"


def test_seats_all_taken_is_full(client, db_session):
    # RSV-202: 6석 전부 active 예약이면 전 좌석 taken(만석). 서버는 상태만 내리고
    # 만석 안내 문구는 프론트가 붙인다.
    seats = ["a1", "a2", "a3", "b1", "b2", "b3"]
    for seat_id in seats:
        token = f"tok-{seat_id}"
        _approve_token(db_session, token, f"dev-{seat_id}")
        _reserve(db_session, seat_id, token, f"dev-{seat_id}")

    rows = client.get("/api/seats").json()
    assert all(row["status"] == "taken" for row in rows)


def test_seats_only_closed_seat_left_counts_as_full(client, db_session):
    # RSV-203(경계): 빈 좌석이 1석 있으나 is_open=false면 available이 0.
    # 5석 taken + 1석 closed → 예약 가능 0 = 만석과 동일 취급.
    taken = ["a1", "a2", "a3", "b1", "b2"]
    for seat_id in taken:
        token = f"tok-{seat_id}"
        _approve_token(db_session, token, f"dev-{seat_id}")
        _reserve(db_session, seat_id, token, f"dev-{seat_id}")
    db_session.get(Seat, "b3").is_open = False
    db_session.commit()

    rows = _by_id(client.get("/api/seats").json())
    assert rows["b3"]["status"] == "closed"
    available = [r for r in rows.values() if r["status"] == "available"]
    assert available == []
