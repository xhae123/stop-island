"""방명록(guestbook) 라우터 — 05-guestbook.md(GB-*) + 결정표(D-17~D-19, D-24).

익명 게시판이라 device_id는 rate limit 판정에만 쓰고 저장하지 않는다(D-19).
- POST /api/guestbook : 본문(trim 후 1~500자, D-18) + 별점(1~5|null, D-17)
  + 맛집 태그(0~5개) 검증 후 게시. 같은 device_id는 1분 1회(D-19) — 초과 시 429.
- GET  /api/guestbook : created_at+id 복합 keyset 커서 무한스크롤(10개/페이지, DESC).
"""

import base64
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_device_id, raise_api
from app.models import GuestbookEntry, GuestbookShopTag, Shop

router = APIRouter()

# --- 검증 상수 (D-18) ---
_MAX_CONTENT_LEN = 500  # 본문 최대 길이(trim 후)
_MAX_TAGS = 5  # 맛집 태그 최대 개수

# --- Rate limit (D-19) ---
# 왜 모듈 전역 dict인가: 7일 팝업이라 별도 저장소(Redis 등)는 과설계.
# in-memory라 서버 재시작 시 초기화되지만, 익명 게시판의 최소 방어로는 충분하다.
# device_id → 마지막 게시 시각(epoch seconds). 테스트는 아래 _now 심(seam)을
# monkeypatch해서 실제 sleep 없이 윈도 경과를 시뮬레이션한다.
_RATE_WINDOW_SECONDS: float = 60.0
_last_post_at: dict[str, float] = {}


def _now() -> float:
    """현재 epoch 초. rate limit 판정의 시계 심 — 테스트에서 monkeypatch 대상."""
    return time.time()


class GuestbookCreate(BaseModel):
    """POST body. content는 필수, rating/shop_tags는 선택."""

    content: str
    rating: int | None = None
    shop_tags: list[str] = Field(default_factory=list)


def _encode_cursor(created_at: datetime, entry_id: str) -> str:
    """(created_at, id) keyset을 불투명 문자열로 인코딩한다.

    왜 keyset 커서인가(📌 05-guestbook GB-506): offset이 아니라 "마지막으로 본
    글보다 오래된 글"만 반환하므로, 스크롤 도중 새 글 추가·관리자 삭제가 있어도
    다음 페이지에 중복·누락이 생기지 않는다.
    """
    raw = f"{created_at.isoformat()}|{entry_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    """불투명 커서를 (created_at, id)로 되돌린다. 형식이 깨지면 400."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_at_str, entry_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(created_at_str), entry_id
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        raise_api(400, "INVALID_CURSOR", "잘못된 요청이에요. 새로고침 후 다시 시도해주세요.")
        raise  # unreachable — raise_api always raises. 타입 체커 만족용.


def _serialize_entry(
    entry: GuestbookEntry, tags: list[tuple[str, str]]
) -> dict[str, Any]:
    """엔트리 + 태그(shop_id, name 튜플 목록)를 응답 dict로 직렬화한다.

    태그는 상점명까지 join해서 내려준다 — 프론트 칩 렌더가 상점명을 필요로 하고,
    비활성 상점(is_active=false)도 이름은 유지해야 하기 때문(GB-602).
    """
    return {
        "id": entry.id,
        "content": entry.content,
        "rating": entry.rating,
        "shop_tags": [{"shop_id": sid, "name": name} for sid, name in tags],
        "created_at": entry.created_at.isoformat(),
    }


def _tags_for_entries(
    db: Session, entry_ids: list[str]
) -> dict[str, list[tuple[str, str]]]:
    """엔트리 id 목록에 대한 태그를 (shop_id, shop_name) 튜플로 한 번에 join 조회한다.

    is_active 필터 없이 join한다(GB-602 📌 결정): 태그는 작성 시점의 사실 기록이라
    상점이 이후 비활성화돼도 기존 글의 칩은 상점명 그대로 유지한다.
    """
    if not entry_ids:
        return {}
    rows = db.execute(
        select(GuestbookShopTag.entry_id, Shop.id, Shop.name)
        .join(Shop, Shop.id == GuestbookShopTag.shop_id)
        .where(GuestbookShopTag.entry_id.in_(entry_ids))
    ).all()
    result: dict[str, list[tuple[str, str]]] = {eid: [] for eid in entry_ids}
    for entry_id, shop_id, shop_name in rows:
        result[entry_id].append((shop_id, shop_name))
    return result


@router.post("/api/guestbook", status_code=201)
def create_guestbook_entry(
    body: GuestbookCreate,
    db: Session = Depends(get_db),
    device_id: str = Depends(get_device_id),
) -> dict[str, Any]:
    # 1) 본문 검증 (D-18): trim 후 1~500자.
    content = body.content.strip()
    if content == "":
        raise_api(400, "CONTENT_EMPTY", "내용을 입력해주세요.")
    if len(content) > _MAX_CONTENT_LEN:
        raise_api(400, "CONTENT_TOO_LONG", "500자까지 쓸 수 있어요.")

    # 2) 별점 검증 (D-17): 있으면 1~5. DB CHECK와 이중 방어(GB-204).
    if body.rating is not None and not (1 <= body.rating <= 5):
        raise_api(400, "INVALID_RATING", "별점은 1~5점만 줄 수 있어요.")

    # 3) 태그 검증 (D-18): 0~5개. 중복 제거하되 6개 초과면 거부(GB-303/GB-106).
    #    중복 제거 후에도 순서를 보존한다(dict.fromkeys).
    tag_ids = list(dict.fromkeys(body.shop_tags))
    if len(tag_ids) > _MAX_TAGS:
        raise_api(400, "TOO_MANY_TAGS", "맛집 태그는 5개까지 붙일 수 있어요.")
    # 존재하지 않는 shop_id는 무시한다(FK IntegrityError로 크래시하지 않도록).
    # 05 시나리오가 unknown 태그를 명시하지 않아, 조용히 걸러내는 관용 정책을 택한다.
    valid_shop_ids: set[str] = set(db.execute(select(Shop.id)).scalars().all())
    tag_ids = [sid for sid in tag_ids if sid in valid_shop_ids]

    # 4) Rate limit (D-19): 같은 device_id는 1분 1회. 검증을 통과한 뒤에 판정해야
    #    GB-106 검증 코드(400)가 rate limit(429)에 가려지지 않는다.
    last = _last_post_at.get(device_id)
    now = _now()
    if last is not None and (now - last) < _RATE_WINDOW_SECONDS:
        raise_api(429, "RATE_LIMITED", "잠시 후 다시 써주세요.")

    # 5) 삽입. entry + tags를 한 트랜잭션으로(GB-402: 5xx 시 부분 생성 금지).
    entry = GuestbookEntry(content=content, rating=body.rating)
    db.add(entry)
    db.flush()  # entry.id 확보
    for sid in tag_ids:
        db.add(GuestbookShopTag(entry_id=entry.id, shop_id=sid))
    db.commit()
    db.refresh(entry)

    # 6) 성공한 게시만 rate limit 윈도를 소비한다(실패 요청은 window 미소비).
    _last_post_at[device_id] = now

    tags = [(sid, name) for sid, name in _tags_for_entries(db, [entry.id])[entry.id]]
    return _serialize_entry(entry, tags)


@router.get("/api/guestbook")
def list_guestbook_entries(
    cursor: str | None = None,
    limit: int = 10,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # limit 방어: 1~50. 기본 10(05 시나리오). 커서 무관하게 페이지 크기 고정.
    limit = max(1, min(limit, 50))

    stmt = select(GuestbookEntry).order_by(
        GuestbookEntry.created_at.desc(), GuestbookEntry.id.desc()
    )
    if cursor is not None:
        c_created_at, c_id = _decode_cursor(cursor)
        # keyset 조건(DESC): 마지막으로 본 글보다 "오래된" 글만.
        # created_at이 같은 경우 id로 타이브레이크한다.
        stmt = stmt.where(
            (GuestbookEntry.created_at < c_created_at)
            | (
                (GuestbookEntry.created_at == c_created_at)
                & (GuestbookEntry.id < c_id)
            )
        )

    # limit+1 조회로 다음 페이지 존재 여부를 판정한다.
    rows = db.execute(stmt.limit(limit + 1)).scalars().all()
    has_more = len(rows) > limit
    page = rows[:limit]

    tags_by_entry = _tags_for_entries(db, [e.id for e in page])
    entries = [_serialize_entry(e, tags_by_entry.get(e.id, [])) for e in page]

    next_cursor: str | None = None
    if has_more and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return {"entries": entries, "next_cursor": next_cursor}
