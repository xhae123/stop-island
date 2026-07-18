import { describe, it, expect, vi, beforeEach } from 'vitest'

// api.js를 통째로 대체 — reconcile이 소비하는 서버 함수만 스텁.
// vi.mock 팩토리는 파일 최상단으로 hoist되므로, 참조 값도 vi.hoisted로 함께 끌어올린다.
const { getVerifyStatus, getReservation, ApiError } = vi.hoisted(() => {
  class ApiError extends Error {
    constructor(code, message, status) {
      super(message)
      this.code = code
      this.status = status
    }
  }
  return { getVerifyStatus: vi.fn(), getReservation: vi.fn(), ApiError }
})
vi.mock('./api.js', () => ({ getVerifyStatus, getReservation, ApiError }))

import {
  verify,
  saveVerify,
  loadVerify,
  reconcileVerify,
  reservation,
  saveReservationId,
  loadReservationId,
  reconcileReservation,
  seat,
  saveSeat,
  loadSeat,
  clearSeat,
  parseSeatParam,
} from './store.svelte.js'

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  verify.current = null
  reservation.id = null
  seat.id = null
})

describe('verify store', () => {
  it('save/load round-trips to the stop-island:verify key', () => {
    saveVerify({ token: 'x', verification_id: 'v1', status: 'approved', issued_date: '2026-07-18' })
    expect(JSON.parse(localStorage.getItem('stop-island:verify')).token).toBe('x')
    verify.current = null
    expect(loadVerify().verification_id).toBe('v1')
  })

  it('reconcileVerify overwrites local with server truth', async () => {
    saveVerify({ token: 'old', verification_id: 'old', status: 'approved', issued_date: '2026-07-18' })
    // 백엔드 GET /api/verify/status approved 실제 형태: { status, token, verification_id, method, shop_name }.
    getVerifyStatus.mockResolvedValue({
      status: 'approved',
      token: 'new',
      verification_id: 'v9',
      method: 'manual',
      shop_name: '막걸리계보',
    })
    const r = await reconcileVerify()
    expect(r.verification_id).toBe('v9')
    expect(JSON.parse(localStorage.getItem('stop-island:verify')).token).toBe('new')
    expect(verify.current.shop_name).toBe('막걸리계보')
  })

  it('reconcileVerify clears stale local when server reports none', async () => {
    saveVerify({ token: 'old', verification_id: 'old', status: 'approved' })
    // 백엔드는 당일 인증 없으면 { status: 'none' }을 준다(null 아님). verification_id 부재로 stale 정리.
    getVerifyStatus.mockResolvedValue({ status: 'none' })
    const r = await reconcileVerify()
    expect(r).toBeNull()
    expect(localStorage.getItem('stop-island:verify')).toBeNull()
  })
})

describe('seat store (D-26)', () => {
  it('save/load round-trips to the stop-island:seat key', () => {
    saveSeat('a3')
    expect(localStorage.getItem('stop-island:seat')).toBe('a3')
    seat.id = null
    expect(loadSeat()).toBe('a3')
    expect(seat.id).toBe('a3')
  })

  it('saveSeat overwrites — latest scan wins', () => {
    saveSeat('a3')
    saveSeat('b1')
    expect(seat.id).toBe('b1')
    expect(localStorage.getItem('stop-island:seat')).toBe('b1')
  })

  it('clearSeat removes the key and resets memory', () => {
    saveSeat('a3')
    clearSeat()
    expect(seat.id).toBeNull()
    expect(localStorage.getItem('stop-island:seat')).toBeNull()
  })

  it('loadSeat is null when absent', () => {
    expect(loadSeat()).toBeNull()
  })
})

describe('parseSeatParam — QR 부트 파싱 (D-26)', () => {
  it('해시 쿼리스트링에서 seat를 뽑는다', () => {
    expect(parseSeatParam('#/?seat=a3')).toBe('a3')
    expect(parseSeatParam('#/?seat=b1')).toBe('b1')
  })
  it('다른 파라미터와 섞여 있어도 seat만 뽑는다', () => {
    expect(parseSeatParam('#/?foo=1&seat=a3&bar=2')).toBe('a3')
  })
  it('공백은 trim, 빈 값은 null', () => {
    expect(parseSeatParam('#/?seat=%20a3%20')).toBe('a3')
    expect(parseSeatParam('#/?seat=')).toBeNull()
  })
  it('seat 파라미터·쿼리스트링·해시가 없으면 null', () => {
    expect(parseSeatParam('#/?other=1')).toBeNull()
    expect(parseSeatParam('#/')).toBeNull()
    expect(parseSeatParam('')).toBeNull()
    expect(parseSeatParam(null)).toBeNull()
  })
})

describe('reservation store', () => {
  it('save/load round-trips to the stop-island:reservation-id key', () => {
    saveReservationId('res-1')
    expect(localStorage.getItem('stop-island:reservation-id')).toBe('res-1')
    reservation.id = null
    expect(loadReservationId()).toBe('res-1')
  })

  it('reconcileReservation returns the active reservation', async () => {
    saveReservationId('res-1')
    // 백엔드 GET /api/reservations/:id 실제 형태: reservation_id + 중첩 seat.
    getReservation.mockResolvedValue({
      reservation_id: 'res-1',
      status: 'active',
      seat: { id: 'a1', label: 'A1', capacity: 2, position_label: null },
      expires_at: '2026-07-18T09:36:21',
      remaining_seconds: 7199,
    })
    const r = await reconcileReservation()
    expect(r.status).toBe('active')
    expect(r.reservation_id).toBe('res-1')
    expect(r.seat.label).toBe('A1')
    expect(localStorage.getItem('stop-island:reservation-id')).toBe('res-1')
  })

  it('reconcileReservation clears stale id on 404', async () => {
    saveReservationId('res-1')
    getReservation.mockRejectedValue(new ApiError('NOT_FOUND', '없어요', 404))
    const r = await reconcileReservation()
    expect(r).toBeNull()
    expect(localStorage.getItem('stop-island:reservation-id')).toBeNull()
  })

  it('reconcileReservation clears when reservation is expired', async () => {
    saveReservationId('res-1')
    getReservation.mockResolvedValue({ reservation_id: 'res-1', status: 'expired' })
    const r = await reconcileReservation()
    expect(r).toBeNull()
    expect(localStorage.getItem('stop-island:reservation-id')).toBeNull()
  })

  it('reconcileReservation keeps id on network error (not stale)', async () => {
    saveReservationId('res-1')
    getReservation.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(reconcileReservation()).rejects.toThrow()
    expect(localStorage.getItem('stop-island:reservation-id')).toBe('res-1')
  })
})
