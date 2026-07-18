import { describe, it, expect, vi, beforeEach } from 'vitest'

// device-id는 고정값으로 대체 — 헤더 부착만 검증.
vi.mock('./device.js', () => ({ getDeviceId: () => 'test-device-123' }))

import { getStatus, reserve, verifyReceipt, getSeats, getSeatStatus, findSeat, getGuestbook, adminLogin, ApiError } from './api.js'

function mockFetch(res) {
  const fn = vi.fn().mockResolvedValue(res)
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('apiFetch', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('attaches X-Device-Id and returns parsed json on 2xx', async () => {
    const fetchMock = mockFetch({
      status: 200,
      ok: true,
      text: async () => JSON.stringify({ available_seats: 3, today_visitors: 10, is_full: false }),
    })
    const data = await getStatus()
    expect(data).toEqual({ available_seats: 3, today_visitors: 10, is_full: false })

    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/status')
    expect(opts.headers['X-Device-Id']).toBe('test-device-123')
    // 익명 device-id 엔드포인트는 credentials를 붙이지 않는다(관리자 세션쿠키 전용).
    expect(opts.credentials).toBe('same-origin')
  })

  it('sends credentials only for /api/admin/* (session cookie)', async () => {
    const fetchMock = mockFetch({ status: 200, ok: true, text: async () => JSON.stringify({ ok: true }) })
    await adminLogin('pw')
    expect(fetchMock.mock.calls[0][1].credentials).toBe('include')
  })

  it('parses the error envelope into an ApiError (code + status)', async () => {
    mockFetch({
      status: 409,
      ok: false,
      text: async () => JSON.stringify({ error: { code: 'SEAT_TAKEN', message: '이미 예약된 자리예요.' } }),
    })
    const err = await reserve({ seatId: 'a1', verifyToken: 't' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('SEAT_TAKEN')
    expect(err.status).toBe(409)
    expect(err.message).toBe('이미 예약된 자리예요.')
  })

  it('sends JSON body with content-type for non-form requests', async () => {
    const fetchMock = mockFetch({ status: 200, ok: true, text: async () => JSON.stringify({ ok: 1 }) })
    await reserve({ seatId: 'a1', verifyToken: 'tok' })
    const [, opts] = fetchMock.mock.calls[0]
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(opts.body)).toEqual({ seat_id: 'a1', verify_token: 'tok' })
  })

  it('sends multipart FormData without JSON content-type for verifyReceipt', async () => {
    const fetchMock = mockFetch({ status: 200, ok: true, text: async () => JSON.stringify({ status: 'approved' }) })
    await verifyReceipt({ shopId: 'makgeolli-gyebo' })
    const [, opts] = fetchMock.mock.calls[0]
    expect(opts.body).toBeInstanceOf(FormData)
    expect(opts.headers['Content-Type']).toBeUndefined()
  })

  // 백엔드 GET /api/seats는 status 키(available|taken|closed)를 준다. 화면은 state를 쓰므로 정규화한다.
  it('getSeats normalizes backend status → state', async () => {
    mockFetch({
      status: 200,
      ok: true,
      text: async () =>
        JSON.stringify([
          { id: 'a1', label: 'A1', capacity: 2, position_label: null, status: 'available' },
          { id: 'a2', label: 'A2', capacity: 2, position_label: null, status: 'taken' },
        ]),
    })
    const seats = await getSeats()
    expect(seats.map((s) => s.state)).toEqual(['available', 'taken'])
    // 원본 status도 보존한다(파괴적 매핑 아님).
    expect(seats[0].status).toBe('available')
  })

  // D-26: 찍은 좌석 하나의 상태를 좌석 목록에서 필터한다(그리드 렌더 아님).
  it('findSeat resolves one seat from the list, case-insensitive', () => {
    const seats = [
      { id: 'a1', label: 'A1', state: 'available' },
      { id: 'a3', label: 'A3', state: 'taken' },
    ]
    expect(findSeat(seats, 'a3').label).toBe('A3')
    expect(findSeat(seats, 'A3').state).toBe('taken') // QR 소문자 vs 서버 대문자 흡수
    expect(findSeat(seats, 'zz')).toBeNull() // 알 수 없는 좌석
    expect(findSeat(null, 'a1')).toBeNull()
    expect(findSeat(seats, null)).toBeNull()
  })

  it('getSeatStatus fetches /api/seats and returns the scanned seat', async () => {
    mockFetch({
      status: 200,
      ok: true,
      text: async () =>
        JSON.stringify([
          { id: 'a1', label: 'A1', capacity: 2, position_label: null, status: 'available' },
          { id: 'a3', label: 'A3', capacity: 4, position_label: '창가 자리', status: 'available' },
        ]),
    })
    const s = await getSeatStatus('a3')
    expect(s.label).toBe('A3')
    expect(s.state).toBe('available') // getSeats가 status→state 정규화한 뒤 필터
    expect(s.position_label).toBe('창가 자리')
  })

  it('getSeatStatus returns null when seatId is absent', async () => {
    expect(await getSeatStatus(null)).toBeNull()
  })

  // 백엔드 GET /api/guestbook는 { entries, next_cursor }를 준다. 화면은 { items }를 기대한다.
  it('getGuestbook normalizes entries → items', async () => {
    mockFetch({
      status: 200,
      ok: true,
      text: async () =>
        JSON.stringify({
          entries: [
            {
              id: 'g1',
              content: '좋아요',
              rating: 5,
              shop_tags: [{ shop_id: 'makgeolli-gyebo', name: '막걸리계보' }],
              created_at: '2026-07-18T07:36:21',
            },
          ],
          next_cursor: 'abc',
        }),
    })
    const res = await getGuestbook()
    expect(res.items).toHaveLength(1)
    expect(res.items[0].shop_tags[0].name).toBe('막걸리계보')
    expect(res.next_cursor).toBe('abc')
  })

  // 409 ALREADY_RESERVED는 봉투 밖에 reservation_id를 실어준다(RSV-506). ApiError.body로 접근 가능해야 한다.
  it('attaches the full error payload to ApiError.body (ALREADY_RESERVED carries reservation_id)', async () => {
    mockFetch({
      status: 409,
      ok: false,
      text: async () =>
        JSON.stringify({
          error: { code: 'ALREADY_RESERVED', message: '이미 예약돼 있어요.' },
          reservation_id: 'res-42',
        }),
    })
    const err = await reserve({ seatId: 'a1', verifyToken: 't' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('ALREADY_RESERVED')
    expect(err.body.reservation_id).toBe('res-42')
  })
})
