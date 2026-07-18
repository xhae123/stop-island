"""POST /api/verify · GET /api/verify/status — 영수증 인증(03-verify.md).

핵심 흐름:
  1) 당일 approved 선점 확인 → 있으면 409 ALREADY_VERIFIED_TODAY(Gemini 호출 없음)
  2) method 판정(📌 결정 #3): image 있으면 photo, shop_id만 있으면 manual, 둘 다 없으면 400
  3) photo: 이미지 가드 → 엔진 recognize → Verifier 체인 → 승인 트랜잭션(중복 mark)
     manual: 즉시 approved + needs_audit + MANUAL_SHOP_SELECTED
  4) 응답 봉투: 성공 200 { status, token?, verification_id, shop_name?, reason_code?, message? }
     실패 4xx/5xx { error: { code, message } }(D-24)

📌 needs_audit는 응답에 싣지 않는다(03-verify 공통 전제 — 사용자는 감사 플래그를 알 수 없다).
   approved 응답에는 reason_code도 싣지 않는다(LOW_CONFIDENCE 등 내부 코드 노출 = 감사 플래그 누출).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_device_id, raise_api
from app.models import Shop, Verification
from app.ocr import NotReceiptError, OcrUnavailable, ReceiptEngine, get_receipt_engine
from app.ocr.verifiers import (
    DUPLICATE_RECEIPT,
    MANUAL_SHOP_SELECTED,
    NOT_RECEIPT,
    NOT_TODAY,
    evaluate,
)
from app.timeutil import today_kst_str

router = APIRouter()

# 서버 측 이미지 가드(VF-203/205). 클라이언트도 막지만 서버가 최종 방어선.
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB(VF-202)
_JPEG_SIG = b"\xff\xd8\xff"
_PNG_SIG = b"\x89PNG\r\n\x1a\n"

# reason_code → 사용자 문구(rejected/retry 200 응답의 message용).
# NOT_TODAY는 날짜가 동적이라 별도 처리.
_REASON_MESSAGES = {
    NOT_RECEIPT: "영수증 사진이 아닌 것 같아요. 영수증이 잘 보이게 다시 찍어주세요.",
    "MISSING_REQUIRED_FIELD": "영수증 정보를 읽지 못했어요. 상호명이 잘 보이게 다시 찍어주세요.",
    "SHOP_NOT_PARTICIPATING": "참여 상점의 영수증이 아니에요. 참여 상점 목록을 확인해주세요.",
    DUPLICATE_RECEIPT: "이미 사용된 영수증이에요.",
}
_OCR_UNAVAILABLE_MSG = "사진 인증이 지금 어려워요. 아래에서 상점을 직접 선택해주세요."
_ALREADY_MSG = "오늘은 이미 인증을 완료했어요. 좌석 선택으로 이동해주세요."
_INVALID_IMAGE_MSG = "이미지를 읽을 수 없어요. 다른 사진으로 다시 시도해주세요."
_INVALID_REQUEST_MSG = "인증 정보가 올바르지 않아요. 다시 시도해주세요."


def _reason_message(reason_code: str, ocr_date: str | None = None) -> str:
    if reason_code == NOT_TODAY:
        return f"오늘 결제한 영수증만 인정돼요. (영수증 날짜: {ocr_date})"
    return _REASON_MESSAGES.get(reason_code, "인증에 실패했어요.")


def _today_approved(db: Session, device_id: str) -> Verification | None:
    """오늘(KST) 이 device의 approved 인증(감사 플래그 포함)을 반환한다."""
    return (
        db.query(Verification)
        .filter(
            Verification.device_id == device_id,
            Verification.verify_date == today_kst_str(),
            Verification.status == "approved",
        )
        .first()
    )


def _shop_name(db: Session, shop_id: str | None) -> str | None:
    if not shop_id:
        return None
    shop = db.get(Shop, shop_id)
    return shop.name if shop else None


def _active_shops(db: Session) -> list[tuple[str, str]]:
    rows = (
        db.query(Shop)
        .filter(Shop.is_active.is_(True))
        .order_by(Shop.sort_order)
        .all()
    )
    return [(s.id, s.name) for s in rows]


def _validate_image(content_type: str | None, data: bytes) -> None:
    """형식·크기·시그니처를 검사한다. 위반 시 400 INVALID_IMAGE(row 없음)."""
    if len(data) == 0 or len(data) > _MAX_IMAGE_BYTES:
        raise_api(400, "INVALID_IMAGE", _INVALID_IMAGE_MSG)
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise_api(400, "INVALID_IMAGE", _INVALID_IMAGE_MSG)
    # content-type은 위조 가능하므로 매직 바이트로 실제 포맷을 확인한다(경량 디코딩 가드).
    if content_type == "image/jpeg" and not data.startswith(_JPEG_SIG):
        raise_api(400, "INVALID_IMAGE", _INVALID_IMAGE_MSG)
    if content_type == "image/png" and not data.startswith(_PNG_SIG):
        raise_api(400, "INVALID_IMAGE", _INVALID_IMAGE_MSG)


def _duplicate_exists(
    db: Session, approval_number: str | None, image_hash: str
) -> bool:
    """이미 승인된 같은 영수증이 있는지 조회한다(중복 키: 승인번호 우선, 없으면 이미지 해시).

    📌 한계: 모델에 승인번호/해시 UNIQUE 제약이 없어 조회+INSERT가 원자적이지 않다.
    순차 재제출(VF-403/404)은 정확히 잡지만, 서로 다른 device의 진짜 동시 제출(VF-902)은
    구조적으로 막지 못한다 — 사후감사(D-22)로 보완. (models.py 소유 밖이라 여기서 못 고침.)
    """
    query = db.query(Verification).filter(Verification.status == "approved")
    if approval_number:
        query = query.filter(Verification.approval_number == approval_number)
    else:
        query = query.filter(Verification.image_hash == image_hash)
    return db.query(query.exists()).scalar()


@router.post("/api/verify")
def verify_receipt(
    image: UploadFile | None = File(default=None),
    shop_id: str | None = Form(default=None),
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
    engine: ReceiptEngine = Depends(get_receipt_engine),
):
    # 1) 당일 approved 선점 확인 — 판정·엔진 호출 전에 차단(VF-801). 감사 플래그 승인도 approved라 걸림.
    if _today_approved(db, device_id) is not None:
        raise_api(409, "ALREADY_VERIFIED_TODAY", _ALREADY_MSG)

    has_image = image is not None and bool(image.filename)

    # 2) method 판정(📌 결정 #3)
    if not has_image and not shop_id:
        raise_api(400, "INVALID_REQUEST", _INVALID_REQUEST_MSG)

    if not has_image:
        return _handle_manual(db, device_id, shop_id)

    return _handle_photo(db, device_id, image, engine)


def _handle_manual(db: Session, device_id: str, shop_id: str):
    """manual 경로(D-04): 즉시 approved + needs_audit + MANUAL_SHOP_SELECTED."""
    shop = db.get(Shop, shop_id)
    if shop is None or not shop.is_active:
        raise_api(400, "INVALID_REQUEST", _INVALID_REQUEST_MSG)

    token = str(uuid.uuid4())
    verification = Verification(
        device_id=device_id,
        image_url=None,  # 증빙 이미지 없음(전건 감사 대상)
        image_hash=None,
        shop_id=shop_id,
        method="manual",
        status="approved",
        needs_audit=True,
        reason_code=MANUAL_SHOP_SELECTED,
        token=token,
        verify_date=today_kst_str(),
        verified_at=datetime.utcnow(),
    )
    return _commit_approved(db, verification, shop.name)


def _handle_photo(
    db: Session, device_id: str, image: UploadFile, engine: ReceiptEngine
):
    """photo 경로: 이미지 가드 → 엔진 → 체인 → 승인 트랜잭션."""
    data = image.file.read()
    _validate_image(image.content_type, data)
    image_hash = hashlib.sha256(data).hexdigest()
    # 실제 파일 저장은 seam — 경로만 기록한다(D-23 디스크 저장은 후속 작업).
    image_url = f"uploads/{today_kst_str()}/{uuid.uuid4()}.jpg"

    # 엔진 실행
    try:
        ocr = engine.recognize(data)
    except NotReceiptError:
        # 영수증 아님 → retry + NOT_RECEIPT. DB는 rejected로 종결(응답 status만 retry).
        return _persist_failure(
            db, device_id, "retry", NOT_RECEIPT, image_hash, image_url,
            ocr=None, shop_id=None,
        )
    except OcrUnavailable:
        # 재시도 소진 장애 → 503, row 없음(판정 자체가 없었음). manual 폴백 안내(D-25).
        raise_api(503, "OCR_UNAVAILABLE", _OCR_UNAVAILABLE_MSG)

    outcome = evaluate(ocr, _active_shops(db))

    if outcome.decision in ("reject", "retry"):
        response_status = "rejected" if outcome.decision == "reject" else "retry"
        return _persist_failure(
            db, device_id, response_status, outcome.reason_code,
            image_hash, image_url, ocr=ocr, shop_id=outcome.matched_shop_id,
        )

    # approve(순수 통과 or review 승격). 승인 트랜잭션에서 중복 mark.
    if _duplicate_exists(db, ocr.approval_number, image_hash):
        return _persist_failure(
            db, device_id, "rejected", DUPLICATE_RECEIPT,
            image_hash, image_url, ocr=ocr, shop_id=outcome.matched_shop_id,
        )

    token = str(uuid.uuid4())
    verification = Verification(
        device_id=device_id,
        image_url=image_url,
        image_hash=image_hash,
        shop_id=outcome.matched_shop_id,
        method="photo",
        status="approved",
        needs_audit=outcome.needs_audit,
        reason_code=outcome.reason_code,  # LOW_CONFIDENCE/SHOP_MATCH_UNCERTAIN 또는 None
        confidence=ocr.confidence,
        ocr_store_name=ocr.store_name,
        ocr_date=ocr.date,
        approval_number=ocr.approval_number,
        token=token,
        verify_date=today_kst_str(),
        verified_at=datetime.utcnow(),
    )
    return _commit_approved(db, verification, outcome.matched_shop_name)


def _persist_failure(
    db: Session,
    device_id: str,
    response_status: str,   # 'rejected' | 'retry' (응답용)
    reason_code: str,
    image_hash: str,
    image_url: str,
    *,
    ocr,
    shop_id: str | None,
):
    """실패(rejected/retry) 시도를 DB에 rejected row로 남기고 응답을 만든다.

    DB status는 항상 'rejected'(2값). 응답 status만 retry/rejected로 구분(서두 📌).
    """
    verification = Verification(
        device_id=device_id,
        image_url=image_url,
        image_hash=image_hash,
        shop_id=shop_id,
        method="photo",
        status="rejected",
        needs_audit=False,
        reason_code=reason_code,
        confidence=ocr.confidence if ocr else None,
        ocr_store_name=ocr.store_name if ocr else None,
        ocr_date=ocr.date if ocr else None,
        approval_number=ocr.approval_number if ocr else None,
        token=None,
        verify_date=today_kst_str(),
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)

    ocr_date = ocr.date if ocr else None
    body = {
        "status": response_status,
        "reason_code": reason_code,
        "message": _reason_message(reason_code, ocr_date),
        "verification_id": verification.id,
    }
    # VF-605 프리필용: OCR이 특정한 상점이 있으면 실어보낸다.
    if shop_id:
        body["matched_shop_id"] = shop_id
    return body


def _commit_approved(db: Session, verification: Verification, shop_name: str | None):
    """approved row를 INSERT한다. 부분 유니크 위반(동시 제출)은 409로 변환(VF-901)."""
    db.add(verification)
    try:
        db.commit()
    except IntegrityError:
        # uq_verif_device_day_approved 위반 = 같은 device가 오늘 이미 승인됨.
        db.rollback()
        raise_api(409, "ALREADY_VERIFIED_TODAY", _ALREADY_MSG)
    db.refresh(verification)

    # 📌 approved 응답에는 needs_audit·reason_code를 싣지 않는다(감사 플래그 비노출).
    body = {
        "status": "approved",
        "token": verification.token,
        "verification_id": verification.id,
    }
    if shop_name:
        body["shop_name"] = shop_name
    return body


@router.get("/api/verify/status")
def verify_status(
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    """당일(KST) 최신 인증 상태 — 재진입 복원용 단발 조회(D-14/VF-102/VF-505).

    폴링 용도가 아니다. approved면 토큰·상점명 반환, 없으면 none.
    감사 무효화(REVOKED_BY_AUDIT)는 approved가 rejected로 전환된 상태라
    approved가 없고 최신 row가 rejected로 잡힌다.
    """
    approved = _today_approved(db, device_id)
    if approved is not None:
        return {
            "status": "approved",
            "token": approved.token,
            "verification_id": approved.id,
            "method": approved.method,
            "shop_name": _shop_name(db, approved.shop_id),
        }

    latest = (
        db.query(Verification)
        .filter(
            Verification.device_id == device_id,
            Verification.verify_date == today_kst_str(),
        )
        .order_by(Verification.created_at.desc(), Verification.id.desc())
        .first()
    )
    if latest is None:
        return {"status": "none"}

    return {
        "status": "rejected",
        "reason_code": latest.reason_code,
        "verification_id": latest.id,
    }
