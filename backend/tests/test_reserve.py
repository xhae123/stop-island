"""POST /api/reserve · GET/DELETE /api/reservations/{id} — RSV/SYS 예약 시나리오.

각 테스트는 시나리오 파일(04-reserve.md, 07-system.md)의 Given/When/Then을 그대로
옮긴 것이다. Given은 DB 배치(db_session)로, When은 HTTP 호출(client)로, Then은
응답 코드·본문·DB 상태로 검증한다.
"""

from datetime import datetime, timedelta

from app.models import Reservation, Verification
from app.timeutil import kst_day_of, today_kst_str
from tests.conftest import DEFAULT_DEVICE_ID


# --- 배치 헬퍼 -------------------------------------------------------------


def _approve_token(
    db,
    token: str,
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    verify_date: str | None = None,
) -> str:
    """approved 인증 row를 만들어 예약에 쓸 토큰을 발급한다(FK 선행 조건).

    verify_date를 주지 않으면 오늘(KST) — 당일 유효 토큰. 어제 날짜를 주면 만료 토큰.
    """
    db.add(
        Verification(
            device_id=device_id,
            method="manual",
            status="approved",
            needs_audit=True,
            token=token,
            verify_date=verify_date or today_kst_str(),
            verified_at=datetime.utcnow(),
        )
    )
    db.commit()
    return token


def _insert_active_reservation(
    db, seat_id: str, token: str, *, device_id: str, minutes: int = 120
) -> str:
    """서버를 거치지 않고 active 예약을 직접 심는다.

    minutes>0 → 미래 만료(active 유지), <0 → 과거 만료(스윕 대상). id를 반환한다.
    """
    now = datetime.utcnow()
    reservation = Reservation(
        seat_id=seat_id,
        verify_token=token,
        device_id=device_id,
        status="active",
        reserved_at=now,
        expires_at=now + timedelta(minutes=minutes),
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation.id


def _seat_of(client, seat_id: str) -> dict:
    rows = {row["id"]: row for row in client.get("/api/seats").json()}
    return rows[seat_id]


# --- RSV-501 예약 확정 성공 -------------------------------------------------


def test_reserve_success(client, db_session):
    # Given: a3가 선택 가능하고 당일 토큰이 유효하다.
    _approve_token(db_session, "tok-ok")

    # When: 예약을 확정한다.
    resp = client.post("/api/reserve", json={"seat_id": "a3", "verify_token": "tok-ok"})

    # Then: 200 + { reservation_id, seat, expires_at }. qr_token 없음(D-09).
    assert resp.status_code == 200
    body = resp.json()
    assert "reservation_id" in body
    assert body["seat"]["id"] == "a3"
    assert body["seat"]["capacity"] == 4
    assert body["seat"]["position_label"] == "창가 자리"
    assert "expires_at" in body
    assert "qr_token" not in body

    # 서버: reservations에 active row가 생겼고 device_id가 기록됐다(소유 검증 근거).
    row = db_session.query(Reservation).filter_by(seat_id="a3").one()
    assert row.status == "active"
    assert row.device_id == DEFAULT_DEVICE_ID
    assert row.verify_token == "tok-ok"

    # a3는 이제 taken으로 보인다.
    assert _seat_of(client, "a3")["status"] == "taken"


def test_reserve_expires_at_is_two_hours(client, db_session):
    # RSV-501(부분): expires_at = reserved_at + 2h(D-11).
    _approve_token(db_session, "tok-ttl")
    client.post("/api/reserve", json={"seat_id": "a1", "verify_token": "tok-ttl"})

    row = db_session.query(Reservation).filter_by(seat_id="a1").one()
    assert row.expires_at - row.reserved_at == timedelta(hours=2)


# --- RSV-502 / SYS-401 좌석 선점 충돌 ---------------------------------------


def test_reserve_seat_taken_conflict(client, db_session):
    # Given(SYS-401): 다른 사용자가 거의 동시에 a3를 먼저 확정한 상태를 경쟁 row로 재현한다.
    _approve_token(db_session, "tok-other", device_id="dev-other")
    _insert_active_reservation(db_session, "a3", "tok-other", device_id="dev-other")
    _approve_token(db_session, "tok-me")

    # When: 후순위인 내가 같은 a3를 확정한다.
    resp = client.post("/api/reserve", json={"seat_id": "a3", "verify_token": "tok-me"})

    # Then: 409 SEAT_TAKEN. 내 명의 row는 생기지 않는다(정확히 1건만 존재 — 부분 유니크).
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SEAT_TAKEN"
    active_a3 = (
        db_session.query(Reservation)
        .filter_by(seat_id="a3", status="active")
        .all()
    )
    assert len(active_a3) == 1
    assert active_a3[0].device_id == "dev-other"


# --- RSV-503 / SYS-201 / SYS-202 토큰 만료 ----------------------------------


def test_reserve_expired_token(client, db_session):
    # Given(RSV-503): 어제(KST) 발급된 토큰. 자정을 넘겨 확정을 시도한다.
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    _approve_token(db_session, "tok-old", verify_date=yesterday)

    resp = client.post("/api/reserve", json={"seat_id": "a1", "verify_token": "tok-old"})

    # Then: 401 TOKEN_EXPIRED. 좌석 점유 없음.
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TOKEN_EXPIRED"
    assert db_session.query(Reservation).count() == 0


def test_reserve_unknown_token(client, db_session):
    # RSV-101/103(서버측 가드): 존재하지 않는 토큰 = 자격 없음 → 401 TOKEN_NOT_FOUND.
    # (만료 자격 TOKEN_EXPIRED와 구분 — 낡은 자격이 아니라 자격 부재)
    resp = client.post(
        "/api/reserve", json={"seat_id": "a1", "verify_token": "does-not-exist"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TOKEN_NOT_FOUND"


def test_reserve_missing_device_header(raw_client, db_session):
    # SYS-302: X-Device-Id 헤더 없는 예약 요청은 400 DEVICE_ID_REQUIRED.
    _approve_token(db_session, "tok-nodev")
    resp = raw_client.post(
        "/api/reserve", json={"seat_id": "a1", "verify_token": "tok-nodev"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEVICE_ID_REQUIRED"


# --- RSV-504/505/506/703/105 멱등(더블탭·응답 유실·두 탭 충돌) -----------------


def test_reserve_idempotent_returns_same_reservation(client, db_session):
    # Given(RSV-504): 이미 a3를 확정한 상태.
    _approve_token(db_session, "tok-dup")
    first = client.post("/api/reserve", json={"seat_id": "a3", "verify_token": "tok-dup"})
    reservation_id = first.json()["reservation_id"]

    # When(RSV-506): 같은 토큰으로 다시 확정을 시도한다(더블탭·응답 유실 후 재시도).
    second = client.post(
        "/api/reserve", json={"seat_id": "a3", "verify_token": "tok-dup"}
    )

    # Then: 409 ALREADY_RESERVED + 기존 reservation_id. 중복 row 없음.
    assert second.status_code == 409
    body = second.json()
    assert body["error"]["code"] == "ALREADY_RESERVED"
    assert body["reservation_id"] == reservation_id
    assert db_session.query(Reservation).count() == 1


def test_reserve_idempotent_ignores_requested_seat(client, db_session):
    # RSV-703: active 예약 보유 중 다른 좌석으로 재요청해도 새 좌석을 만들지 않고
    # 기존 예약을 돌려준다(동시 active 1건 — D-08).
    _approve_token(db_session, "tok-dup2")
    first = client.post("/api/reserve", json={"seat_id": "a1", "verify_token": "tok-dup2"})
    reservation_id = first.json()["reservation_id"]

    second = client.post(
        "/api/reserve", json={"seat_id": "b3", "verify_token": "tok-dup2"}
    )
    assert second.status_code == 409
    assert second.json()["reservation_id"] == reservation_id
    # b3에는 예약이 생기지 않았다.
    assert db_session.query(Reservation).filter_by(seat_id="b3").count() == 0


# --- RSV-602 자리 비우기 ----------------------------------------------------


def test_cancel_frees_seat(client, db_session):
    # Given(RSV-602): active 예약을 보고 있다.
    _approve_token(db_session, "tok-cancel")
    reservation_id = client.post(
        "/api/reserve", json={"seat_id": "a2", "verify_token": "tok-cancel"}
    ).json()["reservation_id"]
    assert _seat_of(client, "a2")["status"] == "taken"

    # When: 자리 비우기.
    resp = client.delete(f"/api/reservations/{reservation_id}")

    # Then: 200, status=cancelled. 좌석은 즉시 available.
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    db_session.expire_all()
    assert db_session.get(Reservation, reservation_id).status == "cancelled"
    assert _seat_of(client, "a2")["status"] == "available"


def test_cancel_is_idempotent_on_expired(client, db_session):
    # RSV-606: 취소 시점에 스윕이 먼저 expired로 바꿨어도 DELETE는 에러 없이 200,
    # 그리고 expired를 cancelled로 덮어쓰지 않는다.
    _approve_token(db_session, "tok-exp")
    reservation_id = _insert_active_reservation(
        db_session, "a1", "tok-exp", device_id=DEFAULT_DEVICE_ID, minutes=-1
    )

    resp = client.delete(f"/api/reservations/{reservation_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "expired"
    db_session.expire_all()
    assert db_session.get(Reservation, reservation_id).status == "expired"


# --- RSV-604 / SYS-101 / SYS-102 만료 스윕이 좌석을 비운다 --------------------


def test_expiry_sweep_flips_and_frees_seat(client, db_session):
    # Given(SYS-101): expires_at을 넘긴 active 예약 1건.
    _approve_token(db_session, "tok-stale")
    reservation_id = _insert_active_reservation(
        db_session, "b1", "tok-stale", device_id=DEFAULT_DEVICE_ID, minutes=-1
    )

    # When: 좌석 조회(lazy 만료)가 돈다.
    assert _seat_of(client, "b1")["status"] == "available"

    # Then: 예약은 expired, 좌석은 비었다.
    db_session.expire_all()
    assert db_session.get(Reservation, reservation_id).status == "expired"


def test_get_reservation_reflects_expiry(client, db_session):
    # RSV-604: 완료 화면 재조회 시 만료가 반영된다.
    _approve_token(db_session, "tok-expget")
    reservation_id = _insert_active_reservation(
        db_session, "a1", "tok-expget", device_id=DEFAULT_DEVICE_ID, minutes=-1
    )

    resp = client.get(f"/api/reservations/{reservation_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "expired"
    assert body["remaining_seconds"] == 0


# --- SYS-203 자정에 걸친 예약은 2시간 유지 ----------------------------------


def test_reserve_spanning_midnight_keeps_two_hours(client, db_session, monkeypatch):
    # Given: 예약 시각이 KST 자정 직전(23:59:00)이다. UTC로는 14:59:00.
    #        미래 날짜로 잡아 실시각 스윕에 걸리지 않게 한다.
    #        KST 23:59 = UTC 14:59 (KST는 UTC+9).
    import app.routers.reserve as reserve_module

    fixed_utc = datetime(2027, 12, 31, 14, 59, 0)  # = 2028-01-01 23:59 KST 직전 경계
    monkeypatch.setattr(reserve_module, "_now_utc", lambda: fixed_utc)

    _approve_token(db_session, "tok-mid")

    # When: 자정을 걸쳐 예약한다.
    resp = client.post("/api/reserve", json={"seat_id": "a1", "verify_token": "tok-mid"})
    assert resp.status_code == 200

    # Then: expires_at은 자정으로 잘리지 않고 정확히 +2h다.
    row = db_session.query(Reservation).filter_by(seat_id="a1").one()
    assert row.reserved_at == fixed_utc
    assert row.expires_at == fixed_utc + timedelta(hours=2)
    # 예약은 KST 자정을 실제로 넘겼다(23:59 시작 → 01:59 만료). 자정 컷 없이 2h 유지.
    assert kst_day_of(row.reserved_at) != kst_day_of(row.expires_at)


# --- RSV-701 / RSV-702 만료·취소 후 재예약 ----------------------------------


def test_re_reserve_after_cancel(client, db_session):
    # Given(RSV-701): 예약을 취소했고 토큰은 당일 유효.
    _approve_token(db_session, "tok-recycle")
    first_id = client.post(
        "/api/reserve", json={"seat_id": "a1", "verify_token": "tok-recycle"}
    ).json()["reservation_id"]
    client.delete(f"/api/reservations/{first_id}")

    # When: 같은 토큰으로 다시 예약한다(새 인증 불필요).
    resp = client.post(
        "/api/reserve", json={"seat_id": "a2", "verify_token": "tok-recycle"}
    )

    # Then: 성공. 이전 row는 cancelled로 남고 새 active row가 생긴다.
    assert resp.status_code == 200
    new_id = resp.json()["reservation_id"]
    assert new_id != first_id
    db_session.expire_all()
    assert db_session.get(Reservation, first_id).status == "cancelled"
    assert db_session.get(Reservation, new_id).status == "active"


def test_re_reserve_after_expiry(client, db_session):
    # RSV-702: 예약이 2시간 경과로 expired 처리된 뒤 같은 토큰으로 재예약.
    _approve_token(db_session, "tok-reexp")
    _insert_active_reservation(
        db_session, "a1", "tok-reexp", device_id=DEFAULT_DEVICE_ID, minutes=-1
    )

    # active 예약이 없으므로(만료됨) ALREADY_RESERVED에 걸리지 않고 성공.
    resp = client.post(
        "/api/reserve", json={"seat_id": "a2", "verify_token": "tok-reexp"}
    )
    assert resp.status_code == 200
    assert resp.json()["seat"]["id"] == "a2"


# --- RSV-801 / RSV-802 소유 검증 --------------------------------------------


def test_get_reservation_other_device_forbidden(client, db_session):
    # Given(RSV-801): 기기 A의 예약. 기기 B가 그 id를 추측했다.
    _approve_token(db_session, "tok-owner")
    reservation_id = client.post(
        "/api/reserve", json={"seat_id": "a1", "verify_token": "tok-owner"}
    ).json()["reservation_id"]

    # When: 기기 B(다른 X-Device-Id)가 조회한다.
    resp = client.get(
        f"/api/reservations/{reservation_id}", headers={"X-Device-Id": "device-b"}
    )

    # Then: 403 FORBIDDEN.
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_delete_reservation_other_device_forbidden(client, db_session):
    # RSV-802: 기기 B의 DELETE 시도는 403이고 기기 A의 예약은 active 유지.
    _approve_token(db_session, "tok-owner2")
    reservation_id = client.post(
        "/api/reserve", json={"seat_id": "a1", "verify_token": "tok-owner2"}
    ).json()["reservation_id"]

    resp = client.delete(
        f"/api/reservations/{reservation_id}", headers={"X-Device-Id": "device-b"}
    )
    assert resp.status_code == 403
    db_session.expire_all()
    assert db_session.get(Reservation, reservation_id).status == "active"


def test_get_reservation_not_found(client, db_session):
    # RSV-803: 서버에 없는 id 조회 → 404(프론트는 조용히 localStorage id를 지운다).
    resp = client.get("/api/reservations/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_get_reservation_active_shape(client, db_session):
    # RSV-601(백엔드측): 완료 화면이 그릴 필드를 GET이 채워 내려준다.
    _approve_token(db_session, "tok-shape")
    reservation_id = client.post(
        "/api/reserve", json={"seat_id": "a3", "verify_token": "tok-shape"}
    ).json()["reservation_id"]

    body = client.get(f"/api/reservations/{reservation_id}").json()
    assert body["status"] == "active"
    assert body["seat"]["label"] == "A3"
    assert body["seat"]["capacity"] == 4
    assert body["seat"]["position_label"] == "창가 자리"
    assert body["remaining_seconds"] > 0
    assert "expires_at" in body


def test_get_reservation_reflects_cancelled(client, db_session):
    # RSV-608(백엔드측): 감사 무효화/관리자 해제로 cancelled가 된 예약을 재조회하면
    # cancelled 상태가 그대로 내려온다(프론트는 "예약이 취소되었어요" 화면으로 전환).
    _approve_token(db_session, "tok-revoke")
    reservation_id = client.post(
        "/api/reserve", json={"seat_id": "a1", "verify_token": "tok-revoke"}
    ).json()["reservation_id"]

    # 관리자/감사 경로가 예약을 해제한 상황을 재현.
    db_session.get(Reservation, reservation_id).status = "cancelled"
    db_session.commit()

    body = client.get(f"/api/reservations/{reservation_id}").json()
    assert body["status"] == "cancelled"
    assert body["remaining_seconds"] == 0
