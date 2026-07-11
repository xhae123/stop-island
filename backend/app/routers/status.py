from fastapi import APIRouter

router = APIRouter()


@router.get("/api/status")
def get_status():
    # TODO: seats + reservations 기반 실계산 (open seats - active reservations)
    return {
        "total_seats": 6,
        "open_seats": 6,
        "available_seats": 4,
        "visitor_count": 0,
    }
