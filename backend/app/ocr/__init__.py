"""OCR 패키지 공개 표면 + 엔진 주입 의존성.

get_receipt_engine: FastAPI 의존성. 기본은 GeminiReceiptEngine seam(미배선이라 항상
OcrUnavailable → manual 폴백). 테스트는 app.dependency_overrides[get_receipt_engine]로
FakeReceiptEngine을 주입해 결정론적으로 판정 경로를 검증한다.

이 의존성을 여기에 둔 이유: verify 라우터가 소유하되 main.py/deps.py를 건드리지 않고
override 키를 안정적으로 공유하기 위함(라우터와 테스트가 같은 심볼을 import).
"""

from app.ocr.engine import (
    FakeReceiptEngine,
    GeminiReceiptEngine,
    NotReceiptError,
    OcrError,
    OcrResult,
    OcrUnavailable,
    ReceiptEngine,
)
from app.ocr.http_engine import HttpReceiptEngine, build_http_engine_from_env

__all__ = [
    "FakeReceiptEngine",
    "GeminiReceiptEngine",
    "HttpReceiptEngine",
    "NotReceiptError",
    "OcrError",
    "OcrResult",
    "OcrUnavailable",
    "ReceiptEngine",
    "get_receipt_engine",
]


def _build_default_engine() -> ReceiptEngine:
    """RECEIPT_CORE_URL이 있으면 외부 코어에 위임(HttpReceiptEngine),
    없으면 기존 인프로세스 Gemini seam을 그대로 쓴다(기본 동작 불변)."""
    http_engine = build_http_engine_from_env()
    if http_engine is not None:
        return http_engine
    return GeminiReceiptEngine()


# 앱 전역에서 재사용하는 단일 엔진 인스턴스. 생성자는 실패하지 않는다(seam).
_default_engine: ReceiptEngine = _build_default_engine()


def get_receipt_engine() -> ReceiptEngine:
    """설정된 ReceiptEngine을 반환하는 FastAPI 의존성."""
    return _default_engine
