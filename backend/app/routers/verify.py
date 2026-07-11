from fastapi import APIRouter

router = APIRouter()


@router.post("/api/verify")
def verify_receipt():
    # TODO: image_url or shop_id 기반 verifications insert
    # TODO: device_id + 당일 날짜 기준 1일 1회 제한 (애플리케이션 레벨 체크)
    # TODO: method='manual'은 자동 승인 + token 발급
    return {"id": "dummy-verification-id", "status": "pending", "token": None}
