"""HttpReceiptEngine 단위 테스트 — 코어 응답을 기존 예외/OcrResult로 매핑.

httpx MockTransport로 코어를 가짜 응답으로 대체한다(새 테스트 의존성 0).
verify 라우터·evaluate는 이 매핑 위에서 그대로 동작하므로 UX 계약이 보존된다.
"""

from __future__ import annotations

import httpx
import pytest

from app.ocr.engine import NotReceiptError, OcrUnavailable
from app.ocr.http_engine import HttpReceiptEngine

VALID_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def _engine(handler, api_key=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpReceiptEngine(base_url="http://core", api_key=api_key, client=client)


def test_receipt_maps_to_ocrresult():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "is_receipt": True,
                "store_name": "막걸리계보",
                "business_number": "123-45-67890",
                "date": "2026-07-22",
                "approval_number": "APP-1",
                "total_amount": 12000,
                "confidence": 0.92,
            },
        )

    ocr = _engine(handler).recognize(VALID_JPEG)
    assert ocr.store_name == "막걸리계보"
    assert ocr.date == "2026-07-22"
    assert ocr.approval_number == "APP-1"
    assert ocr.confidence == 0.92
    # 확장 필드는 raw로 실려온다(타입 필드 불변).
    assert ocr.raw["total_amount"] == 12000
    assert ocr.raw["business_number"] == "123-45-67890"


def test_not_receipt_raises():
    def handler(request):
        return httpx.Response(200, json={"is_receipt": False})

    with pytest.raises(NotReceiptError):
        _engine(handler).recognize(VALID_JPEG)


def test_503_raises_unavailable():
    def handler(request):
        return httpx.Response(503, json={"reason": "upstream_unavailable"})

    with pytest.raises(OcrUnavailable):
        _engine(handler).recognize(VALID_JPEG)


def test_401_raises_unavailable():
    def handler(request):
        return httpx.Response(401, json={"reason": "unauthorized"})

    with pytest.raises(OcrUnavailable):
        _engine(handler).recognize(VALID_JPEG)


def test_transport_error_raises_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(OcrUnavailable):
        _engine(handler).recognize(VALID_JPEG)


def test_sends_api_key_header():
    seen = {}

    def handler(request):
        seen["key"] = request.headers.get("x-api-key")
        seen["rid"] = request.headers.get("x-request-id")
        return httpx.Response(200, json={"is_receipt": True, "confidence": 0.9})

    _engine(handler, api_key="si-live-abc").recognize(VALID_JPEG)
    assert seen["key"] == "si-live-abc"
    assert seen["rid"]  # X-Request-Id 항상 부여
