"""GET /api/status 시나리오 테스트 — MAIN-201/202/203 + D-20.

백엔드 검증 대상:
- available_seats = count_available(db) (MAIN-201/202)
- is_full = is_full(db) (MAIN-203 만석 판정)
- today_visitors = 당일(KST) approved 인증 수 (D-20)

프론트 전용(여기서 테스트 안 함): 30초 폴링 주기·skeleton/"—" 로딩 표시,
에러 인디케이터, unmount 정리, visibilitychange/online 재조회, CTA 활성 유지 등
렌더링·타이밍 동작(MAIN-204~208, 501~505). 서버는 값만 정확히 내려주면 된다.
"""

from datetime import datetime, timedelta

from app.models import Reservation, Seat, Verification
from app.timeutil import now_kst

DEVICE = "test-device"


def _approve(db, *, device_id: str, verify_date: str, token: str | None = None) -> None:
    # 당일/특정일 approved 인증 1건. D-06 부분 유니크(device_id+verify_date)를
    # 피하려고 approved 여러 건이 필요하면 device_id를 서로 다르게 준다.
    db.add(
        Verification(
            device_id=device_id,
            method="manual",
            status="approved",
            needs_audit=True,
            token=token,
            verify_date=verify_date,
            verified_at=datetime.utcnow(),
        )
    )
    db.commit()


def _reject(db, *, device_id: str, verify_date: str) -> None:
    # 실패 인증도 row로 남지만 방문 수(D-20)에는 포함되면 안 된다.
    db.add(
        Verification(
            device_id=device_id,
            method="photo",
            status="rejected",
            reason_code="NOT_TODAY",
            verify_date=verify_date,
        )
    )
    db.commit()


def _reserve_seat(db, seat_id: str) -> None:
    # 좌석 하나를 active 예약으로 점유한다. verify_token FK가 있어 토큰 인증이 선행돼야 한다.
    # device_id를 좌석별로 달리해 D-06 approved 부분 유니크(device_id+verify_date)를 피한다.
    device_id = f"{DEVICE}-{seat_id}"
    token = f"tok-{seat_id}"
    _approve(db, device_id=device_id, verify_date="2000-01-01", token=token)
    now = datetime.utcnow()
    db.add(
        Reservation(
            seat_id=seat_id,
            verify_token=token,
            device_id=device_id,
            status="active",
            reserved_at=now,
            expires_at=now + timedelta(hours=2),
        )
    )
    db.commit()


# --- available_seats / is_full (MAIN-201/202/203) ---


def test_status_shape_and_defaults(client):
    # MAIN-201: 응답은 정확히 세 키. 시드 상태(좌석 6·예약 0·인증 0)에서 만석 아님.
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"available_seats", "today_visitors", "is_full"}
    assert body["available_seats"] == 6
    assert body["is_full"] is False
    assert body["today_visitors"] == 0


def test_available_seats_reflects_active_reservation(client, db_session):
    # MAIN-202: active 예약이 생기면 빈자리가 줄어든다(seat_status 반영).
    _reserve_seat(db_session, "a1")
    body = client.get("/api/status").json()
    assert body["available_seats"] == 5
    assert body["is_full"] is False


def test_is_full_true_when_all_seats_taken(client, db_session):
    # MAIN-203: 6석 모두 점유되면 available 0 · is_full True.
    for seat_id in ("a1", "a2", "a3", "b1", "b2", "b3"):
        _reserve_seat(db_session, seat_id)
    body = client.get("/api/status").json()
    assert body["available_seats"] == 0
    assert body["is_full"] is True


def test_is_full_true_when_all_seats_closed(client, db_session):
    # MAIN-203 경계: 좌석이 전부 닫혀도(is_open=False) available 0 · is_full True.
    for seat in db_session.query(Seat).all():
        seat.is_open = False
    db_session.commit()
    body = client.get("/api/status").json()
    assert body["available_seats"] == 0
    assert body["is_full"] is True


# --- today_visitors = 당일 approved 수 (D-20) ---


def test_today_visitors_counts_only_today_approved(client, db_session):
    # D-20: 오늘 approved만 센다. 어제 approved·오늘 rejected는 제외.
    today = now_kst().strftime("%Y-%m-%d")
    yesterday = (now_kst() - timedelta(days=1)).strftime("%Y-%m-%d")

    _approve(db_session, device_id="dev-today", verify_date=today)
    _approve(db_session, device_id="dev-yesterday", verify_date=yesterday)
    _reject(db_session, device_id="dev-rejected", verify_date=today)

    body = client.get("/api/status").json()
    # 오늘 approved 1건만 카운트.
    assert body["today_visitors"] == 1


def test_today_visitors_counts_multiple_today_approved(client, db_session):
    # 서로 다른 device_id의 오늘 approved는 각각 방문 1로 누적된다.
    today = now_kst().strftime("%Y-%m-%d")
    _approve(db_session, device_id="dev-1", verify_date=today)
    _approve(db_session, device_id="dev-2", verify_date=today)
    _approve(db_session, device_id="dev-3", verify_date=today)

    body = client.get("/api/status").json()
    assert body["today_visitors"] == 3
