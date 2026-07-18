"""방명록 라우터 테스트 — 05-guestbook.md(GB-*) Given/When/Then 명세 기반 TDD.

커버 GB id: GB-101, GB-103, GB-104, GB-105, GB-106, GB-201, GB-203, GB-204,
GB-302, GB-303, GB-401, GB-403, GB-501, GB-502, GB-504, GB-505, GB-506, GB-601, GB-602.
(순수 프론트/로컬 UI 시나리오 — GB-102/107/202/301/304/305/402/404/405/503/507/508/603/604 —
는 서버 무관하거나 클라이언트 책임이라 백엔드 테스트 대상 아님. 상세는 리포트 참조.)
"""

from datetime import datetime, timedelta

import pytest

from app.models import GuestbookEntry, GuestbookShopTag, Shop
from app.routers import guestbook


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    # 왜 autouse: rate limit 맵은 모듈 전역이라 테스트 간 누수된다. 매 테스트 초기화.
    guestbook._last_post_at.clear()
    yield
    guestbook._last_post_at.clear()


def _add_shop(db, shop_id: str, name: str, *, is_active: bool = True, sort_order: int = 0):
    db.add(
        Shop(
            id=shop_id,
            name=name,
            category="cafe",
            is_active=is_active,
            sort_order=sort_order,
        )
    )
    db.commit()


def _add_entry(db, content: str, *, rating=None, created_at: datetime, entry_id=None):
    entry = GuestbookEntry(content=content, rating=rating, created_at=created_at)
    if entry_id is not None:
        entry.id = entry_id
    db.add(entry)
    db.commit()
    return entry


# --- 작성 폼 검증 (D-18) ---


def test_gb101_basic_post(client, db_session):
    # GB-101/GB-401 정상 게시 — content만으로 201, 엔트리 반환, row 생성.
    resp = client.post("/api/guestbook", json={"content": "오늘 여기서 쉬다 갑니다"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "오늘 여기서 쉬다 갑니다"
    assert data["rating"] is None
    assert data["shop_tags"] == []
    assert "id" in data and "created_at" in data
    assert db_session.query(GuestbookEntry).count() == 1


def test_gb103_whitespace_only_rejected(client, db_session):
    # GB-103 공백/줄바꿈만 → trim 후 0자 → 400 CONTENT_EMPTY, row 미생성.
    resp = client.post("/api/guestbook", json={"content": "   \n  "})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CONTENT_EMPTY"
    assert db_session.query(GuestbookEntry).count() == 0


def test_gb106_empty_content_rejected(client, db_session):
    # GB-106 빈 content 우회 POST → 400 CONTENT_EMPTY.
    resp = client.post("/api/guestbook", json={"content": ""})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CONTENT_EMPTY"
    assert db_session.query(GuestbookEntry).count() == 0


def test_gb104_exactly_500_chars_ok(client, db_session):
    # GB-104 경계: trim 후 정확히 500자 → 게시 성공.
    content = "가" * 500
    resp = client.post("/api/guestbook", json={"content": content})
    assert resp.status_code == 201
    assert len(resp.json()["content"]) == 500
    assert db_session.query(GuestbookEntry).count() == 1


def test_gb105_501_chars_rejected(client, db_session):
    # GB-105/GB-106 경계: 501자 → 400 CONTENT_TOO_LONG, row 미생성.
    content = "가" * 501
    resp = client.post("/api/guestbook", json={"content": content})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CONTENT_TOO_LONG"
    assert db_session.query(GuestbookEntry).count() == 0


# --- 별점 (D-17) ---


def test_gb201_post_with_rating(client, db_session):
    # GB-201 별점 저장.
    resp = client.post("/api/guestbook", json={"content": "국밥 최고", "rating": 4})
    assert resp.status_code == 201
    assert resp.json()["rating"] == 4
    entry = db_session.query(GuestbookEntry).one()
    assert entry.rating == 4


def test_gb203_rating_null_stored(client, db_session):
    # GB-203 경계: rating=null 명시 게시 → NULL 저장.
    resp = client.post("/api/guestbook", json={"content": "그냥 후기", "rating": None})
    assert resp.status_code == 201
    assert resp.json()["rating"] is None
    assert db_session.query(GuestbookEntry).one().rating is None


@pytest.mark.parametrize("bad_rating", [0, 7])
def test_gb204_rating_out_of_range_rejected(client, db_session, bad_rating):
    # GB-204 오류: 범위 밖 rating → 400 INVALID_RATING, row 미생성.
    resp = client.post(
        "/api/guestbook", json={"content": "테스트", "rating": bad_rating}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_RATING"
    assert db_session.query(GuestbookEntry).count() == 0


# --- 맛집 태그 ---


def test_gb302_post_with_tags(client, db_session):
    # GB-302 태그 포함 게시 → entries 1 + shop_tags row 생성, 응답에 상점명 join.
    resp = client.post(
        "/api/guestbook",
        json={"content": "여기 좋아요", "shop_tags": ["makgeolli-gyebo", "jojunyoung"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    tag_ids = {t["shop_id"] for t in data["shop_tags"]}
    tag_names = {t["name"] for t in data["shop_tags"]}
    assert tag_ids == {"makgeolli-gyebo", "jojunyoung"}
    assert "막걸리계보" in tag_names
    assert db_session.query(GuestbookShopTag).count() == 2


def test_gb303_sixth_tag_rejected(client, db_session):
    # GB-303/GB-106 경계: 태그 6개 → 400 TOO_MANY_TAGS, row 미생성.
    for i in range(4):  # 시드 2개 + 4개 = 6개 확보
        _add_shop(db_session, f"shop-{i}", f"상점{i}", sort_order=10 + i)
    six = ["makgeolli-gyebo", "jojunyoung", "shop-0", "shop-1", "shop-2", "shop-3"]
    resp = client.post("/api/guestbook", json={"content": "많이 태그", "shop_tags": six})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOO_MANY_TAGS"
    assert db_session.query(GuestbookEntry).count() == 0
    assert db_session.query(GuestbookShopTag).count() == 0


def test_five_tags_ok(client, db_session):
    # 경계 반대편: 정확히 5개는 허용.
    for i in range(3):
        _add_shop(db_session, f"shop-{i}", f"상점{i}", sort_order=10 + i)
    five = ["makgeolli-gyebo", "jojunyoung", "shop-0", "shop-1", "shop-2"]
    resp = client.post("/api/guestbook", json={"content": "딱 다섯", "shop_tags": five})
    assert resp.status_code == 201
    assert len(resp.json()["shop_tags"]) == 5


def test_unknown_shop_tag_ignored(client, db_session):
    # 존재하지 않는 shop_id는 조용히 무시(FK 크래시 방지) — 나머지 태그는 반영.
    resp = client.post(
        "/api/guestbook",
        json={"content": "하나만 유효", "shop_tags": ["makgeolli-gyebo", "does-not-exist"]},
    )
    assert resp.status_code == 201
    tag_ids = {t["shop_id"] for t in resp.json()["shop_tags"]}
    assert tag_ids == {"makgeolli-gyebo"}


# --- XSS / code injection (GB-601) ---


def test_gb601_code_injection_stored_as_text(client, db_session):
    # GB-601: 스크립트/HTML은 원문 그대로 저장·반환(서버 크래시·이스케이프 없음).
    payload = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    resp = client.post("/api/guestbook", json={"content": payload})
    assert resp.status_code == 201
    assert resp.json()["content"] == payload  # 원문 그대로
    assert db_session.query(GuestbookEntry).one().content == payload


# --- Rate limit (D-19) ---


def test_gb403_rate_limit_then_success_after_window(client, db_session, monkeypatch):
    # GB-403: 같은 device_id로 연속 게시 → 429. 윈도 경과 후 재시도 성공.
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(guestbook, "_now", lambda: fake_now["t"])

    first = client.post("/api/guestbook", json={"content": "첫 글"})
    assert first.status_code == 201

    # 40초 후 (윈도 60초 내) → 429 RATE_LIMITED, row 미생성.
    fake_now["t"] = 1040.0
    blocked = client.post("/api/guestbook", json={"content": "두 번째 글"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert db_session.query(GuestbookEntry).count() == 1

    # 61초 후 (윈도 경과) → 성공.
    fake_now["t"] = 1061.0
    ok = client.post("/api/guestbook", json={"content": "세 번째 글"})
    assert ok.status_code == 201
    assert db_session.query(GuestbookEntry).count() == 2


def test_rate_limit_is_per_device(client, db_session, monkeypatch):
    # GB-403 보강: rate limit은 device_id별로 독립. 다른 기기는 즉시 게시 가능.
    monkeypatch.setattr(guestbook, "_now", lambda: 500.0)
    a = client.post(
        "/api/guestbook", json={"content": "기기 A"}, headers={"X-Device-Id": "dev-a"}
    )
    b = client.post(
        "/api/guestbook", json={"content": "기기 B"}, headers={"X-Device-Id": "dev-b"}
    )
    assert a.status_code == 201
    assert b.status_code == 201
    # 같은 기기 A 재시도는 429.
    a2 = client.post(
        "/api/guestbook", json={"content": "기기 A 또"}, headers={"X-Device-Id": "dev-a"}
    )
    assert a2.status_code == 429


# --- 목록 조회 & 무한스크롤 ---


def test_gb502_empty_list(client, db_session):
    # GB-502 경계: 글 0건 → 빈 리스트 + next_cursor null.
    resp = client.get("/api/guestbook")
    assert resp.status_code == 200
    assert resp.json() == {"entries": [], "next_cursor": None}


def test_gb501_first_page(client, db_session):
    # GB-501: 23건 중 첫 10건 최신순 + non-null next_cursor.
    base = datetime(2026, 7, 18, 0, 0, 0)
    for i in range(23):
        _add_entry(db_session, f"글 {i}", created_at=base + timedelta(minutes=i))
    resp = client.get("/api/guestbook")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 10
    assert data["next_cursor"] is not None
    # 최신순(DESC): 가장 마지막에 만든 "글 22"가 맨 위.
    assert data["entries"][0]["content"] == "글 22"
    assert data["entries"][-1]["content"] == "글 13"


def test_gb504_second_page_via_cursor(client, db_session):
    # GB-504: cursor로 다음 페이지 → 11~20번째, 중복 없음.
    base = datetime(2026, 7, 18, 0, 0, 0)
    for i in range(23):
        _add_entry(db_session, f"글 {i}", created_at=base + timedelta(minutes=i))
    page1 = client.get("/api/guestbook").json()
    page2 = client.get(
        "/api/guestbook", params={"cursor": page1["next_cursor"]}
    ).json()
    assert len(page2["entries"]) == 10
    assert page2["entries"][0]["content"] == "글 12"
    page1_ids = {e["id"] for e in page1["entries"]}
    page2_ids = {e["id"] for e in page2["entries"]}
    assert page1_ids.isdisjoint(page2_ids)  # 중복 없음


def test_gb505_last_page_cursor_null(client, db_session):
    # GB-505 경계: 마지막 페이지 → 남은 3건 + next_cursor null.
    base = datetime(2026, 7, 18, 0, 0, 0)
    for i in range(23):
        _add_entry(db_session, f"글 {i}", created_at=base + timedelta(minutes=i))
    p1 = client.get("/api/guestbook").json()
    p2 = client.get("/api/guestbook", params={"cursor": p1["next_cursor"]}).json()
    p3 = client.get("/api/guestbook", params={"cursor": p2["next_cursor"]}).json()
    assert len(p3["entries"]) == 3
    assert p3["next_cursor"] is None


def test_gb506_cursor_stable_when_new_entries_arrive(client, db_session):
    # GB-506 동시성: 1페이지 조회 후 새 글이 앞에 추가돼도, keyset 커서는
    # "1페이지 마지막 글보다 오래된 글"만 반환 → 중복·누락 없이 11~20번째 로드.
    base = datetime(2026, 7, 18, 0, 0, 0)
    for i in range(20):
        _add_entry(db_session, f"글 {i}", created_at=base + timedelta(minutes=i))
    page1 = client.get("/api/guestbook").json()
    page1_ids = {e["id"] for e in page1["entries"]}

    # 스크롤 도중 다른 사용자가 새 글 2건 게시(더 최신 created_at).
    _add_entry(db_session, "새 글 A", created_at=base + timedelta(hours=1))
    _add_entry(db_session, "새 글 B", created_at=base + timedelta(hours=2))

    page2 = client.get(
        "/api/guestbook", params={"cursor": page1["next_cursor"]}
    ).json()
    page2_ids = {e["id"] for e in page2["entries"]}
    # 새 글은 page2에 끼어들지 않고, 기존 11~20번째만 온다.
    assert len(page2["entries"]) == 10
    assert page2_ids.isdisjoint(page1_ids)
    assert "새 글 A" not in [e["content"] for e in page2["entries"]]
    assert "새 글 B" not in [e["content"] for e in page2["entries"]]


def test_gb602_inactive_shop_tag_still_shown(client, db_session):
    # GB-602 경계: 태그된 상점이 이후 비활성화돼도 목록의 칩(상점명)은 유지.
    _add_shop(db_session, "cafe-a", "카페 A", is_active=True, sort_order=5)
    entry = _add_entry(
        db_session, "카페 A 태그 글", created_at=datetime(2026, 7, 18, 0, 0, 0)
    )
    db_session.add(GuestbookShopTag(entry_id=entry.id, shop_id="cafe-a"))
    db_session.commit()
    # 관리자가 카페 A 비활성화.
    shop = db_session.get(Shop, "cafe-a")
    shop.is_active = False
    db_session.commit()

    data = client.get("/api/guestbook").json()
    card = next(e for e in data["entries"] if e["id"] == entry.id)
    assert card["shop_tags"] == [{"shop_id": "cafe-a", "name": "카페 A"}]
