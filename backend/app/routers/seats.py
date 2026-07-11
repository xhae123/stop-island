from fastapi import APIRouter

router = APIRouter()


@router.get("/api/seats")
def list_seats():
    # TODO: seats + reservations 조인해서 좌석별 상태(available/taken/closed) 계산
    return [
        {"id": "a1", "label": "A1", "capacity": 2, "position_label": None, "status": "available"},
        {"id": "a2", "label": "A2", "capacity": 2, "position_label": None, "status": "available"},
        {"id": "a3", "label": "A3", "capacity": 4, "position_label": "창가 자리", "status": "available"},
        {"id": "b1", "label": "B1", "capacity": 2, "position_label": None, "status": "available"},
        {"id": "b2", "label": "B2", "capacity": 2, "position_label": None, "status": "available"},
        {"id": "b3", "label": "B3", "capacity": 4, "position_label": None, "status": "available"},
    ]
