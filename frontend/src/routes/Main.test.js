// 메인 현황 숫자 폴백 헬퍼 단위 테스트.
// 신호 나쁨/최초 실패 시 숫자 자리를 "—"로 비워 화면이 죽지 않게 한다(§6, MAIN-204/501).
import { describe, it, expect } from 'vitest'
import { formatCount } from './Main.svelte'

describe('formatCount', () => {
  it('숫자는 문자열로 그대로 표시', () => {
    expect(formatCount(4)).toBe('4')
    expect(formatCount(38)).toBe('38')
  })

  it('0석(만석)도 정상 표기 — 폴백 아님', () => {
    expect(formatCount(0)).toBe('0')
  })

  it('값 없음(null/undefined)은 "—" 폴백', () => {
    expect(formatCount(null)).toBe('—')
    expect(formatCount(undefined)).toBe('—')
  })
})
