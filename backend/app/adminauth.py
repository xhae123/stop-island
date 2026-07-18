"""관리자 세션 인증 — D-21(단일 비밀번호 → HttpOnly 세션 쿠키 12시간).

이 모듈은 admin.py에서만 import 한다. 두 가지 관심사만 담당한다:
1. 비밀번호 검증 소스 — 오직 환경변수 ADMIN_PASSWORD. 레포에 시크릿을 넣지 않는다.
   테스트는 monkeypatch로 이 값을 주입/재정의한다(module-level getter라 가능).
2. 세션 저장소 — 인메모리 dict {token: expiry_dt}.

왜 인메모리 세션인가: 7일 무인 팝업이고 단일 인스턴스로 운영한다(SYS-7). Redis 같은
외부 저장소는 과설계다. 대가로 서버 재시작 시 세션이 전부 리셋되어 운영진이 재로그인해야
하지만, 규모상 수용 가능한 리스크다.
"""

import os
import secrets
from datetime import datetime, timedelta

from fastapi import Request

from app.deps import raise_api

# 세션 쿠키 이름과 수명(D-21: 12시간).
SESSION_COOKIE_NAME = "admin_session"
SESSION_TTL = timedelta(hours=12)

# 개발용 기본값 — 운영/테스트는 반드시 ADMIN_PASSWORD를 설정한다.
# 레포에 실제 비밀번호를 두지 않기 위한 플레이스홀더일 뿐이다.
_DEV_DEFAULT_PASSWORD = "dev-admin-change-me"

# token -> 만료 시각(UTC-naive). 나머지 코드가 datetime.utcnow()를 쓰므로 통일한다.
_sessions: dict[str, datetime] = {}


def get_admin_password() -> str:
    """관리자 비밀번호를 환경변수에서 읽는다(module-level getter — 테스트가 monkeypatch).

    왜 매번 os.environ을 읽나: import 시점에 상수로 굳히면 테스트의 monkeypatch.setenv가
    반영되지 않는다. 호출마다 읽어 런타임 주입을 허용한다.
    """
    return os.environ.get("ADMIN_PASSWORD", _DEV_DEFAULT_PASSWORD)


def create_session() -> str:
    """새 세션 토큰을 발급하고 저장소에 12시간 만료로 등록한다. 토큰 문자열을 반환한다."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = datetime.utcnow() + SESSION_TTL
    return token


def _is_valid(token: str | None) -> bool:
    """토큰이 저장소에 있고 만료 전이면 True. 만료됐으면 저장소에서 제거하고 False(ADM-104)."""
    if not token:
        return False
    expiry = _sessions.get(token)
    if expiry is None:
        return False
    if datetime.utcnow() >= expiry:
        # 만료된 세션은 즉시 제거한다(ADM-104: 저장소에서 만료 세션 삭제).
        _sessions.pop(token, None)
        return False
    return True


def require_admin(request: Request) -> None:
    """모든 /api/admin/* 보호 라우트가 의존하는 세션 가드.

    세션 쿠키를 읽어 저장소·만료를 검증하고, 실패하면 401 ADMIN_UNAUTHORIZED를 던진다.
    성공 시 반환값은 없다(부수효과 없는 게이트).
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not _is_valid(token):
        raise_api(401, "ADMIN_UNAUTHORIZED", "세션이 만료됐어요. 다시 로그인해주세요.")
