from fastapi import APIRouter

router = APIRouter()


@router.post("/api/reserve")
def create_reservation():
    # TODO: verify_token 필수. 좌석 active reservation 중복 체크 (트랜잭션)
    # TODO: expires_at = reserved_at + 2시간
    return {"id": "dummy-reservation-id", "seat_id": "a1", "status": "active"}
