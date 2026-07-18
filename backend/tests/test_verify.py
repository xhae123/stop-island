"""영수증 인증 TDD — 03-verify.md의 VF-* 시나리오를 테스트 스펙으로 삼는다.

엔진은 app.dependency_overrides[get_receipt_engine]로 FakeReceiptEngine을 주입해
결정론적으로 판정 경로를 검증한다. 참여 상점은 seed(막걸리계보·조준영 목공방)를 쓴다.

difflib 유사도(seed 상점 대비):
  "막걸리계보"    → 1.00  (≥0.7 통과)
  "계보 막걸리"   → 0.545 (0.5~0.7 review → SHOP_MATCH_UNCERTAIN)
  "스타벅스 강남점" → 0.13  (<0.5 reject → SHOP_NOT_PARTICIPATING)
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.main import app as fastapi_app
from app.models import Verification
from app.ocr import FakeReceiptEngine, NotReceiptError, OcrResult, OcrUnavailable
from app.ocr import get_receipt_engine
from app.timeutil import now_kst, today_kst_str

# --- 헬퍼 -------------------------------------------------------------------

# 시그니처가 맞는 최소 유효 JPEG 바이트(서버 이미지 가드 통과용).
VALID_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
OTHER_JPEG = b"\xff\xd8\xff\xe0" + b"\x11" * 48  # 해시가 다른 별개 이미지


def _today() -> str:
    return today_kst_str()


def _yesterday() -> str:
    return (now_kst() - timedelta(days=1)).strftime("%Y-%m-%d")


def _ocr(
    store_name: str | None = "막걸리계보",
    date: str | None = None,
    approval_number: str | None = "APP-DEFAULT",
    confidence: float = 0.95,
) -> OcrResult:
    return OcrResult(
        store_name=store_name,
        date=date if date is not None else _today(),
        approval_number=approval_number,
        confidence=confidence,
    )


def _post_photo(client, image=VALID_JPEG, content_type="image/jpeg", shop_id=None):
    files = {"image": ("receipt.jpg", image, content_type)}
    data = {"shop_id": shop_id} if shop_id is not None else None
    return client.post("/api/verify", files=files, data=data)


@pytest.fixture
def set_engine():
    """FakeReceiptEngine을 주입/교체하는 헬퍼. 테스트 종료 시 override를 정리한다."""

    def _set(engine):
        fastapi_app.dependency_overrides[get_receipt_engine] = lambda: engine

    yield _set
    fastapi_app.dependency_overrides.pop(get_receipt_engine, None)


def _count_verifications(db_session, **filters) -> int:
    q = db_session.query(Verification)
    for k, v in filters.items():
        q = q.filter(getattr(Verification, k) == v)
    return q.count()


# --- 3. 해피 패스 -----------------------------------------------------------


def test_vf301_photo_approved_issues_token(client, set_engine, db_session):
    set_engine(FakeReceiptEngine(result=_ocr(approval_number="APP-301")))
    resp = _post_photo(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["token"]
    assert body["verification_id"]
    assert body["shop_name"] == "막걸리계보"
    # 📌 감사 플래그·내부 코드는 응답에 노출하지 않는다(D-05).
    assert "needs_audit" not in body
    assert "reason_code" not in body
    row = db_session.query(Verification).filter_by(id=body["verification_id"]).one()
    assert row.status == "approved"
    assert row.method == "photo"
    assert row.needs_audit is False
    assert row.shop_id == "makgeolli-gyebo"
    assert row.image_hash  # dup 검출용 저장


def test_vf302_ocr_match_wins_over_user_shop_hint(client, set_engine):
    # 사용자는 막걸리계보를 골랐지만 OCR은 조준영 목공방으로 매칭 → OCR 우선.
    set_engine(FakeReceiptEngine(result=_ocr(store_name="조준영 목공방", approval_number="APP-302")))
    resp = _post_photo(client, shop_id="makgeolli-gyebo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["shop_name"] == "조준영 목공방"


# --- 4. rejected / retry ----------------------------------------------------


def test_vf401_not_today_rejected(client, set_engine, db_session):
    set_engine(FakeReceiptEngine(result=_ocr(date=_yesterday(), approval_number="APP-401")))
    resp = _post_photo(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "NOT_TODAY"
    assert _yesterday() in body["message"]
    assert body["token"] is None if "token" in body else True
    assert _count_verifications(db_session, status="rejected", reason_code="NOT_TODAY") == 1


def test_vf402_shop_not_participating_rejected(client, set_engine):
    set_engine(FakeReceiptEngine(result=_ocr(store_name="스타벅스 강남점", approval_number="APP-402")))
    resp = _post_photo(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "SHOP_NOT_PARTICIPATING"


def test_vf403_duplicate_by_approval_number(client, set_engine):
    # device A 승인 → device B가 다른 이미지·같은 승인번호로 제출 → 중복.
    set_engine(FakeReceiptEngine(result=_ocr(approval_number="DUP-403")))
    r1 = _post_photo(client)
    assert r1.json()["status"] == "approved"

    r2 = client.post(
        "/api/verify",
        files={"image": ("r.jpg", OTHER_JPEG, "image/jpeg")},
        headers={"X-Device-Id": "device-b"},
    )
    body = r2.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "DUPLICATE_RECEIPT"


def test_vf404_duplicate_by_image_hash_when_approval_none(client, set_engine):
    # 승인번호 None → 중복 키는 이미지 해시. 같은 이미지 재제출이 잡힌다.
    set_engine(FakeReceiptEngine(result=_ocr(approval_number=None)))
    r1 = _post_photo(client, image=VALID_JPEG)
    assert r1.json()["status"] == "approved"

    r2 = client.post(
        "/api/verify",
        files={"image": ("r.jpg", VALID_JPEG, "image/jpeg")},  # 동일 바이트 → 동일 해시
        headers={"X-Device-Id": "device-b"},
    )
    body = r2.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "DUPLICATE_RECEIPT"


def test_vf405_not_receipt_retry(client, set_engine, db_session):
    set_engine(FakeReceiptEngine(raises=NotReceiptError()))
    resp = _post_photo(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "retry"
    assert body["reason_code"] == "NOT_RECEIPT"
    # DB에는 rejected로 종결(응답 status만 retry).
    assert _count_verifications(db_session, status="rejected", reason_code="NOT_RECEIPT") == 1


def test_vf406_missing_required_field_retry(client, set_engine):
    set_engine(FakeReceiptEngine(result=_ocr(store_name=None)))
    resp = _post_photo(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "retry"
    assert body["reason_code"] == "MISSING_REQUIRED_FIELD"


def test_vf407_aggregate_reject_beats_review(client, set_engine):
    # 어제 날짜(reject) + confidence 0.4(review) → reject 우선, NOT_TODAY만 표시.
    set_engine(
        FakeReceiptEngine(result=_ocr(date=_yesterday(), confidence=0.4, approval_number="APP-407"))
    )
    resp = _post_photo(client)
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "NOT_TODAY"


def test_vf408_same_image_resubmit_reevaluates(client, set_engine, db_session):
    # 같은 이미지를 다시 제출해도 체인은 재실행되고 새 시도 row가 남는다.
    set_engine(FakeReceiptEngine(result=_ocr(date=_yesterday(), approval_number="APP-408")))
    _post_photo(client)
    _post_photo(client)
    assert _count_verifications(db_session, reason_code="NOT_TODAY") == 2


def test_vf409_unlimited_retries_then_approve(client, set_engine, db_session):
    # 4번 reject 후 5번째 정상 → 승인. rejected는 무제한.
    set_engine(FakeReceiptEngine(result=_ocr(date=_yesterday(), approval_number="APP-409")))
    for _ in range(4):
        assert _post_photo(client).json()["status"] == "rejected"
    set_engine(FakeReceiptEngine(result=_ocr(date=_today(), approval_number="APP-409-OK")))
    resp = _post_photo(client)
    assert resp.json()["status"] == "approved"
    assert _count_verifications(db_session, status="rejected") == 4
    assert _count_verifications(db_session, status="approved") == 1


# --- 5. 관용 승인(needs_audit) --------------------------------------------


def test_vf501_low_confidence_approved_with_audit(client, set_engine, db_session):
    set_engine(FakeReceiptEngine(result=_ocr(confidence=0.45, approval_number="APP-501")))
    resp = _post_photo(client)
    body = resp.json()
    assert body["status"] == "approved"
    assert body["token"]
    # 응답에는 감사 흔적 없음.
    assert "needs_audit" not in body and "reason_code" not in body
    row = db_session.query(Verification).filter_by(id=body["verification_id"]).one()
    assert row.needs_audit is True
    assert row.reason_code == "LOW_CONFIDENCE"


def test_vf502_fuzzy_boundary_approved_with_audit(client, set_engine, db_session):
    set_engine(FakeReceiptEngine(result=_ocr(store_name="계보 막걸리", approval_number="APP-502")))
    resp = _post_photo(client)
    body = resp.json()
    assert body["status"] == "approved"
    row = db_session.query(Verification).filter_by(id=body["verification_id"]).one()
    assert row.needs_audit is True
    assert row.reason_code == "SHOP_MATCH_UNCERTAIN"
    assert row.shop_id == "makgeolli-gyebo"


# --- 6. manual 경로 ---------------------------------------------------------


def test_vf601_manual_immediate_approve_with_audit(client, db_session):
    resp = client.post("/api/verify", data={"shop_id": "makgeolli-gyebo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["token"]
    assert body["shop_name"] == "막걸리계보"
    row = db_session.query(Verification).filter_by(id=body["verification_id"]).one()
    assert row.method == "manual"
    assert row.needs_audit is True
    assert row.reason_code == "MANUAL_SHOP_SELECTED"
    assert row.image_url is None


def test_vf602_manual_no_dup_defense_across_devices(client):
    r1 = client.post("/api/verify", data={"shop_id": "makgeolli-gyebo"})
    assert r1.json()["status"] == "approved"
    # 다른 device가 같은 상점 manual → 중복 방어 불가, 그대로 승인.
    r2 = client.post(
        "/api/verify",
        data={"shop_id": "makgeolli-gyebo"},
        headers={"X-Device-Id": "device-b"},
    )
    assert r2.json()["status"] == "approved"


def test_vf604_no_image_no_shop_invalid_request(client):
    resp = client.post("/api/verify", data={"shop_id": ""})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


def test_vf604_nonexistent_shop_invalid_request(client):
    resp = client.post("/api/verify", data={"shop_id": "no-such-shop"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


# --- 7. OCR 장애 폴백 -------------------------------------------------------


def test_vf701_ocr_unavailable_503_no_row(client, set_engine, db_session):
    set_engine(FakeReceiptEngine(raises=OcrUnavailable()))
    resp = _post_photo(client)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "OCR_UNAVAILABLE"
    # 판정 자체가 없었으므로 row를 남기지 않는다.
    assert _count_verifications(db_session) == 0


# --- 8. 1일 1회 제한 / 날짜 경계 --------------------------------------------


def test_vf801_already_verified_today_409(client, set_engine, db_session):
    set_engine(FakeReceiptEngine(result=_ocr(approval_number="APP-801")))
    assert _post_photo(client).json()["status"] == "approved"
    # 같은 device 재제출 → 409, 새 row·엔진 호출 없음.
    resp = _post_photo(client)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ALREADY_VERIFIED_TODAY"
    assert _count_verifications(db_session, status="approved") == 1


def test_vf802_reverify_allowed_after_revoke(client, set_engine, db_session):
    # 무효화(REVOKED_BY_AUDIT)된 rejected row는 1일 1회 유니크에서 빠지므로 재인증 허용.
    db_session.add(
        Verification(
            device_id="test-device",
            method="photo",
            status="rejected",
            reason_code="REVOKED_BY_AUDIT",
            verify_date=_today(),
        )
    )
    db_session.commit()
    set_engine(FakeReceiptEngine(result=_ocr(approval_number="APP-802")))
    resp = _post_photo(client)
    assert resp.json()["status"] == "approved"


# --- GET /api/verify/status -------------------------------------------------


def test_status_none_for_new_device(client):
    resp = client.get("/api/verify/status")
    assert resp.status_code == 200
    assert resp.json() == {"status": "none"}


def test_status_approved_restores_token(client, set_engine):
    set_engine(FakeReceiptEngine(result=_ocr(approval_number="APP-STAT")))
    post = _post_photo(client).json()
    resp = client.get("/api/verify/status")
    body = resp.json()
    assert body["status"] == "approved"
    assert body["token"] == post["token"]
    assert body["shop_name"] == "막걸리계보"
    assert body["method"] == "photo"


def test_status_manual_approved(client):
    client.post("/api/verify", data={"shop_id": "makgeolli-gyebo"})
    body = client.get("/api/verify/status").json()
    assert body["status"] == "approved"
    assert body["method"] == "manual"


def test_vf505_status_revoked(client, db_session):
    db_session.add(
        Verification(
            device_id="test-device",
            method="photo",
            status="rejected",
            reason_code="REVOKED_BY_AUDIT",
            verify_date=_today(),
        )
    )
    db_session.commit()
    body = client.get("/api/verify/status").json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "REVOKED_BY_AUDIT"


# --- 기본(mock-backed) 엔진 end-to-end -------------------------------------


def test_default_engine_photo_approves(client, db_session):
    # override 없음 → 기본 GeminiReceiptEngine(mock _call_gemini)이 승인 결과를 낸다.
    # dev에서 photo 경로가 503 없이 end-to-end로 동작함을 증명(Tom 결정).
    resp = _post_photo(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["token"]
    assert body["shop_name"] == "막걸리계보"
    row = db_session.query(Verification).filter_by(id=body["verification_id"]).one()
    assert row.status == "approved"
    assert row.approval_number.startswith("MOCK-")


def test_default_engine_distinct_images_no_false_duplicate(client):
    # approval_number를 이미지 해시에서 파생 → 다른 이미지는 가짜 DUPLICATE로 충돌하지 않는다.
    r1 = _post_photo(client, image=VALID_JPEG)
    assert r1.json()["status"] == "approved"
    r2 = _post_photo(client, image=OTHER_JPEG, content_type="image/jpeg")
    r2b = client.post(
        "/api/verify",
        files={"image": ("r.jpg", OTHER_JPEG, "image/jpeg")},
        headers={"X-Device-Id": "device-c"},
    )
    # device-b로 첫 이미지 다르게 → 승인(중복 아님)
    assert r2b.json()["status"] == "approved"


def test_engine_raising_ocr_unavailable_still_503(client, set_engine, db_session):
    # 엔진 recognize가 OcrUnavailable을 던지면 503 폴백은 그대로 유지된다.
    set_engine(FakeReceiptEngine(raises=OcrUnavailable()))
    resp = _post_photo(client)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "OCR_UNAVAILABLE"
    assert _count_verifications(db_session) == 0


# --- 오류: device id / 이미지 가드 -----------------------------------------


def test_vf106_device_id_required_post(raw_client):
    resp = raw_client.post("/api/verify", data={"shop_id": "makgeolli-gyebo"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEVICE_ID_REQUIRED"


def test_vf106_device_id_required_status(raw_client):
    resp = raw_client.get("/api/verify/status")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEVICE_ID_REQUIRED"


def test_vf205_invalid_content_type(client, db_session):
    resp = client.post(
        "/api/verify",
        files={"image": ("x.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_IMAGE"
    assert _count_verifications(db_session) == 0


def test_vf205_zero_byte_image(client):
    resp = client.post(
        "/api/verify",
        files={"image": ("x.jpg", b"", "image/jpeg")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_IMAGE"


def test_vf205_bad_signature(client):
    resp = client.post(
        "/api/verify",
        files={"image": ("x.jpg", b"not really a jpeg", "image/jpeg")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_IMAGE"
