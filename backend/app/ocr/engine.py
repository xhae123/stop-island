"""OCR 엔진 인터페이스 + 결정론적 Fake + Gemini seam.

설계 문서(design-receipt-ocr.md)의 ReceiptData/ReceiptExtractor 전체를 그대로
옮기지 않고, 멈춰,섬! 인증 판정에 실제로 필요한 최소 표면만 노출한다(YAGNI).
판정 로직은 store_name/date/approval_number/confidence 네 필드만 소비하므로
OcrResult는 그 네 값 + 원본 dict(raw)만 담는다.

엔진은 동기(sync)다 — verify 라우터·SQLAlchemy 세션이 전부 동기라 async로
감싸면 needless abstraction만 늘어난다. 설계 문서의 async는 대규모 서비스용 예시.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class OcrError(Exception):
    """OCR 계층 최상위 예외."""


class NotReceiptError(OcrError):
    """이미지가 영수증이 아님(is_receipt=false).

    설계 문서 규약: 재시도해도 결과가 바뀌지 않으므로 재시도 없이 즉시 발생.
    라우터는 이를 잡아 retry + NOT_RECEIPT로 응답한다(VF-405)."""


class OcrUnavailable(OcrError):
    """OCR 엔진 호출이 재시도 소진 후에도 실패(타임아웃·5xx·429).

    라우터는 이를 잡아 503 OCR_UNAVAILABLE + manual 폴백 안내로 응답한다(D-25/VF-701)."""


@dataclass
class OcrResult:
    """영수증에서 뽑아낸, 판정에 필요한 최소 구조.

    date: 결제일 'YYYY-MM-DD' (없으면 None). DateVerifier가 KST 오늘과 비교한다.
    confidence: Gemini self-report 0.0~1.0. ConfidenceVerifier 임계값 판정용.
    raw: 감사·디버깅용 원본 추출 결과 전체(선택).
    """

    store_name: str | None
    date: str | None
    approval_number: str | None
    confidence: float
    raw: dict = field(default_factory=dict)


class ReceiptEngine(ABC):
    """영수증 이미지 → OcrResult 변환기.

    recognize()는 성공 시 OcrResult를 반환하고, 실패 시:
    - 영수증이 아니면 NotReceiptError
    - 엔진 장애(재시도 소진)면 OcrUnavailable
    를 던진다.
    """

    @abstractmethod
    def recognize(self, image_bytes: bytes) -> OcrResult:
        ...


class FakeReceiptEngine(ReceiptEngine):
    """테스트용 결정론적 엔진.

    - result를 주면 recognize()가 항상 그 값을 반환한다.
    - raises에 예외 인스턴스를 주면(예: OcrUnavailable(), NotReceiptError())
      recognize()가 그 예외를 던진다 — 장애·비영수증 시나리오 재현용.
    """

    def __init__(
        self,
        result: OcrResult | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._result = result
        self._raises = raises

    def recognize(self, image_bytes: bytes) -> OcrResult:
        if self._raises is not None:
            raise self._raises
        if self._result is None:
            # 명시적 실패 — 픽스처 오설정을 조용히 통과시키지 않는다.
            raise OcrUnavailable("FakeReceiptEngine에 result도 raises도 설정되지 않음")
        return self._result


class GeminiReceiptEngine(ReceiptEngine):
    """실 OCR seam — Gemini Flash 연동 자리.

    실제 모델 I/O는 `_call_gemini` 한 곳에 격리한다. 나중에 이 함수 body만
    진짜 Gemini 호출로 갈아끼우면 배선이 끝난다(Tom 결정 2026-07-17) — 나머지
    recognize/_parse 구조와 호출 측(라우터·테스트)은 손댈 필요가 없다.

    지금은 `_call_gemini`가 승인되는 mock 원시 응답을 반환하므로 photo 인증
    경로가 dev에서 end-to-end로 동작한다(예전처럼 항상 503이 아니다). 생성자는
    절대 실패하지 않는다(앱 부트를 막지 않음).
    """

    # dev mock이 사용하는 상호명. seed 참여 상점과 일치해야 StoreVerifier를 통과한다.
    _MOCK_STORE_NAME = "막걸리계보"

    def __init__(self, api_key: str | None = None) -> None:
        # 나중 실호출용. mock 경로는 이 키를 쓰지 않는다. 시크릿을 레포에 넣지 않는다.
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def recognize(self, image_bytes: bytes) -> OcrResult:
        raw = self._call_gemini(image_bytes)  # ← 진짜 Gemini로 갈아끼우는 유일한 지점
        return self._parse(raw)

    def _call_gemini(self, image_bytes: bytes) -> dict:
        """★ THE SWAP POINT ★ — 실제 Gemini 모델 I/O를 격리한 유일한 함수.

        배선 시 이 함수 body만 아래 스케치처럼 교체하면 된다:

            from google import genai  # requirements에 추가
            client = genai.Client(api_key=self.api_key)
            if not self.api_key:
                raise OcrUnavailable("GEMINI_API_KEY 미설정")
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {"role": "user", "parts": [
                        {"text": _RECEIPT_EXTRACTION_PROMPT},
                        {"inline_data": {"mime_type": "image/jpeg",
                                          "data": image_bytes}},
                    ]},
                ],
                config={"response_mime_type": "application/json",
                        "response_schema": _RECEIPT_JSON_SCHEMA},
            )
            # 타임아웃·5xx·429는 OcrUnavailable, is_receipt=false는 NotReceiptError로 매핑.
            return json.loads(resp.text)

        지금은 MOCK: 승인되는 그럴듯한 원시 응답을 반환한다. approval_number는
        이미지 해시에서 파생시켜(서로 다른 이미지가 가짜 DUPLICATE로 충돌하지 않도록)
        고정 payload의 함정을 피한다.
        """
        from app.timeutil import today_kst_str

        approval_number = "MOCK-" + hashlib.sha256(image_bytes).hexdigest()[:12]
        return {
            "is_receipt": True,
            "store": {"name": self._MOCK_STORE_NAME},
            "transaction": {
                "date": today_kst_str(),
                "approval_number": approval_number,
            },
            "confidence": 0.9,
        }

    def _parse(self, raw: dict) -> OcrResult:
        """Gemini 원시 응답(dict) → OcrResult. mock·실호출 양쪽이 공유하는 파싱 규약.

        is_receipt=false면 NotReceiptError(설계 문서 규약 — 재시도 없이 즉시).
        """
        if not raw.get("is_receipt", True):
            raise NotReceiptError("영수증이 아닌 이미지")
        store = raw.get("store") or {}
        transaction = raw.get("transaction") or {}
        return OcrResult(
            store_name=store.get("name"),
            date=transaction.get("date"),
            approval_number=transaction.get("approval_number"),
            confidence=float(raw.get("confidence", 0.0)),
            raw=raw,
        )
