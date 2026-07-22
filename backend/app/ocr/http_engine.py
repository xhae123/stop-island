"""HttpReceiptEngine — 영수증 코어 서버(/v1/extract)를 호출하는 ReceiptEngine 구현.

stop-island는 이 엔진을 통해 OCR을 외부 코어에 위임한다. verify 라우터·evaluate·DB는
그대로다(엔진이 seam이라 구현체만 갈아끼운다). 실패는 기존 예외로 흡수해 UX를 보존한다:

  200 is_receipt=true  → OcrResult(추가필드 total_amount/business_number는 raw에)
  200 is_receipt=false → NotReceiptError  → 라우터가 retry + NOT_RECEIPT
  503 / timeout / 연결실패 / 그 외 → OcrUnavailable → 503 → 수동 폴백

코어의 확장 필드(total_amount, business_number)는 OcrResult 타입 필드를 늘리지 않고
raw dict에 실어 나른다 — evaluate는 4필드만 소비하므로 판정 로직이 불변이다.
"""

from __future__ import annotations

import os
import uuid

import httpx

from app.ocr.engine import NotReceiptError, OcrResult, OcrUnavailable, ReceiptEngine

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _sniff_content_type(data: bytes) -> str:
    """검증된 이미지 바이트의 실제 포맷을 매직바이트로 판별(라우터가 이미 가드함)."""
    return "image/png" if data.startswith(_PNG_SIG) else "image/jpeg"


class HttpReceiptEngine(ReceiptEngine):
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        # 코어 내부 Gemini 타임아웃(기본 8s)보다 길게 잡아, 코어가 먼저 깔끔한 503을
        # 반환하게 한다(소켓 타임아웃은 최후 안전망).
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        # 싱글턴 엔진이라 Client를 재사용한다(커넥션 풀). 테스트는 MockTransport 주입.
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def recognize(self, image_bytes: bytes) -> OcrResult:
        headers = {"X-Request-Id": uuid.uuid4().hex}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        files = {
            "image": ("receipt", image_bytes, _sniff_content_type(image_bytes)),
        }

        try:
            resp = self._client.post(
                f"{self._base_url}/v1/extract",
                files=files,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            # 타임아웃·연결실패 등 전송 계층 실패 → 엔진 불가.
            raise OcrUnavailable(f"코어 호출 실패: {exc}") from exc

        if resp.status_code != 200:
            # 503(코어 판단 불가)·401(오설정)·기타 → 전부 불가로 흡수(→ 수동 폴백).
            raise OcrUnavailable(f"코어 응답 {resp.status_code}")

        body = resp.json()
        if not body.get("is_receipt", False):
            raise NotReceiptError("코어 판정: 영수증 아님")

        return OcrResult(
            store_name=body.get("store_name"),
            date=body.get("date"),
            approval_number=body.get("approval_number"),
            confidence=float(body.get("confidence") or 0.0),
            raw={
                "total_amount": body.get("total_amount"),
                "business_number": body.get("business_number"),
                "source": "receipt-core",
            },
        )


def build_http_engine_from_env() -> HttpReceiptEngine | None:
    """RECEIPT_CORE_URL이 설정돼 있으면 HttpReceiptEngine을 만든다. 없으면 None."""
    base_url = os.environ.get("RECEIPT_CORE_URL")
    if not base_url or not base_url.strip():
        return None
    api_key = os.environ.get("RECEIPT_CORE_API_KEY")
    timeout = os.environ.get("RECEIPT_CORE_TIMEOUT_SECONDS")
    return HttpReceiptEngine(
        base_url=base_url.strip(),
        api_key=api_key.strip() if api_key else None,
        timeout_seconds=float(timeout) if timeout and timeout.strip() else 10.0,
    )
