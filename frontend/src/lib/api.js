// API 클라이언트 — 백엔드 실 호출 (mock 교체)
// 단일 진실은 서버. 이 파일은 엔드포인트 배선(§5)만 담당하고 상태를 갖지 않는다.
// 계약 출처: context/scenarios/00-overview.md "API 정리" + context/db-schema.md.

import { getDeviceId } from './device.js'

// base URL은 환경변수로 주입. 로컬 개발 기본값은 FastAPI 기본 포트.
const BASE_URL = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// 백엔드 에러 봉투 { error: { code, message } } (D-24)를 감싼 예외.
// 화면은 code로 분기하고 message로 표시한다.
// body: 파싱된 에러 응답 전체. 일부 봉투는 봉투 밖에 추가 필드를 싣는다
//   (예: 409 ALREADY_RESERVED가 reservation_id를 함께 준다 — RSV-506).
//   화면이 그 값으로 복구하려면 code/message만으로는 부족해 원본 payload를 보관한다.
export class ApiError extends Error {
  constructor(code, message, status, body = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.body = body
  }
}

// 단일 요청 래퍼.
// - 모든 요청에 X-Device-Id 자동 부착 (D-07)
// - credentials: 'include' — 관리자 HttpOnly 세션 쿠키(D-21)가 흐르도록 항상 포함
// - JSON 기본, isForm이면 multipart(FormData) — Content-Type은 브라우저가 boundary와 함께 설정
// - 비-2xx면 에러 봉투를 파싱해 ApiError로 throw
async function apiFetch(path, { method = 'GET', body, headers = {}, isForm = false } = {}) {
  const finalHeaders = {
    'X-Device-Id': getDeviceId(),
    ...headers,
  }

  let finalBody
  if (isForm) {
    finalBody = body // FormData 그대로. Content-Type 지정 금지(boundary 자동)
  } else if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json'
    finalBody = JSON.stringify(body)
  }

  // credentials는 관리자 세션 쿠키(D-21)가 필요한 /api/admin/* 에만 include.
  // 익명 device-id 엔드포인트에 include를 붙이면 credentialed-CORS 제약에 걸려
  // (allow-origin이 정확 매칭 + allow-credentials 필요) 응답 처리가 막힌다.
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: finalHeaders,
    body: finalBody,
    credentials: path.startsWith('/api/admin') ? 'include' : 'same-origin',
  })

  // 204 No Content 등 바디 없는 성공 응답 처리.
  if (res.status === 204) return null

  let payload = null
  const text = await res.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      // JSON이 아닌 응답(프록시 오류 HTML 등). 정규화된 에러로 승격.
      if (!res.ok) throw new ApiError('UNKNOWN', text.slice(0, 200), res.status)
      return text
    }
  }

  if (!res.ok) {
    const err = payload?.error ?? {}
    // payload 전체를 body로 넘긴다: 봉투 밖 추가 필드(ALREADY_RESERVED의 reservation_id 등)를
    // 화면이 e.body로 읽어 복구할 수 있도록.
    throw new ApiError(err.code ?? 'UNKNOWN', err.message ?? '요청에 실패했어요.', res.status, payload)
  }

  return payload
}

// --- 사용자 API ---

// GET /api/status → { available_seats, today_visitors, is_full }
export function getStatus() {
  return apiFetch('/api/status')
}

// GET /api/shops → [{ id, name, category, is_active, sort_order }, ...]
export function getShops() {
  return apiFetch('/api/shops')
}

// POST /api/verify (multipart) → { status: 'approved'|'rejected'|'retry', token?, reason_code?, verification_id }
// image(File) 있으면 photo 경로, 없이 shopId만 있으면 manual 경로(즉시 승인, D-04).
export function verifyReceipt({ image, shopId } = {}) {
  const form = new FormData()
  if (image) form.append('image', image)
  if (shopId) form.append('shop_id', shopId)
  return apiFetch('/api/verify', { method: 'POST', body: form, isForm: true })
}

// GET /api/verify/status → 당일(KST) 인증 상태 (재진입 복원용, D-14). 인증 없으면 서버가 null/빈 상태.
export function getVerifyStatus() {
  return apiFetch('/api/verify/status')
}

// GET /api/seats → 백엔드는 [{ id, label, capacity, position_label, status }, ...] (status=available|taken|closed).
// 화면은 `state`라는 이름을 쓰므로 여기서 status→state로 정규화한다(anti-corruption layer).
// 백엔드가 단일 진실이라 status를 바꾸지 않고, 프론트 소비 이름만 여기서 맞춘다.
export async function getSeats() {
  const seats = await apiFetch('/api/seats')
  return Array.isArray(seats) ? seats.map((s) => ({ ...s, state: s.status })) : seats
}

// 좌석 리스트에서 seat id 하나를 찾는다(D-26). 좌석 id 대소문자 불일치를 흡수한다
// (QR은 소문자 'a3'를 운반하는데 서버가 'A3'로 줄 수도 있으므로). 순수 함수 — 테스트 대상.
export function findSeat(seats, seatId) {
  if (!Array.isArray(seats) || !seatId) return null
  const target = String(seatId).toLowerCase()
  return seats.find((s) => String(s.id).toLowerCase() === target) ?? null
}

// GET /api/seats에서 찍은 좌석 하나의 상태만 필터해 반환(D-26). 그리드 렌더용이 아님.
// 없으면(알 수 없는 seat id) null. state는 available|taken|closed(getSeats가 정규화).
export async function getSeatStatus(seatId) {
  if (!seatId) return null
  const seats = await getSeats()
  return findSeat(seats, seatId)
}

// POST /api/reserve → { reservation_id, seat, expires_at }. 선점당하면 409 SEAT_TAKEN.
export function reserve({ seatId, verifyToken }) {
  return apiFetch('/api/reserve', {
    method: 'POST',
    body: { seat_id: seatId, verify_token: verifyToken },
  })
}

// GET /api/reservations/:id → 내 예약 조회 (device-id 소유 검증, D-10).
export function getReservation(id) {
  return apiFetch(`/api/reservations/${id}`)
}

// DELETE /api/reservations/:id → 자리 비우기 (D-09).
export function cancelReservation(id) {
  return apiFetch(`/api/reservations/${id}`, { method: 'DELETE' })
}

// GET /api/guestbook?cursor= → 백엔드는 { entries, next_cursor } (cursor 기반 10개씩).
// 화면은 { items, next_cursor }를 기대하므로 entries→items로 정규화한다(anti-corruption layer).
// 각 entry 형태 { id, content, rating, shop_tags:[{shop_id,name}], created_at }는 그대로 통과.
export async function getGuestbook(cursor) {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  const res = await apiFetch(`/api/guestbook${qs}`)
  return { items: res.entries, next_cursor: res.next_cursor }
}

// POST /api/guestbook → 생성된 entry. content 필수, rating/shopTags 선택 (D-17·D-18).
export function postGuestbook({ content, rating = null, shopTags = [] }) {
  return apiFetch('/api/guestbook', {
    method: 'POST',
    body: { content, rating, shop_tags: shopTags },
  })
}

// --- 관리자 API (D-21·D-22) ---
// 인증은 HttpOnly 세션 쿠키. apiFetch가 credentials: 'include'로 자동 전달.

// POST /api/admin/login → 세션 쿠키 발급.
export function adminLogin(password) {
  return apiFetch('/api/admin/login', { method: 'POST', body: { password } })
}

// GET /api/admin/audit → 감사 큐 { items: [...] } (needs_audit=true & 미감사 목록, ADM-201).
export function getAudit() {
  return apiFetch('/api/admin/audit')
}

// POST /api/admin/verifications/:id/ok — "문제없음"(needs_audit=false 처리, ADM-211).
export function auditOk(id) {
  return apiFetch(`/api/admin/verifications/${id}/ok`, { method: 'POST' })
}

// POST /api/admin/verifications/:id/revoke — 어뷰징 무효화(REVOKED_BY_AUDIT + 연결 예약 해제, ADM-212).
export function auditRevoke(id) {
  return apiFetch(`/api/admin/verifications/${id}/revoke`, { method: 'POST' })
}

// GET /api/admin/reservations → active 예약 목록.
// 주: db-schema에는 DELETE만 명시. 목록 조회 엔드포인트는 백엔드 확인 필요.
export function adminListReservations() {
  return apiFetch('/api/admin/reservations')
}

// PATCH /api/admin/seats/:id — 좌석 열기/닫기 (is_open 변경, D-22 ②).
export function setSeatOpen(id, isOpen) {
  return apiFetch(`/api/admin/seats/${id}`, { method: 'PATCH', body: { is_open: isOpen } })
}

// DELETE /api/admin/reservations/:id — active 예약 수동 해제 (D-22 ③).
export function adminReleaseReservation(id) {
  return apiFetch(`/api/admin/reservations/${id}`, { method: 'DELETE' })
}

// DELETE /api/admin/guestbook/:id — 방명록 삭제 (D-22 ④).
export function deleteGuestbook(id) {
  return apiFetch(`/api/admin/guestbook/${id}`, { method: 'DELETE' })
}

// GET /api/admin/shops → { items: [...] } 전체 상점(비활성 포함). 공개 /api/shops는 활성만 주므로,
// 관리자가 비활성 상점을 보고 재활성화하려면 이 엔드포인트가 필요하다(is_active 키 포함).
export function adminGetShops() {
  return apiFetch('/api/admin/shops')
}

// POST /api/admin/shops — 상점 추가 (D-22 ⑤). 백엔드 ShopCreateBody는 snake_case + id/name/category/sort_order만
// 받는다(is_active는 서버가 항상 true로 설정하므로 보내지 않는다).
export function createShop({ id, name, category, sortOrder = 0 }) {
  return apiFetch('/api/admin/shops', {
    method: 'POST',
    body: { id, name, category, sort_order: sortOrder },
  })
}

// PATCH /api/admin/shops/:id — 상점 수정/비활성 (D-22 ⑤). 부분 패치.
export function updateShop(id, patch = {}) {
  const body = {}
  if (patch.name !== undefined) body.name = patch.name
  if (patch.category !== undefined) body.category = patch.category
  if (patch.sortOrder !== undefined) body.sort_order = patch.sortOrder
  if (patch.isActive !== undefined) body.is_active = patch.isActive
  return apiFetch(`/api/admin/shops/${id}`, { method: 'PATCH', body })
}

// GET /api/admin/stats → 당일 통계 (D-22 ⑥).
export function getStats() {
  return apiFetch('/api/admin/stats')
}

// --- DEPRECATED 호환 shim (Wave 2B가 교체) ---
// 기존 mock 화면(routes/*.svelte)이 아직 옛 함수명을 import 한다. 빌드를 통과시키기 위한
// 최소 스텁이며 실 로직이 없다. 2B 화면 에이전트가 위의 실 API로 각 호출부를 교체해야 한다.
const DEPRECATED = (name, real) => () => {
  throw new Error(`api.${name}()는 제거됐어요. api.${real}()를 쓰세요 (Wave 2B에서 교체).`)
}
export const getMyVerification = DEPRECATED('getMyVerification', 'getVerifyStatus + store.reconcileVerify')
export const getMyReservation = DEPRECATED('getMyReservation', 'store.reconcileReservation')
export const analyzeReceipt = DEPRECATED('analyzeReceipt', 'verifyReceipt')
export const confirmVerification = DEPRECATED('confirmVerification', 'verifyReceipt')
export const submitManualVerification = DEPRECATED('submitManualVerification', 'verifyReceipt({ shopId })')
export const reserveSeat = DEPRECATED('reserveSeat', 'reserve({ seatId, verifyToken })')
export const submitGuestbook = DEPRECATED('submitGuestbook', 'postGuestbook')
