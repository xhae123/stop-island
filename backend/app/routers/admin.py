from fastapi import APIRouter

router = APIRouter()


@router.get("/api/admin/verifications")
def list_pending_verifications():
    # TODO: status='pending' 목록 조회
    return []


@router.patch("/api/admin/verifications/{verification_id}")
def update_verification_status(verification_id: str):
    # TODO: status 승인/거부 처리 + token 발급 (승인 시)
    return {"id": verification_id, "status": "approved"}


@router.patch("/api/admin/seats/{seat_id}")
def update_seat(seat_id: str):
    # TODO: is_open 변경 (좌석 열기/닫기)
    return {"id": seat_id, "is_open": True}


@router.delete("/api/admin/reservations/{reservation_id}")
def cancel_reservation(reservation_id: str):
    # TODO: 예약 수동 해제 (status='cancelled')
    return {"id": reservation_id, "status": "cancelled"}


@router.delete("/api/admin/guestbook/{entry_id}")
def delete_guestbook_entry(entry_id: str):
    # TODO: 방명록 삭제
    return {"id": entry_id, "deleted": True}


@router.post("/api/admin/shops")
def create_shop():
    # TODO: 상점 추가
    return {"id": "dummy-shop-id"}


@router.patch("/api/admin/shops/{shop_id}")
def update_shop(shop_id: str):
    # TODO: 상점 수정
    return {"id": shop_id}
