// @vitest-environment node
import { describe, it, expect } from 'vitest'
import { remainingLabel, formatExpiry, deriveStats, auditBadgeCount } from './Admin.svelte'

describe('remainingLabel', () => {
  it('만료됨 when diff <= 0', () => {
    expect(remainingLabel(0)).toBe('만료됨')
    expect(remainingLabel(-5000)).toBe('만료됨')
  })

  it('시간+분 표기 (1시간 이상)', () => {
    const ms = (1 * 60 + 58) * 60 * 1000
    expect(remainingLabel(ms)).toBe('남은 1시간 58분')
  })

  it('분만 표기 (1시간 미만)', () => {
    expect(remainingLabel(58 * 60 * 1000)).toBe('남은 58분')
  })

  it('초는 버림 (floor)', () => {
    expect(remainingLabel(59 * 1000)).toBe('남은 0분')
  })
})

describe('formatExpiry', () => {
  it('빈 입력이면 빈 문자열', () => {
    expect(formatExpiry(null)).toBe('')
    expect(formatExpiry(undefined)).toBe('')
    expect(formatExpiry('not-a-date')).toBe('')
  })

  it('절대시각(KST) + 남은시간을 결합', () => {
    const now = Date.parse('2026-07-18T05:00:00Z') // 14:00 KST
    const expires = '2026-07-18T06:58:00Z' // 15:58 KST, +1h58m
    const out = formatExpiry(expires, now)
    expect(out).toContain('15:58까지')
    expect(out).toContain('남은 1시간 58분')
  })
})

describe('deriveStats', () => {
  it('null 입력에도 0으로 채운 4개 카드', () => {
    const cards = deriveStats(null)
    expect(cards).toHaveLength(4)
    expect(cards.map(c => c.key)).toEqual(['visitors', 'verification', 'audit', 'seats'])
    expect(cards.find(c => c.key === 'audit').value).toBe('0')
  })

  it('백엔드 실제 stats 응답(중첩) 매핑', () => {
    // GET /api/admin/stats 라이브 캡처 형태:
    // { date, today_visitors, verifications:{approved,rejected,needs_audit}, seats:{available,open_total,total} }
    const raw = {
      date: '2026-07-18',
      today_visitors: 12,
      verifications: { approved: 12, rejected: 3, needs_audit: 2 },
      seats: { available: 2, open_total: 6, total: 6 },
    }
    const cards = deriveStats(raw)
    const byKey = Object.fromEntries(cards.map(c => [c.key, c.value]))
    expect(byKey.visitors).toBe('12')
    expect(byKey.verification).toBe('승인 12 · 거부 3')
    expect(byKey.audit).toBe('2')
    expect(byKey.seats).toBe('2 / 6')
  })

  it('audit 카드는 감사 탭으로 이동 가능', () => {
    const audit = deriveStats(null).find(c => c.key === 'audit')
    expect(audit.tab).toBe('audit')
  })
})

describe('auditBadgeCount', () => {
  it('감사 목록이 로드됐으면 그 길이', () => {
    expect(auditBadgeCount([{ id: 1 }, { id: 2 }], { verifications: { needs_audit: 9 } })).toBe(2)
    expect(auditBadgeCount([], { verifications: { needs_audit: 9 } })).toBe(0)
  })

  it('미로드(null)면 통계값(중첩) 폴백', () => {
    expect(auditBadgeCount(null, { verifications: { needs_audit: 3 } })).toBe(3)
    expect(auditBadgeCount(null, null)).toBe(0)
  })
})
