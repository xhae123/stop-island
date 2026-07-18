"""Verifier 체인(D-03) — OcrResult를 판정 결과로 집계한다.

체인 순서(공통 전제):
  RequiredField(store.name, retry)
  → Confidence(0.6, review)
  → Date(당일, reject)
  → Store(fuzzy, difflib; <0.5 reject / 0.5~0.7 review / ≥0.7 pass)

중복(Duplicate)은 이 체인에 넣지 않는다 — 📌 결정 #6: 체인 단계는 조회조차 하지 않고,
실제 check_and_mark는 승인 트랜잭션 안에서 수행한다(retry 재제출 자기충돌 방지).
따라서 이 모듈은 reject/retry/review만 판정하고, 중복은 라우터가 승인 직전에 처리한다.

집계 우선순위: reject > retry > review(_aggregate).
review만 있으면 서버가 approved로 승격 + needs_audit=True(D-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from app.ocr.engine import OcrResult
from app.timeutil import today_kst_str

# reason_code 상수 — 03-verify.md reason_code 표와 1:1 대응.
NOT_RECEIPT = "NOT_RECEIPT"
MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
NOT_TODAY = "NOT_TODAY"
SHOP_NOT_PARTICIPATING = "SHOP_NOT_PARTICIPATING"
DUPLICATE_RECEIPT = "DUPLICATE_RECEIPT"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
SHOP_MATCH_UNCERTAIN = "SHOP_MATCH_UNCERTAIN"
MANUAL_SHOP_SELECTED = "MANUAL_SHOP_SELECTED"
REVOKED_BY_AUDIT = "REVOKED_BY_AUDIT"

# StoreVerifier 2단계 임계값(📌 결정 #5)
STORE_REJECT_BELOW = 0.5   # 이 미만이면 명백 불일치 → reject
STORE_PASS_AT = 0.7        # 이 이상이면 통과. 사이(0.5~0.7)는 review
CONFIDENCE_MIN = 0.6       # ConfidenceVerifier 임계값


@dataclass
class ChainOutcome:
    """체인 집계 결과. 라우터가 이걸로 응답·row를 만든다."""

    decision: Literal["approve", "reject", "retry"]
    reason_code: str | None          # approve+needs_audit면 review 코드, pure approve면 None
    needs_audit: bool
    matched_shop_id: str | None       # StoreVerifier가 특정한 상점(review/pass 시)
    matched_shop_name: str | None


def _best_store_match(
    ocr_name: str, allowed_shops: list[tuple[str, str]]
) -> tuple[str | None, str | None, float]:
    """ocr_name과 가장 유사한 참여 상점을 difflib 유사도로 찾는다.

    allowed_shops: (shop_id, shop_name) 리스트.
    반환: (best_shop_id, best_shop_name, best_ratio). 목록이 비면 (None, None, 0.0).
    """
    best_id: str | None = None
    best_name: str | None = None
    best_ratio = 0.0
    for shop_id, shop_name in allowed_shops:
        ratio = SequenceMatcher(None, ocr_name, shop_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = shop_id
            best_name = shop_name
    return best_id, best_name, best_ratio


def evaluate(ocr: OcrResult, allowed_shops: list[tuple[str, str]]) -> ChainOutcome:
    """OcrResult를 판정한다. allowed_shops는 활성 상점 (id, name) 목록."""
    # (severity, reason_code)를 체인 순서대로 모은다. 대표 코드는 순서로 결정.
    failures: list[tuple[str, str]] = []
    matched_shop_id: str | None = None
    matched_shop_name: str | None = None

    has_store_name = bool(ocr.store_name and ocr.store_name.strip())

    # 1) RequiredField(store.name) — severity retry(📌 결정 #4)
    if not has_store_name:
        failures.append(("retry", MISSING_REQUIRED_FIELD))

    # 2) Confidence(0.6) — severity review
    if ocr.confidence < CONFIDENCE_MIN:
        failures.append(("review", LOW_CONFIDENCE))

    # 3) Date(당일) — severity reject. None이면 스킵(모듈 None 처리 규약).
    if ocr.date is not None and ocr.date != today_kst_str():
        failures.append(("reject", NOT_TODAY))

    # 4) Store(fuzzy) — store_name 없으면 스킵(RequiredField가 이미 retry로 잡음).
    if has_store_name:
        best_id, best_name, ratio = _best_store_match(ocr.store_name, allowed_shops)
        if ratio < STORE_REJECT_BELOW:
            failures.append(("reject", SHOP_NOT_PARTICIPATING))
        elif ratio < STORE_PASS_AT:
            failures.append(("review", SHOP_MATCH_UNCERTAIN))
            matched_shop_id, matched_shop_name = best_id, best_name
        else:
            matched_shop_id, matched_shop_name = best_id, best_name

    return _aggregate(failures, matched_shop_id, matched_shop_name)


def _aggregate(
    failures: list[tuple[str, str]],
    matched_shop_id: str | None,
    matched_shop_name: str | None,
) -> ChainOutcome:
    """reject > retry > review 우선순위로 최종 판정을 만든다."""
    if not failures:
        return ChainOutcome("approve", None, False, matched_shop_id, matched_shop_name)

    severities = {sev for sev, _ in failures}

    if "reject" in severities:
        # 체인 순서상 첫 reject 코드를 대표로(Date가 Store보다 앞 — VF-407).
        reason = next(code for sev, code in failures if sev == "reject")
        return ChainOutcome("reject", reason, False, matched_shop_id, matched_shop_name)

    if "retry" in severities:
        reason = next(code for sev, code in failures if sev == "retry")
        return ChainOutcome("retry", reason, False, matched_shop_id, matched_shop_name)

    # review만 남음 → 관용 승인 + 감사 플래그(D-05). 첫 review 코드를 대표로.
    reason = next(code for sev, code in failures if sev == "review")
    return ChainOutcome("approve", reason, True, matched_shop_id, matched_shop_name)
