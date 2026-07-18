import { describe, it, expect } from 'vitest'
import {
  seatSubLabel,
  seatUnavailableMessage,
  canConfirmSeat,
  formatRemaining,
  SEAT_TAKEN_MESSAGE,
  RESCAN_MESSAGE,
} from './reserveLogic.js'

describe('seatSubLabel — 좌석 상태→표시 문구 (RSV-201)', () => {
  it('available은 정원 표기', () => {
    expect(seatSubLabel('available', 2)).toBe('2인석')
    expect(seatSubLabel('available', 4)).toBe('4인석')
  })
  it('taken은 "사용 중"', () => {
    expect(seatSubLabel('taken', 2)).toBe('사용 중')
  })
  it('closed는 "운영 중지"', () => {
    expect(seatSubLabel('closed', 4)).toBe('운영 중지')
  })
})

describe('seatUnavailableMessage — 찍은 자리 비가용 안내 (D-26)', () => {
  it('taken은 "이 자리는 지금 사용 중이에요"', () => {
    expect(seatUnavailableMessage('taken')).toBe('이 자리는 지금 사용 중이에요')
  })
  it('closed는 "운영 중지된 자리예요"', () => {
    expect(seatUnavailableMessage('closed')).toBe('운영 중지된 자리예요')
  })
})

describe('canConfirmSeat — 확정 버튼 게이팅 (D-26)', () => {
  it('available이고 확정 중이 아니면 true', () => {
    expect(canConfirmSeat('available', false)).toBe(true)
  })
  it('확정 요청 중이면 false (연타 방지)', () => {
    expect(canConfirmSeat('available', true)).toBe(false)
  })
  it('taken/closed/null이면 false', () => {
    expect(canConfirmSeat('taken', false)).toBe(false)
    expect(canConfirmSeat('closed', false)).toBe(false)
    expect(canConfirmSeat(null, false)).toBe(false)
  })
})

describe('선점(409) 재스캔 문구 (D-26)', () => {
  it('그리드 재선택이 아니라 재스캔을 유도한다', () => {
    expect(SEAT_TAKEN_MESSAGE).toBe('아쉽지만 방금 다른 분이 먼저 예약했어요')
    expect(RESCAN_MESSAGE).toBe('다른 빈 자리의 QR을 찍어주세요')
  })
})

describe('formatRemaining — 남은 시간 포맷 (D-09)', () => {
  it('1시간 58분 = 7080초', () => {
    expect(formatRemaining(1 * 3600 + 58 * 60)).toBe('1시간 58분')
  })
  it('정확히 2시간', () => {
    expect(formatRemaining(2 * 3600)).toBe('2시간 0분')
  })
  it('1시간 미만은 분만 표기', () => {
    expect(formatRemaining(42 * 60)).toBe('42분')
    expect(formatRemaining(59)).toBe('0분')
  })
  it('0·음수·NaN은 0분', () => {
    expect(formatRemaining(0)).toBe('0분')
    expect(formatRemaining(-120)).toBe('0분')
    expect(formatRemaining(NaN)).toBe('0분')
  })
})
