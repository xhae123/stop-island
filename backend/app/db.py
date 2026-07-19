import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

# DB 경로는 환경변수로 외부화한다. 기본값은 기존 동작(CWD의 app.db) 그대로라
# 로컬/테스트는 영향 없음. 컨테이너에서는 마운트된 볼륨의 절대경로를 넣어
# 컨테이너 재생성에도 데이터가 보존되게 한다. (예: sqlite:////data/app.db)
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")

# check_same_thread=False: SQLite 기본 제약(단일 스레드) 해제.
# FastAPI는 요청마다 다른 스레드에서 세션을 쓸 수 있어서 필요.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    # SQLite는 외래키 제약을 커넥션마다 명시적으로 켜야 강제된다(기본 OFF).
    # verify_token FK·shop_id FK 등이 실제로 검사되도록 모든 커넥션에 PRAGMA를 적용한다.
    # Engine 전역 리스너로 걸어야 테스트용 in-memory 엔진에도 동일하게 적용된다.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
