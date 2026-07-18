"""GET /api/shops 시나리오 테스트 — MENU-301/302/303.

백엔드 검증 대상:
- is_active=true 상점만, sort_order 오름차순으로 반환 (MENU-301)
- is_active=false 상점 제외
- 활성 상점 0개면 빈 배열(깨끗한 응답) — MENU-303 빈 목록 처리의 서버 측

프론트 전용(여기서 테스트 안 함): 상위 3개 배지 + "+n개" 텍스트,
skeleton, "참여 상점을 준비 중이에요"/"불러오지 못했어요" 폴백 문구,
in-flight 이탈 무시(MENU-304/305/306). 서버는 정렬된 활성 목록만 내려준다.
"""

from app.models import Shop


def test_shops_lists_active_sorted_by_sort_order(client, db_session):
    # MENU-301: 시드 2개(막걸리계보 sort 1, 조준영 sort 2) + 신규 1개를 섞은 정렬 검증.
    # sort_order를 일부러 뒤섞어 넣고, 응답이 오름차순으로 정렬돼 나오는지 본다.
    db_session.add(Shop(id="cafe-a", name="카페 가", category="cafe", sort_order=0, is_active=True))
    db_session.commit()

    resp = client.get("/api/shops")
    assert resp.status_code == 200
    body = resp.json()

    assert [s["sort_order"] for s in body] == sorted(s["sort_order"] for s in body)
    assert [s["id"] for s in body] == ["cafe-a", "makgeolli-gyebo", "jojunyoung"]
    # 응답 필드: id/name/category/sort_order.
    first = body[0]
    assert set(first.keys()) == {"id", "name", "category", "sort_order"}


def test_shops_excludes_inactive(client, db_session):
    # is_active=false 상점은 목록에서 빠진다.
    db_session.add(
        Shop(id="hidden", name="숨김 상점", category="cafe", sort_order=5, is_active=False)
    )
    db_session.commit()

    body = client.get("/api/shops").json()
    ids = {s["id"] for s in body}
    assert "hidden" not in ids
    # 시드 활성 2개는 그대로 노출.
    assert ids == {"makgeolli-gyebo", "jojunyoung"}


def test_shops_empty_when_none_active(client, db_session):
    # MENU-303 서버 측: 활성 상점이 없으면 빈 배열을 깨끗하게 반환한다(200 + []).
    for shop in db_session.query(Shop).all():
        shop.is_active = False
    db_session.commit()

    resp = client.get("/api/shops")
    assert resp.status_code == 200
    assert resp.json() == []
