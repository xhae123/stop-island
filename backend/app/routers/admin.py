"""관리자 원격 모니터링 라우터 — 06-admin.md(ADM-*) + 결정표(D-21, D-22, D-24).

D-22: 이것은 승인 큐가 아니라 **감사 큐**다. 사용자 플로우는 이미 즉시 완결됐고(D-00·D-05),
관리자는 뒤에서 정리만 한다. 따라서 대기 화면·실시간성은 없고, 라우트는 전부 조회 또는
멱등 정리 연산이다.

로그인(POST /api/admin/login)을 제외한 모든 라우트는 require_admin 세션 가드에 의존한다.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adminauth import (
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    create_session,
    get_admin_password,
    require_admin,
)
from app.db import get_db
from app.deps import raise_api
from app.models import GuestbookEntry, Reservation, Seat, Shop, Verification
from app.reservations_core import count_available, expire_stale
from app.timeutil import today_kst_str

router = APIRouter()


# ---------------------------------------------------------------------------
# 로그인 / 세션 (ADM-1xx, D-21)
# ---------------------------------------------------------------------------
class LoginBody(BaseModel):
    password: str


@router.post("/api/admin/login")
def login(body: LoginBody, response: Response) -> dict[str, Any]:
    # ADM-101/102: 단일 비밀번호 검증. 일치하면 HttpOnly 세션 쿠키(12시간)를 내려준다.
    if body.password != get_admin_password():
        raise_api(401, "INVALID_PASSWORD", "비밀번호가 올바르지 않아요.")

    token = create_session()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,  # JS에서 못 읽게(XSS로 세션 탈취 방지)
        max_age=int(SESSION_TTL.total_seconds()),
        samesite="lax",
        # secure=False: 로컬 개발·테스트(http)에서도 쿠키가 실리도록. 운영 HTTPS는
        # nginx 종단이므로 여기서 강제하지 않는다(배포 시 프록시가 처리).
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# 감사 큐 (ADM-2xx, D-22)
# ---------------------------------------------------------------------------
def _serialize_audit(v: Verification, seat_label: str | None) -> dict[str, Any]:
    """감사 카드 직렬화 — 운영진이 판단에 필요한 필드를 전부 싣는다(ADM-201).

    seat_label: 연결된 active 예약의 좌석 라벨(없으면 None → "예약 없음").
    """
    return {
        "id": v.id,
        "method": v.method,
        "image_url": v.image_url,
        "shop_id": v.shop_id,
        "reason_code": v.reason_code,
        "confidence": v.confidence,
        "ocr_store_name": v.ocr_store_name,
        "ocr_date": v.ocr_date,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "verified_at": v.verified_at.isoformat() if v.verified_at else None,
        # active 예약이 있으면 좌석 라벨, 없으면 None. 프론트가 "예약 없음"으로 렌더.
        "reservation": {"seat_label": seat_label} if seat_label else None,
    }


@router.get("/api/admin/audit", dependencies=[Depends(require_admin)])
def audit_queue(db: Session = Depends(get_db)) -> dict[str, Any]:
    # ADM-201/202/702: 미감사(needs_audit=1 AND audited_at IS NULL) 건을 오래된 순으로.
    # "오늘" 필터가 아니라 미처리 필터 — 어제 건도 남는다(ADM-702).
    rows = (
        db.query(Verification)
        .filter(Verification.needs_audit.is_(True), Verification.audited_at.is_(None))
        .order_by(Verification.created_at.asc(), Verification.id.asc())
        .all()
    )

    # 연결된 active 예약(verify_token 기준)의 좌석 라벨을 한 번에 모은다(N+1 방지).
    tokens = [v.token for v in rows if v.token]
    seat_label_by_token: dict[str, str] = {}
    if tokens:
        joined = (
            db.query(Reservation.verify_token, Seat.label)
            .join(Seat, Seat.id == Reservation.seat_id)
            .filter(
                Reservation.verify_token.in_(tokens),
                Reservation.status == "active",
            )
            .all()
        )
        seat_label_by_token = {token: label for token, label in joined}

    items = [
        _serialize_audit(v, seat_label_by_token.get(v.token) if v.token else None)
        for v in rows
    ]
    return {"items": items}


def _fetch_pending_verification(db: Session, verification_id: str) -> Verification:
    """감사 대상 verification을 조회한다. 없으면 404. (감사 상태 판정은 호출부의 조건부 UPDATE가 담당)"""
    v = db.get(Verification, verification_id)
    if v is None:
        raise_api(404, "NOT_FOUND", "존재하지 않는 인증이에요.")
    return v


@router.post(
    "/api/admin/verifications/{verification_id}/ok",
    dependencies=[Depends(require_admin)],
)
def audit_ok(verification_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    # ADM-211: 문제없음 → needs_audit=0, audited_at 기록. status/token/예약은 불변.
    _fetch_pending_verification(db, verification_id)

    # 조건부 UPDATE가 동시성 관문이다(ADM-213/214): needs_audit=1 AND audited_at IS NULL인
    # 행만 갱신된다. 먼저 도착한 요청만 rowcount=1, 나중 요청은 0 → 409.
    updated = (
        db.query(Verification)
        .filter(
            Verification.id == verification_id,
            Verification.needs_audit.is_(True),
            Verification.audited_at.is_(None),
        )
        .update(
            {"needs_audit": False, "audited_at": datetime.utcnow()},
            synchronize_session=False,
        )
    )
    if updated == 0:
        db.rollback()
        raise_api(409, "ALREADY_PROCESSED", "다른 운영진이 이미 처리했어요.")
    db.commit()
    return {"ok": True}


@router.post(
    "/api/admin/verifications/{verification_id}/revoke",
    dependencies=[Depends(require_admin)],
)
def audit_revoke(verification_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    # ADM-212: 어뷰징 무효화 → 단일 트랜잭션으로
    #   ① verification을 rejected + REVOKED_BY_AUDIT + audited_at (토큰 무효)
    #   ② 연결된 active 예약을 cancelled (03 VF-504)
    v = _fetch_pending_verification(db, verification_id)
    token = v.token  # 조건부 UPDATE 전에 토큰을 확보(값은 불변)

    # ① 조건부 UPDATE — ADM-213 동시성 관문. needs_audit=1 AND audited_at IS NULL만.
    updated = (
        db.query(Verification)
        .filter(
            Verification.id == verification_id,
            Verification.needs_audit.is_(True),
            Verification.audited_at.is_(None),
        )
        .update(
            {
                "status": "rejected",
                "reason_code": "REVOKED_BY_AUDIT",
                "needs_audit": False,
                "audited_at": datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        db.rollback()
        raise_api(409, "ALREADY_PROCESSED", "다른 운영진이 이미 처리했어요.")

    # ② 연결된 active 예약 해제. 같은 트랜잭션이라 commit 한 번으로 원자적이다.
    if token:
        db.query(Reservation).filter(
            Reservation.verify_token == token,
            Reservation.status == "active",
        ).update({"status": "cancelled"}, synchronize_session=False)

    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 좌석 관리 (ADM-3xx)
# ---------------------------------------------------------------------------
class SeatToggleBody(BaseModel):
    is_open: bool


@router.patch("/api/admin/seats/{seat_id}", dependencies=[Depends(require_admin)])
def toggle_seat(
    seat_id: str, body: SeatToggleBody, db: Session = Depends(get_db)
) -> dict[str, Any]:
    # ADM-301/303: is_open 원격 토글. active 예약이 있어도 예약은 유지된다(신규만 차단, D-22).
    seat = db.get(Seat, seat_id)
    if seat is None:
        raise_api(404, "NOT_FOUND", "존재하지 않는 좌석이에요.")
    seat.is_open = body.is_open
    db.commit()
    return {"id": seat.id, "label": seat.label, "is_open": seat.is_open}


# ---------------------------------------------------------------------------
# 예약 관리 (ADM-4xx)
# ---------------------------------------------------------------------------
@router.get("/api/admin/reservations", dependencies=[Depends(require_admin)])
def list_active_reservations(db: Session = Depends(get_db)) -> dict[str, Any]:
    # ADM-401: active 예약 모니터링 목록. 조회 전 lazy 만료(D-11)를 돌려 목록이 정확하게.
    expire_stale(db)
    now = datetime.utcnow()

    # 예약 + 좌석 + (연결된) verification을 한 번에 join한다(N+1 방지).
    # verify_token → verifications.token 아우터 조인 — 토큰이 있으면 method/shop/needs_audit를 붙인다.
    rows = (
        db.query(Reservation, Seat, Verification, Shop)
        .join(Seat, Seat.id == Reservation.seat_id)
        .outerjoin(Verification, Verification.token == Reservation.verify_token)
        .outerjoin(Shop, Shop.id == Verification.shop_id)
        .filter(Reservation.status == "active")
        .order_by(Reservation.expires_at.asc())  # 곧 비는 순
        .all()
    )

    items: list[dict[str, Any]] = []
    for reservation, seat, verification, shop in rows:
        remaining = int((reservation.expires_at - now).total_seconds())
        items.append(
            {
                "reservation_id": reservation.id,
                "seat_id": seat.id,
                "seat_label": seat.label,
                "capacity": seat.capacity,
                "position_label": seat.position_label,
                "expires_at": reservation.expires_at.isoformat(),
                # 음수 방지: 만료 스윕과 조회 사이 미세 시차로 음수가 나올 수 있어 0으로 클램프.
                "remaining_seconds": max(0, remaining),
                # 감사 판단 보조: 연결된 인증의 method/상점/감사 플래그. device_id는 노출하지 않는다(프라이버시).
                "method": verification.method if verification else None,
                "shop_id": verification.shop_id if verification else None,
                "shop_name": shop.name if shop else None,
                "needs_audit": bool(verification.needs_audit) if verification else False,
            }
        )
    return {"items": items}


@router.delete(
    "/api/admin/reservations/{reservation_id}",
    dependencies=[Depends(require_admin)],
)
def release_reservation(
    reservation_id: str, db: Session = Depends(get_db)
) -> dict[str, Any]:
    # ADM-402/403: active → cancelled(행 보존, 이력 유지). 좌석은 즉시 빈자리로 계산된다.
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise_api(404, "NOT_FOUND", "존재하지 않는 예약이에요.")

    # 조건부 UPDATE로 active만 해제한다(ADM-403/405 멱등): expired/cancelled를 덮어쓰지 않는다.
    updated = (
        db.query(Reservation)
        .filter(Reservation.id == reservation_id, Reservation.status == "active")
        .update({"status": "cancelled"}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise_api(409, "NOT_ACTIVE", "이미 종료된 예약이에요.")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 방명록 관리 (ADM-5xx)
# ---------------------------------------------------------------------------
@router.delete(
    "/api/admin/guestbook/{entry_id}", dependencies=[Depends(require_admin)]
)
def delete_guestbook_entry(
    entry_id: str, db: Session = Depends(get_db)
) -> dict[str, Any]:
    # ADM-501/502: 엔트리 삭제. guestbook_shop_tags는 ON DELETE CASCADE로 함께 삭제된다
    # (PRAGMA foreign_keys=ON이 켜져 있어 DB가 처리).
    entry = db.get(GuestbookEntry, entry_id)
    if entry is None:
        raise_api(404, "NOT_FOUND", "이미 삭제된 글이에요.")
    db.delete(entry)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 상점 관리 (ADM-6xx)
# ---------------------------------------------------------------------------
class ShopCreateBody(BaseModel):
    id: str  # 슬러그. 참조 무결성 때문에 생성 후 수정 불가(ADM-602)
    name: str
    category: str
    sort_order: int = 0


class ShopUpdateBody(BaseModel):
    # 부분 수정 — 슬러그(id)는 받지 않는다(ADM-602: 참조 무결성).
    name: str | None = None
    category: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


@router.get("/api/admin/shops", dependencies=[Depends(require_admin)])
def list_all_shops(db: Session = Depends(get_db)) -> dict[str, Any]:
    # ADM-6xx: 관리자용 상점 목록. 공개 /api/shops와 달리 비활성(is_active=false)까지 전부 내려준다.
    # 왜 별도 엔드포인트인가: 공개 목록은 is_active=true만 노출하므로, 비활성 상점을 다시
    # 활성화하려면 관리자가 그 존재 자체를 볼 수 있어야 한다(공개 목록으로는 도달 불가).
    shops = db.query(Shop).order_by(Shop.sort_order, Shop.id).all()
    return {
        "items": [
            {
                "id": shop.id,
                "name": shop.name,
                "category": shop.category,
                "sort_order": shop.sort_order,
                "is_active": shop.is_active,
            }
            for shop in shops
        ]
    }


@router.post("/api/admin/shops", status_code=201, dependencies=[Depends(require_admin)])
def create_shop(body: ShopCreateBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    # ADM-601/603: 상점 추가(is_active=true 기본). 슬러그 중복이면 409.
    if db.get(Shop, body.id) is not None:
        raise_api(409, "SHOP_ID_TAKEN", "이미 있는 상점 ID예요.")
    shop = Shop(
        id=body.id,
        name=body.name,
        category=body.category,
        sort_order=body.sort_order,
        is_active=True,
    )
    db.add(shop)
    db.commit()
    return {"id": shop.id, "name": shop.name, "is_active": shop.is_active}


@router.patch("/api/admin/shops/{shop_id}", dependencies=[Depends(require_admin)])
def update_shop(
    shop_id: str, body: ShopUpdateBody, db: Session = Depends(get_db)
) -> dict[str, Any]:
    # ADM-602/604: 이름/카테고리/정렬/활성 수정(소프트 스위치). 슬러그는 불변.
    shop = db.get(Shop, shop_id)
    if shop is None:
        raise_api(404, "NOT_FOUND", "존재하지 않는 상점이에요.")
    if body.name is not None:
        shop.name = body.name
    if body.category is not None:
        shop.category = body.category
    if body.sort_order is not None:
        shop.sort_order = body.sort_order
    if body.is_active is not None:
        shop.is_active = body.is_active
    db.commit()
    return {
        "id": shop.id,
        "name": shop.name,
        "category": shop.category,
        "sort_order": shop.sort_order,
        "is_active": shop.is_active,
    }


# ---------------------------------------------------------------------------
# 당일 통계 (ADM-7xx, D-22)
# ---------------------------------------------------------------------------
@router.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    # ADM-701/702: 전부 당일(KST) 기준. 조회 시 lazy 만료(D-11)를 먼저 돌려 빈자리 정확도 확보.
    expire_stale(db)
    today = today_kst_str()

    # 오늘 인증: verify_date(=판정 KST 날짜)로 필터한다(created_at UTC가 아니라, D-01).
    approved_today = (
        db.query(Verification)
        .filter(Verification.verify_date == today, Verification.status == "approved")
        .count()
    )
    rejected_today = (
        db.query(Verification)
        .filter(Verification.verify_date == today, Verification.status == "rejected")
        .count()
    )
    # 미감사: 날짜 무관 감사 큐 크기(ADM-702 — 어제 건도 남는다). 통계 카드 탭 → 감사 탭 배지와 일치.
    needs_audit_count = (
        db.query(Verification)
        .filter(Verification.needs_audit.is_(True), Verification.audited_at.is_(None))
        .count()
    )

    open_total = db.query(Seat).filter(Seat.is_open.is_(True)).count()
    total_seats = db.query(Seat).count()
    available = count_available(db)

    return {
        "date": today,
        "today_visitors": approved_today,  # D-20: 당일 approved 수 = 방문자 수
        "verifications": {
            "approved": approved_today,
            "rejected": rejected_today,
            "needs_audit": needs_audit_count,
        },
        "seats": {
            "available": available,
            "open_total": open_total,
            "total": total_seats,
        },
    }
