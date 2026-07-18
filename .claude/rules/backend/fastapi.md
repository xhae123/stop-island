---
paths:
  - "backend/**/*.py"
---

# 백엔드 규칙

## 스택
- FastAPI + SQLAlchemy + SQLite
- Python 3.14+
- Pydantic v2 모델

## 컨벤션
- 라우터: `backend/app/routers/` 하위, 도메인별 분리
- DB 모델: `backend/app/models.py`
- DB 세션: `backend/app/db.py`의 `get_db()` 의존성 주입
- 시드 데이터: `backend/app/init_db.py`

## API 설계
- 응답 형식: Pydantic 모델로 직렬화
- 에러: FastAPI `HTTPException` 사용
- CORS: `app/main.py`에서 설정 (프론트엔드 도메인 허용)
- 이미지 저장: `uploads/{YYYY-MM-DD}/{uuid}.jpg` (서버 로컬 디스크)

## 주의
- SQLite는 단일 writer — 동시성 이슈 주의
- any 타입 금지. 모든 함수에 타입 힌트
- 예약 만료: 2시간 후 자동 (cron 또는 요청 시 체크)
