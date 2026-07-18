"""Wave-0 스모크 테스트 — 하네스가 살아있는지 + 스키마/시드 검증."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import Reservation, Seat, Verification
from app.reservations_core import expire_stale, seat_status


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_tables_created(db_session):
    # 모든 도메인 테이블이 생성됐는지 확인.
    inspector = inspect(db_session.get_bind())
    tables = set(inspector.get_table_names())
    expected = {
        "shops",
        "seats",
        "verifications",
        "reservations",
        "guestbook_entries",
        "guestbook_shop_tags",
    }
    assert expected.issubset(tables)


def test_seed_has_six_seats(db_session):
    seats = db_session.query(Seat).all()
    assert len(seats) == 6
    assert {s.id for s in seats} == {"a1", "a2", "a3", "b1", "b2", "b3"}


def test_partial_unique_index_exists(db_session):
    # D-06 부분 유니크 인덱스가 실제로 생성됐는지 확인.
    inspector = inspect(db_session.get_bind())
    index_names = {ix["name"] for ix in inspector.get_indexes("verifications")}
    assert "uq_verif_device_day_approved" in index_names


def _make_token(db_session, token: str, device_id: str = "test-device") -> str:
    # 예약은 verify_token FK가 있으므로(PRAGMA foreign_keys=ON) 토큰 발급 인증이 먼저 있어야 한다.
    db_session.add(
        Verification(
            device_id=device_id,
            method="manual",
            status="approved",
            needs_audit=True,
            token=token,
            verify_date="2026-07-18",
            verified_at=datetime.utcnow(),
        )
    )
    db_session.commit()
    return token


def _add_reservation(db_session, seat_id, token, *, minutes, device_id="test-device"):
    # minutes>0이면 미래 만료(active 유지), <0이면 과거 만료(만료 대상).
    now = datetime.utcnow()
    db_session.add(
        Reservation(
            seat_id=seat_id,
            verify_token=token,
            device_id=device_id,
            status="active",
            reserved_at=now,
            expires_at=now + timedelta(minutes=minutes),
        )
    )
    db_session.commit()


def test_reservation_partial_unique_index_exists(db_session):
    inspector = inspect(db_session.get_bind())
    index_names = {ix["name"] for ix in inspector.get_indexes("reservations")}
    assert "uq_reservation_seat_active" in index_names


def test_two_active_reservations_same_seat_raise(db_session):
    # 좌석당 active 예약 최대 1건 — DB 레벨 방어(RSV-502/SYS-401).
    _make_token(db_session, "tok-a", device_id="dev-a")
    _make_token(db_session, "tok-b", device_id="dev-b")
    _add_reservation(db_session, "a1", "tok-a", minutes=120, device_id="dev-a")

    with pytest.raises(IntegrityError):
        _add_reservation(db_session, "a1", "tok-b", minutes=120, device_id="dev-b")
    db_session.rollback()


def test_expire_stale_flips_past_reservation_and_frees_seat(db_session):
    # 과거 만료된 active 예약은 expire_stale 후 'expired'로 바뀌고 좌석은 'available'로 읽힌다.
    _make_token(db_session, "tok-old")
    _add_reservation(db_session, "a1", "tok-old", minutes=-1)

    flipped = expire_stale(db_session)
    assert flipped == 1

    a1 = next(s for s in seat_status(db_session) if s["id"] == "a1")
    assert a1["status"] == "available"
