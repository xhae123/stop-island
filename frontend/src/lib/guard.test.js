import { describe, it, expect, beforeEach } from 'vitest'
import { hasValidVerify, requireVerify, hasSeat, requireSeat } from './guard.js'

const KEY = 'stop-island:verify'
const SEAT_KEY = 'stop-island:seat'

function todayKST() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date())
}

describe('guard', () => {
  beforeEach(() => localStorage.clear())

  it('false when no verify token', () => {
    expect(requireVerify()).toBe(false)
  })

  it('true for an approved same-day token', () => {
    localStorage.setItem(KEY, JSON.stringify({ token: 't', status: 'approved', issued_date: todayKST() }))
    expect(requireVerify()).toBe(true)
  })

  it('false for an approved token issued on a different day', () => {
    localStorage.setItem(KEY, JSON.stringify({ token: 't', status: 'approved', issued_date: '2000-01-01' }))
    expect(hasValidVerify()).toBe(false)
  })

  it('false when status is not approved', () => {
    localStorage.setItem(KEY, JSON.stringify({ token: 't', status: 'rejected', issued_date: todayKST() }))
    expect(hasValidVerify()).toBe(false)
  })

  it('false when token field is missing', () => {
    localStorage.setItem(KEY, JSON.stringify({ status: 'approved', issued_date: todayKST() }))
    expect(hasValidVerify()).toBe(false)
  })

  it('false when localStorage holds corrupt json', () => {
    localStorage.setItem(KEY, '{not json')
    expect(hasValidVerify()).toBe(false)
  })
})

describe('seat guard (D-26)', () => {
  beforeEach(() => localStorage.clear())

  it('false when no seat stored', () => {
    expect(requireSeat()).toBe(false)
    expect(hasSeat()).toBe(false)
  })

  it('true when a seat is stored (찍은 QR)', () => {
    localStorage.setItem(SEAT_KEY, 'a3')
    expect(requireSeat()).toBe(true)
    expect(hasSeat()).toBe(true)
  })
})
