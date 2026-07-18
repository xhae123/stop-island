"""테스트 하네스 — Wave-1 에이전트용 픽스처 계약.

이 파일이 제공하는 픽스처(전부 function-scoped, 테스트마다 DB 초기화됨):

- ``db_session`` → SQLAlchemy ``Session``
    상태를 직접 배치(arrange)할 때 쓴다. 좌석/상점 시드는 이미 들어가 있다.
    예) ``db_session.add(Verification(...)); db_session.commit()``

- ``client`` → fastapi ``TestClient``
    기본으로 ``X-Device-Id: test-device`` 헤더가 실려 나간다.
    다른 device로 보내려면 요청마다 헤더를 덮어쓴다:
        ``client.post("/api/verify", headers={"X-Device-Id": "other"})``
    헤더 없는 요청(DEVICE_ID_REQUIRED 검증)을 보내려면 ``raw_client``를 쓴다.

- ``raw_client`` → fastapi ``TestClient`` (기본 device 헤더 없음)
    X-Device-Id 누락 경로(VF-106 등)를 테스트할 때 사용한다.

- ``DEFAULT_DEVICE_ID`` (상수) = "test-device"
    ``client``가 기본으로 싣는 device_id. 테스트에서 DB row의 device_id와 맞출 때 참조한다.

DB 격리: 각 테스트는 StaticPool 기반 in-memory SQLite 엔진을 새로 만들고
(create_all → seed), get_db 의존성을 오버라이드한다. 테스트가 끝나면 엔진을 버린다.
따라서 테스트 간 상태 누수가 없다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# models를 먼저 임포트해야 Base.metadata에 테이블이 등록된다.
# 주의: `import app.models`는 이름 `app`을 패키지에 바인딩하므로,
# FastAPI 인스턴스는 `fastapi_app` 별칭으로 받아 이름 충돌을 피한다.
import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app as fastapi_app
from app.seed import seed

DEFAULT_DEVICE_ID = "test-device"


@event.listens_for(Engine, "connect")
def _test_sqlite_pragma(dbapi_connection, connection_record) -> None:
    # 운영 db.py도 동일 PRAGMA를 걸지만, in-memory 테스트 엔진에도 FK 강제를 보장한다.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def _engine():
    # in-memory + StaticPool + check_same_thread=False:
    # TestClient(다른 스레드)와 db_session이 "같은" in-memory DB를 공유하게 하는 조합.
    # 매 테스트 새 엔진 → 테스트 간 완전 격리.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def _session_factory(_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture
def db_session(_session_factory):
    db = _session_factory()
    seed(db)  # 좌석 6 + 상점 2. 멱등이라 안전.
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def _override_get_db(_session_factory, db_session):
    # db_session에 의존시켜 seed가 먼저 돌게 한다.
    def _get_db_override():
        db = _session_factory()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = _get_db_override
    yield
    fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def raw_client(_override_get_db):
    # 기본 device 헤더 없음. DEVICE_ID_REQUIRED 경로 테스트용.
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture
def client(_override_get_db):
    # 기본으로 X-Device-Id를 싣는다. 대부분의 테스트가 이걸 쓴다.
    with TestClient(fastapi_app, headers={"X-Device-Id": DEFAULT_DEVICE_ID}) as c:
        yield c
