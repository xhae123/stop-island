"""관리자 원격 모니터링 테스트 — 06-admin.md(ADM-*) + 결정표(D-21, D-22, D-24).

TDD: 시나리오의 Given/When/Then을 먼저 테스트로 옮기고, admin.py/adminauth.py를
green이 될 때까지 구현한다.

세션 저장소(app.adminauth._sessions)는 모듈 전역이라 conftest의 DB 리셋과 무관하게
살아남는다. 매 테스트가 새 TestClient(=새 쿠키 항아리)를 쓰므로 이전 테스트의 세션
토큰이 흘러들지 않지만, 방어적으로 autouse 픽스처에서 비워 준다.
"""

from datetime import datetime, timedelta

import pytest

import app.adminauth as adminauth
from app.models import (
    GuestbookEntry,
    GuestbookShopTag,
    Reservation,
    Shop,
    Verification,
)
from app.timeutil import today_kst_str

# --- 테스트 상수 ---
_ADMIN_PASSWORD = "test-admin-pw"


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    # 비밀번호는 env에서만 온다(레포에 시크릿 금지). 테스트가 값을 주입한다.
    monkeypatch.setenv("ADMIN_PASSWORD", _ADMIN_PASSWORD)
    # 세션 저장소를 비워 테스트 간 누수를 막는다.
    adminauth._sessions.clear()
    yield
    adminauth._sessions.clear()


# ---------------------------------------------------------------------------
# arrange 헬퍼
# ---------------------------------------------------------------------------
_device_counter = [0]


def _next_device_id() -> str:
    # D-06 부분 유니크(device_id, verify_date)를 피하려고 매 인증마다 다른 device를 쓴다.
    _device_counter[0] += 1
    return f"dev-{_device_counter[0]}"


def _make_verification(
    db,
    *,
    device_id=None,
    status="approved",
    needs_audit=False,
    audited_at=None,
    token=None,
    method="photo",
    reason_code=None,
    verify_date=None,
    created_at=None,
    shop_id="makgeolli-gyebo",
    image_url="uploads/2026-07-18/x.jpg",
    ocr_store_name="막걸리계보",
    confidence=0.5,
) -> Verification:
    v = Verification(
        device_id=device_id or _next_device_id(),
        method=method,
        status=status,
        needs_audit=needs_audit,
        audited_at=audited_at,
        reason_code=reason_code,
        token=token,
        shop_id=shop_id,
        image_url=image_url,
        ocr_store_name=ocr_store_name,
        ocr_date="2026-07-18",
        confidence=confidence,
        verify_date=verify_date or today_kst_str(),
        verified_at=datetime.utcnow(),
        created_at=created_at or datetime.utcnow(),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _add_reservation(db, seat_id, token, *, minutes=120, device_id="test-device"):
    now = datetime.utcnow()
    r = Reservation(
        seat_id=seat_id,
        verify_token=token,
        device_id=device_id,
        status="active",
        reserved_at=now,
        expires_at=now + timedelta(minutes=minutes),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _login(client, password=_ADMIN_PASSWORD):
    return client.post("/api/admin/login", json={"password": password})


# 세션 없이 호출하면 401이어야 하는 모든 보호 라우트 (메서드, 경로).
_PROTECTED_ROUTES = [
    ("get", "/api/admin/audit"),
    ("post", "/api/admin/verifications/x/ok"),
    ("post", "/api/admin/verifications/x/revoke"),
    ("patch", "/api/admin/seats/a1"),
    ("get", "/api/admin/reservations"),
    ("delete", "/api/admin/reservations/x"),
    ("delete", "/api/admin/guestbook/x"),
    ("get", "/api/admin/shops"),
    ("post", "/api/admin/shops"),
    ("patch", "/api/admin/shops/makgeolli-gyebo"),
    ("get", "/api/admin/stats"),
]


# ---------------------------------------------------------------------------
# 로그인 / 세션 (ADM-1xx)
# ---------------------------------------------------------------------------
def test_login_success_sets_cookie_and_unlocks(client):
    # ADM-101: 올바른 비밀번호 → 200 + HttpOnly 세션 쿠키. 이후 관리자 API 접근 가능.
    resp = _login(client)
    assert resp.status_code == 200
    assert "admin_session" in resp.cookies
    # 쿠키가 실린 뒤 보호 라우트가 열린다.
    assert client.get("/api/admin/stats").status_code == 200


def test_login_wrong_password_401(client):
    # ADM-102: 틀린 비밀번호 → 401 INVALID_PASSWORD(D-24 봉투).
    resp = _login(client, password="nope")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_PASSWORD"
    assert "admin_session" not in resp.cookies


@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
def test_admin_routes_require_session(client, method, path):
    # ADM-105: 세션 쿠키 없이 관리자 API 호출 → 401 ADMIN_UNAUTHORIZED. 데이터 안 내려감.
    resp = getattr(client, method)(path)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "ADMIN_UNAUTHORIZED"


def test_session_survives_refresh(client):
    # ADM-107: 로그인 후 재요청(새로고침 상당)에도 쿠키가 살아 있어 재로그인 불필요.
    _login(client)
    assert client.get("/api/admin/stats").status_code == 200
    assert client.get("/api/admin/stats").status_code == 200


def test_two_admins_independent_sessions(client, raw_client):
    # ADM-106: 두 기기가 각자 로그인 → 서로 다른 세션 토큰, 상호 무효화 없음.
    r1 = _login(client)
    raw_client.headers.update({"X-Device-Id": "device-2"})
    r2 = _login(raw_client)
    assert r1.status_code == r2.status_code == 200
    assert r1.cookies["admin_session"] != r2.cookies["admin_session"]
    assert client.get("/api/admin/stats").status_code == 200
    assert raw_client.get("/api/admin/stats").status_code == 200


def test_expired_session_rejected(client):
    # ADM-104: 12시간 경과 세션 → 401 ADMIN_UNAUTHORIZED, 저장소에서 제거된다.
    _login(client)
    token = client.cookies["admin_session"]
    # 만료 시각을 과거로 밀어 만료를 시뮬레이션한다.
    adminauth._sessions[token] = datetime.utcnow() - timedelta(seconds=1)
    resp = client.get("/api/admin/stats")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "ADMIN_UNAUTHORIZED"
    assert token not in adminauth._sessions  # 만료 세션 제거


# ---------------------------------------------------------------------------
# 감사 큐 (ADM-2xx)
# ---------------------------------------------------------------------------
def test_audit_queue_lists_only_needs_audit_unaudited(client, db_session):
    # ADM-201/202: needs_audit=1 AND audited_at IS NULL 건만, 오래된 순으로.
    base = datetime(2026, 7, 18, 1, 0, 0)
    # 대상 3건 (created_at 다르게 — 정렬 확인)
    _make_verification(
        db_session, token="t1", needs_audit=True,
        reason_code="LOW_CONFIDENCE", created_at=base + timedelta(minutes=2),
    )
    _make_verification(
        db_session, token="t2", needs_audit=True,
        reason_code="MANUAL_SHOP_SELECTED", method="manual",
        created_at=base + timedelta(minutes=1),
    )
    _make_verification(
        db_session, token="t3", needs_audit=True,
        reason_code="SHOP_MATCH_UNCERTAIN", created_at=base + timedelta(minutes=3),
    )
    # 제외 대상: 이미 감사됨 / 감사 불필요 / rejected
    _make_verification(
        db_session, token="t4", needs_audit=True,
        audited_at=datetime.utcnow(), created_at=base,
    )
    _make_verification(db_session, token="t5", needs_audit=False, created_at=base)

    _login(client)
    resp = client.get("/api/admin/audit")
    assert resp.status_code == 200
    items = resp.json()["items"] if isinstance(resp.json(), dict) else resp.json()
    tokens = [it["reason_code"] for it in items]
    # 3건만, 오래된 순(t2=1분 → t1=2분 → t3=3분)
    assert tokens == ["MANUAL_SHOP_SELECTED", "LOW_CONFIDENCE", "SHOP_MATCH_UNCERTAIN"]
    # 감사에 필요한 필드가 실려 있다.
    first = items[0]
    for key in ("id", "image_url", "ocr_store_name", "confidence", "reason_code", "method"):
        assert key in first


def test_audit_queue_shows_linked_reservation(client, db_session):
    # ADM-201: 연결된 active 예약의 좌석 라벨이 표시된다.
    _make_verification(db_session, token="tok-r", needs_audit=True)
    _add_reservation(db_session, "a1", "tok-r")
    _login(client)
    items = client.get("/api/admin/audit").json()["items"]
    assert items[0]["reservation"]["seat_label"] == "A1"


def test_audit_ok_marks_audited(client, db_session):
    # ADM-211: 문제없음 → needs_audit=0, audited_at 기록. status/token/예약 불변.
    v = _make_verification(db_session, token="tok-ok", needs_audit=True)
    _login(client)
    resp = client.post(f"/api/admin/verifications/{v.id}/ok")
    assert resp.status_code == 200

    db_session.expire_all()
    row = db_session.get(Verification, v.id)
    assert row.needs_audit is False
    assert row.audited_at is not None
    assert row.status == "approved"
    assert row.token == "tok-ok"
    # 큐에서 사라진다.
    assert client.get("/api/admin/audit").json()["items"] == []


def test_audit_revoke_rejects_and_cancels_reservation(client, db_session):
    # ADM-212: 무효화 → verification rejected+REVOKED_BY_AUDIT, 연결 active 예약 cancelled.
    v = _make_verification(db_session, token="tok-rv", needs_audit=True, method="manual")
    _add_reservation(db_session, "a1", "tok-rv")
    _login(client)
    resp = client.post(f"/api/admin/verifications/{v.id}/revoke")
    assert resp.status_code == 200

    db_session.expire_all()
    row = db_session.get(Verification, v.id)
    assert row.status == "rejected"
    assert row.reason_code == "REVOKED_BY_AUDIT"
    assert row.audited_at is not None
    res = db_session.query(Reservation).filter_by(verify_token="tok-rv").one()
    assert res.status == "cancelled"


def test_audit_revoke_idempotent_second_call_409(client, db_session):
    # ADM-214/215: 두 번째 무효화 → 409 ALREADY_PROCESSED, 예약 이중 해제 없음.
    v = _make_verification(db_session, token="tok-idem", needs_audit=True)
    _add_reservation(db_session, "a1", "tok-idem")
    _login(client)
    assert client.post(f"/api/admin/verifications/{v.id}/revoke").status_code == 200
    resp2 = client.post(f"/api/admin/verifications/{v.id}/revoke")
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "ALREADY_PROCESSED"
    # 예약은 여전히 cancelled 하나뿐 — 이중 효과 없음.
    db_session.expire_all()
    res = db_session.query(Reservation).filter_by(verify_token="tok-idem").all()
    assert len(res) == 1 and res[0].status == "cancelled"


def test_two_admin_race_single_effect(client, db_session):
    # ADM-213: A 문제없음, B 무효화가 순차 도착 → 먼저만 성공, 나중은 409. 뒤집기 없음.
    v = _make_verification(db_session, token="tok-race", needs_audit=True)
    _add_reservation(db_session, "a1", "tok-race")
    _login(client)
    r1 = client.post(f"/api/admin/verifications/{v.id}/ok")
    r2 = client.post(f"/api/admin/verifications/{v.id}/revoke")
    assert r1.status_code == 200
    assert r2.status_code == 409
    db_session.expire_all()
    row = db_session.get(Verification, v.id)
    # 먼저 처리된 '문제없음'만 반영 — 무효화로 뒤집히지 않는다.
    assert row.status == "approved"
    assert db_session.query(Reservation).filter_by(verify_token="tok-race").one().status == "active"


def test_audit_action_on_missing_404(client):
    # 존재하지 않는 verification → 404 NOT_FOUND.
    _login(client)
    assert client.post("/api/admin/verifications/nope/ok").status_code == 404


# ---------------------------------------------------------------------------
# 좌석 관리 (ADM-3xx)
# ---------------------------------------------------------------------------
def test_seat_toggle_close_and_open(client):
    # ADM-301/303: is_open 토글.
    _login(client)
    r = client.patch("/api/admin/seats/a1", json={"is_open": False})
    assert r.status_code == 200
    assert r.json()["is_open"] is False
    r2 = client.patch("/api/admin/seats/a1", json={"is_open": True})
    assert r2.json()["is_open"] is True


def test_seat_toggle_missing_404(client):
    _login(client)
    assert client.patch("/api/admin/seats/zz", json={"is_open": False}).status_code == 404


# ---------------------------------------------------------------------------
# 예약 관리 (ADM-4xx)
# ---------------------------------------------------------------------------
def test_manual_reservation_release_frees_seat(client, db_session):
    # ADM-402: active 예약 수동 해제 → cancelled(행 보존), 좌석 즉시 빈자리.
    _make_verification(db_session, token="tok-rel", needs_audit=False)
    res = _add_reservation(db_session, "a1", "tok-rel")
    _login(client)
    resp = client.delete(f"/api/admin/reservations/{res.id}")
    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(Reservation, res.id).status == "cancelled"


def test_release_non_active_409(client, db_session):
    # ADM-403: 이미 만료/취소된 예약 해제 시도 → 409 NOT_ACTIVE, 상태 불변.
    _make_verification(db_session, token="tok-exp", needs_audit=False)
    res = _add_reservation(db_session, "a1", "tok-exp")
    res.status = "expired"
    db_session.commit()
    _login(client)
    resp = client.delete(f"/api/admin/reservations/{res.id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "NOT_ACTIVE"
    db_session.expire_all()
    assert db_session.get(Reservation, res.id).status == "expired"


def test_release_missing_404(client):
    _login(client)
    assert client.delete("/api/admin/reservations/nope").status_code == 404


def test_active_reservations_list(client, db_session):
    # ADM-401: active만, expires_at 오름차순, 좌석 라벨 + verification method/needs_audit 포함.
    v_a = _make_verification(
        db_session, token="ta", needs_audit=True, method="manual", shop_id="makgeolli-gyebo",
    )
    v_b = _make_verification(db_session, token="tb", needs_audit=False, method="photo")
    v_c = _make_verification(db_session, token="tc", needs_audit=False, method="photo")
    # a1: 곧 만료(30분), a2: 나중 만료(90분) → 정렬상 a1이 먼저
    _add_reservation(db_session, "a2", "tb", minutes=90)
    _add_reservation(db_session, "a1", "ta", minutes=30)
    # 제외되어야 할 것: cancelled 예약
    cancelled = _add_reservation(db_session, "b1", "tc", minutes=60)
    cancelled.status = "cancelled"
    db_session.commit()

    _login(client)
    resp = client.get("/api/admin/reservations")
    assert resp.status_code == 200
    items = resp.json()["items"]
    # active 2건만, expires_at 오름차순(a1 먼저)
    assert [it["seat_id"] for it in items] == ["a1", "a2"]

    first = items[0]
    assert first["seat_label"] == "A1"
    assert first["capacity"] == 2
    assert first["method"] == "manual"
    assert first["shop_id"] == "makgeolli-gyebo"
    assert first["shop_name"] == "막걸리계보"
    assert first["needs_audit"] is True
    assert first["remaining_seconds"] > 0
    # device_id는 노출하지 않는다(프라이버시).
    assert "device_id" not in first

    assert items[1]["needs_audit"] is False


def test_active_reservations_empty(client):
    # ADM-401: 예약 없으면 빈 목록.
    _login(client)
    resp = client.get("/api/admin/reservations")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# 방명록 관리 (ADM-5xx)
# ---------------------------------------------------------------------------
def test_guestbook_delete_removes_entry_and_tags(client, db_session):
    # ADM-501: 삭제 → 엔트리 제거 + shop_tags ON DELETE CASCADE.
    entry = GuestbookEntry(content="부적절한 글", rating=3)
    db_session.add(entry)
    db_session.flush()
    db_session.add(GuestbookShopTag(entry_id=entry.id, shop_id="makgeolli-gyebo"))
    db_session.commit()
    entry_id = entry.id

    _login(client)
    resp = client.delete(f"/api/admin/guestbook/{entry_id}")
    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(GuestbookEntry, entry_id) is None
    tags = db_session.query(GuestbookShopTag).filter_by(entry_id=entry_id).all()
    assert tags == []


def test_guestbook_delete_missing_404(client):
    # ADM-502: 이미 삭제된 글 → 404 NOT_FOUND.
    _login(client)
    resp = client.delete("/api/admin/guestbook/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 상점 관리 (ADM-6xx)
# ---------------------------------------------------------------------------
def test_shop_create(client, db_session):
    # ADM-601: 상점 추가 → is_active=true 기본.
    _login(client)
    resp = client.post(
        "/api/admin/shops",
        json={"id": "cafe-haeng", "name": "행궁카페", "category": "cafe", "sort_order": 3},
    )
    assert resp.status_code == 201
    db_session.expire_all()
    shop = db_session.get(Shop, "cafe-haeng")
    assert shop is not None and shop.is_active is True


def test_shop_create_duplicate_409(client):
    # ADM-603: 중복 슬러그 → 409 SHOP_ID_TAKEN.
    _login(client)
    resp = client.post(
        "/api/admin/shops",
        json={"id": "makgeolli-gyebo", "name": "중복", "category": "bar"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SHOP_ID_TAKEN"


def test_shop_update_and_deactivate(client, db_session):
    # ADM-602/604: 이름/정렬 수정 + is_active=false 소프트 스위치.
    _login(client)
    resp = client.patch(
        "/api/admin/shops/makgeolli-gyebo",
        json={"name": "막걸리계보 본점", "is_active": False},
    )
    assert resp.status_code == 200
    db_session.expire_all()
    shop = db_session.get(Shop, "makgeolli-gyebo")
    assert shop.name == "막걸리계보 본점"
    assert shop.is_active is False


def test_shop_update_missing_404(client):
    _login(client)
    assert client.patch("/api/admin/shops/nope", json={"name": "x"}).status_code == 404


def test_admin_list_shops_includes_inactive(client, db_session):
    # 관리자 목록은 비활성 상점까지 전부 보여야 한다(공개 /api/shops는 활성만).
    # 왜 필요한가: 비활성 상점을 재활성화하려면 관리자가 그 상점을 볼 수 있어야 한다.
    db_session.get(Shop, "jojunyoung").is_active = False
    db_session.commit()
    _login(client)

    resp = client.get("/api/admin/shops")
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [s["id"] for s in items]
    # 시드 상점 2개가 모두(비활성 포함) 포함된다.
    assert "makgeolli-gyebo" in ids
    assert "jojunyoung" in ids
    inactive = next(s for s in items if s["id"] == "jojunyoung")
    assert inactive["is_active"] is False
    # sort_order 오름차순 정렬 + is_active 키 노출 확인.
    assert [s["id"] for s in items[:2]] == ["makgeolli-gyebo", "jojunyoung"]


def test_admin_list_shops_requires_session(client):
    # 세션 없이는 401(보호 라우트).
    assert client.get("/api/admin/shops").status_code == 401


# ---------------------------------------------------------------------------
# 당일 통계 (ADM-7xx)
# ---------------------------------------------------------------------------
def test_stats_counts_today_only(client, db_session):
    # ADM-701/702: 오늘(KST) approved만 방문자 수로 집계. 어제 건은 제외.
    today = today_kst_str()
    # 오늘 approved 2건(그중 미감사 1건), rejected 1건
    _make_verification(db_session, token="s1", status="approved", verify_date=today)
    _make_verification(
        db_session, token="s2", status="approved", needs_audit=True, verify_date=today,
    )
    _make_verification(
        db_session, token=None, status="rejected", verify_date=today, reason_code="NOT_TODAY",
    )
    # 어제 approved 1건 — 집계 제외
    _make_verification(db_session, token="s3", status="approved", verify_date="2000-01-01")

    _login(client)
    resp = client.get("/api/admin/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["today_visitors"] == 2  # 오늘 approved만 (D-20)
    assert data["verifications"]["approved"] == 2
    assert data["verifications"]["rejected"] == 1
    assert data["verifications"]["needs_audit"] == 1  # 미감사 큐 크기
    # 좌석 현황: 열린 좌석 6, 빈자리 6 (예약 없음)
    assert data["seats"]["open_total"] == 6
    assert data["seats"]["available"] == 6
