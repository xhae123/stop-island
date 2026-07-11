"""DB 테이블 생성 + 시드 데이터 삽입.

실행: python -m app.init_db
"""

from app import models
from app.db import Base, SessionLocal, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(models.Seat).count() == 0:
            seats = [
                models.Seat(id="a1", label="A1", capacity=2, position_label=None),
                models.Seat(id="a2", label="A2", capacity=2, position_label=None),
                models.Seat(id="a3", label="A3", capacity=4, position_label="창가 자리"),
                models.Seat(id="b1", label="B1", capacity=2, position_label=None),
                models.Seat(id="b2", label="B2", capacity=2, position_label=None),
                models.Seat(id="b3", label="B3", capacity=4, position_label=None),
            ]
            db.add_all(seats)

        if db.query(models.Shop).count() == 0:
            shops = [
                models.Shop(
                    id="makgeolli-gyebo",
                    name="막걸리계보",
                    category="bar",
                    sort_order=1,
                ),
                models.Shop(
                    id="jojunyoung",
                    name="조준영 목공방",
                    category="craft",
                    sort_order=2,
                ),
            ]
            db.add_all(shops)

        db.commit()
    finally:
        db.close()

    print("DB initialized: app.db")


if __name__ == "__main__":
    init_db()
