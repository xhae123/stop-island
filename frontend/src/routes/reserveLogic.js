// 예약 화면 순수 로직 (테스트 대상). UI·부수효과 없음 — Reserve.svelte·Reservation.svelte가
// 소비한다. "값의 집은 하나" 원칙에 따라 표시 매핑/문구/시간 포맷을 한 곳에 모아 단위
// 테스트로 고정한다. (D-26: 좌석 그리드 선택 로직은 폐기 — 좌석은 찍은 QR로 정해진다.)

// 좌석 서브 라벨: 서버 상태(available|taken|closed)를 표시 문구로.
// - available → 정원 표기("2인석"/"4인석")
// - taken → "사용 중" / closed → "운영 중지" (문구 구분, RSV-201)
export function seatSubLabel(state, capacity) {
  if (state === 'taken') return '사용 중'
  if (state === 'closed') return '운영 중지'
  return `${capacity}인석`
}

// 찍은 자리가 쓸 수 없을 때의 안내 문구(D-26). 메인·예약 확정 양쪽이 쓴다.
export function seatUnavailableMessage(state) {
  if (state === 'closed') return '운영 중지된 자리예요'
  return '이 자리는 지금 사용 중이에요'
}

// 예약 확정 버튼 활성 조건(D-26): 찍은 자리가 available이고 확정 요청 중이 아닐 때만.
export function canConfirmSeat(state, confirming) {
  return state === 'available' && !confirming
}

// 409 SEAT_TAKEN 선점 시 문구(D-26). 그리드 재선택이 아니라 재스캔을 유도한다.
export const SEAT_TAKEN_MESSAGE = '아쉽지만 방금 다른 분이 먼저 예약했어요'
export const RESCAN_MESSAGE = '다른 빈 자리의 QR을 찍어주세요'

// 남은 시간(초) → "H시간 M분" / "M분". 음수·NaN은 0분으로.
// 초 단위는 표시하지 않는다(2시간 스케일에 초는 조급함만 — D-09).
export function formatRemaining(seconds) {
  const s = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h}시간 ${m}분` : `${m}분`
}
