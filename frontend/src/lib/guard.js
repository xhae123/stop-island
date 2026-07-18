// 라우팅 가드 (§7, D-14)
// 이중 방어: 클라이언트 낙관 + 서버 확정. 여기(가드)는 낙관 판정만 한다 —
// localStorage의 verify 토큰으로 "일단 통과시킬지"를 동기 판단하고, 실제 유효성은
// 예약 API가 서버에서 최종 검증(만료면 TOKEN_EXPIRED 등)한다.
//
// svelte-spa-router의 conditions와 맞물린다: requireVerify가 false를 반환하면
// Router가 conditionsFailed 이벤트를 쏘고, App.svelte가 그걸 받아 /verify로 push 한다.

const VERIFY_KEY = 'stop-island:verify'
const SEAT_KEY = 'stop-island:seat'

// 클라이언트 시계를 KST로 강제(D-01 낙관 근사). en-CA 로케일은 'YYYY-MM-DD'를 준다.
// 서버가 최종 진실이므로 여기선 근사면 충분하다.
function todayKST() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date())
}

// 당일·미소진(approved + token 존재) verify 토큰이 로컬에 있는지.
export function hasValidVerify() {
  try {
    const raw = localStorage.getItem(VERIFY_KEY)
    if (!raw) return false
    const v = JSON.parse(raw)
    if (!v || v.status !== 'approved' || !v.token) return false
    // issued_date가 있으면 당일인지 확인. 없으면(구버전) 낙관 통과.
    if (v.issued_date && v.issued_date !== todayKST()) return false
    return true
  } catch {
    return false
  }
}

// svelte-spa-router conditions 함수: true 통과, false면 conditionsFailed → /verify 리다이렉트.
export function requireVerify() {
  return hasValidVerify()
}

// 찍은 좌석(D-26)이 로컬에 있는지. QR 부트가 stop-island:seat에 저장한다.
export function hasSeat() {
  try {
    return !!localStorage.getItem(SEAT_KEY)
  } catch {
    return false
  }
}

// svelte-spa-router conditions 함수: /reserve는 seat도 필수(D-26). 없으면 conditionsFailed.
export function requireSeat() {
  return hasSeat()
}

// 가드 실패 시 보낼 곳. App.svelte가 conditionsFailed 핸들러에서 사용.
// 토큰 없음 → /verify, seat 없음 → / (메인이 좌석 QR 스캔을 안내).
export const VERIFY_REDIRECT = '/verify'
export const SEAT_REDIRECT = '/'
