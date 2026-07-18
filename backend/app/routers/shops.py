"""GET /api/shops — 참여 상점 목록 (MENU-301).

읽기 전용. is_active=true 상점만 sort_order 오름차순으로 반환한다.
상위 3개 배지 + "+n개" 표기, 빈 목록/실패 폴백 문구는 프론트 책임(D 결정표·02-menu.md).
서버는 정렬된 활성 목록만 내려주고, 활성 상점이 없으면 빈 배열을 반환한다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Shop

router = APIRouter()


@router.get("/api/shops")
def list_shops(db: Session = Depends(get_db)) -> list[dict[str, str | int]]:
    shops = (
        db.query(Shop)
        .filter(Shop.is_active.is_(True))
        .order_by(Shop.sort_order)
        .all()
    )
    return [
        {
            "id": shop.id,
            "name": shop.name,
            "category": shop.category,
            "sort_order": shop.sort_order,
        }
        for shop in shops
    ]
