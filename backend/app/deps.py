"""요청 횡단 관심사(cross-cutting) — device_id 식별과 에러 응답 규약.

- ApiError / raise_api: D-24 에러 응답 규약({ error: { code, message } })의 공통 예외.
  라우터는 HTTPException 대신 raise_api를 써서 일관된 봉투를 낸다.
  실제 JSONResponse 변환은 main.py에 등록된 예외 핸들러가 담당한다.
- get_device_id: D-07. X-Device-Id 헤더를 읽고, 없으면 400 DEVICE_ID_REQUIRED.
"""

from fastapi import Header


class ApiError(Exception):
    """D-24 에러 봉투를 실어 나르는 애플리케이션 예외.

    status_code: HTTP 상태 코드
    code: 시나리오에서 정의한 에러 코드(예: 'DEVICE_ID_REQUIRED', 'SEAT_TAKEN')
    message: 사용자 노출 문구
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def raise_api(status_code: int, code: str, message: str) -> None:
    """ApiError를 던지는 헬퍼. 라우터에서 `raise_api(...)`로 호출한다."""
    raise ApiError(status_code=status_code, code=code, message=message)


def get_device_id(x_device_id: str | None = Header(default=None)) -> str:
    """X-Device-Id 헤더를 필수로 강제하는 FastAPI 의존성(D-07).

    헤더가 없거나 빈 문자열이면 400 DEVICE_ID_REQUIRED를 던진다.
    device_id가 필요한 모든 라우터가 `device_id: str = Depends(get_device_id)`로 주입받는다.
    """
    if x_device_id is None or x_device_id.strip() == "":
        raise_api(400, "DEVICE_ID_REQUIRED", "일시적인 오류예요. 새로고침 후 다시 시도해주세요.")
    return x_device_id
