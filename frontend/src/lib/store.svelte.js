// 공유 상태 스토어 (Svelte 5 universal reactivity)
// localStorage 표준 규약(00-overview.md §localStorage)을 코드에 강제한다.
// 원칙: 단일 진실은 항상 서버. localStorage는 캐시일 뿐이며, 불일치 시 서버 값으로 덮고
// stale 키는 지운다. reconcile* 함수가 그 "서버 확정" 경로다.

import { getVerifyStatus, getReservation, ApiError } from './api.js'

const VERIFY_KEY = 'stop-island:verify'
const RESERVATION_KEY = 'stop-island:reservation-id'
const SEAT_KEY = 'stop-island:seat'

// 반응형 컨테이너: 객체 참조는 고정, 내부 속성만 갱신해 모듈 간 반응성을 유지한다.
// 화면은 verify.current / reservation.id / seat.id 를 읽으면 자동 구독된다.
export const verify = $state({ current: null })
export const reservation = $state({ id: null })
export const seat = $state({ id: null })

// --- verify ({ token?, verification_id, status, issued_date, shop_name? }) ---

// localStorage → 메모리. 파싱 실패/부재 시 null.
export function loadVerify() {
  try {
    const raw = localStorage.getItem(VERIFY_KEY)
    verify.current = raw ? JSON.parse(raw) : null
  } catch {
    verify.current = null
  }
  return verify.current
}

export function saveVerify(v) {
  verify.current = v
  localStorage.setItem(VERIFY_KEY, JSON.stringify(v))
}

export function clearVerify() {
  verify.current = null
  localStorage.removeItem(VERIFY_KEY)
}

// 서버 확정: GET /api/verify/status로 당일 인증 상태를 받아 로컬을 덮어쓴다.
// 서버가 유효 인증을 안 주면(로컬만 남은 stale) 지운다.
export async function reconcileVerify() {
  const server = await getVerifyStatus()
  // 서버가 당일 인증 없음을 응답(null/빈 객체)하면 로컬 stale 제거.
  if (!server || !server.verification_id) {
    clearVerify()
    return null
  }
  // issued_date 표준 키. 서버가 verify_date로 줄 수도 있어 폴백 허용(계약 확정 시 정리).
  const normalized = {
    token: server.token,
    verification_id: server.verification_id,
    status: server.status,
    issued_date: server.issued_date ?? server.verify_date,
    shop_name: server.shop_name,
  }
  saveVerify(normalized)
  return normalized
}

// --- seat (id 문자열, D-26) ---
// 좌석별 QR로 결정되는 "찍은 자리". 그리드 선택은 폐기 — 값의 집은 이 키 하나다.
// 최신 스캔이 덮어쓴다(saveSeat). 예약 흐름(메인 맥락·확정)이 이 값을 읽는다.

// QR 부트 파싱: 해시 쿼리스트링에서 seat 파라미터를 뽑는다. "#/?seat=a3" → "a3".
// 순수 함수(부수효과 없음) — App 부트가 window.location.hash를 넘겨 호출한다.
export function parseSeatParam(hash) {
  if (!hash) return null
  const q = hash.indexOf('?')
  if (q === -1) return null
  const raw = new URLSearchParams(hash.slice(q + 1)).get('seat')
  if (!raw) return null
  const trimmed = raw.trim()
  return trimmed || null
}

export function loadSeat() {
  seat.id = localStorage.getItem(SEAT_KEY) || null
  return seat.id
}

export function saveSeat(id) {
  seat.id = id
  localStorage.setItem(SEAT_KEY, id)
}

export function clearSeat() {
  seat.id = null
  localStorage.removeItem(SEAT_KEY)
}

// --- reservation (id 문자열) ---

export function loadReservationId() {
  reservation.id = localStorage.getItem(RESERVATION_KEY) || null
  return reservation.id
}

export function saveReservationId(id) {
  reservation.id = id
  localStorage.setItem(RESERVATION_KEY, id)
}

export function clearReservation() {
  reservation.id = null
  localStorage.removeItem(RESERVATION_KEY)
}

// 서버 확정: 저장된 예약 id를 GET /api/reservations/:id로 재조회.
// 소유 아님(403)·없음(404)·만료/취소는 stale로 보고 로컬 id를 지운다.
// 네트워크 오류 등은 던져서 호출부가 offline 처리하도록 남긴다(로컬 유지).
export async function reconcileReservation() {
  const id = loadReservationId()
  if (!id) return null
  try {
    const r = await getReservation(id)
    // active 아니면(expired/cancelled) 더는 유효하지 않으므로 정리.
    if (!r || r.status !== 'active') {
      clearReservation()
      return null
    }
    return r
  } catch (e) {
    if (e instanceof ApiError && (e.status === 403 || e.status === 404 || e.code === 'TOKEN_EXPIRED')) {
      clearReservation()
      return null
    }
    throw e
  }
}
