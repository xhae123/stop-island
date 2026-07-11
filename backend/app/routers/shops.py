from fastapi import APIRouter

router = APIRouter()


@router.get("/api/shops")
def list_shops():
    # TODO: shops 테이블에서 is_active=true, sort_order 정렬로 조회
    return [
        {"id": "makgeolli-gyebo", "name": "막걸리계보", "category": "bar", "sort_order": 1},
        {"id": "jojunyoung", "name": "조준영 목공방", "category": "craft", "sort_order": 2},
    ]
