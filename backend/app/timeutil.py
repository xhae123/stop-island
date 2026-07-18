"""KST(Asia/Seoul) 하루 경계 헬퍼 — D-01.

모든 "당일/하루" 판정은 서버 기준 KST 자정 경계로 한다(팝업은 한국 현장,
클라이언트 시계 불신). 저장은 UTC-naive datetime(created_at 등)으로 하되,
"오늘"을 계산할 때는 반드시 이 모듈을 통해 KST로 변환한다.

- now_kst(): 현재 KST 시각(tz-aware)
- today_kst_str(): 오늘 KST 날짜 'YYYY-MM-DD'
- kst_day_of(dt): 저장된 UTC-naive datetime의 KST 날짜 'YYYY-MM-DD'
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    """현재 시각을 KST tz-aware datetime으로 반환한다."""
    return datetime.now(KST)


def today_kst_str() -> str:
    """오늘(KST) 날짜를 'YYYY-MM-DD'로 반환한다. verify_date 기록·당일 판정의 기준."""
    return now_kst().strftime("%Y-%m-%d")


def kst_day_of(dt: datetime) -> str:
    """UTC-naive로 저장된 datetime(예: created_at)의 KST 날짜 'YYYY-MM-DD'를 반환한다.

    tz 정보가 없는 값은 UTC로 간주하고 KST로 변환한다. 이미 tz-aware면 그대로 변환한다.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%d")
