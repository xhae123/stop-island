import { describe, it, expect } from 'vitest'
import { canPost, trimmedLength, appendPage, MAX_CONTENT } from './Guestbook.svelte'
import { formatRelativeTime } from '../components/GuestEntry.svelte'
import { toggleShopTag } from '../components/ShopMultiSelect.svelte'

// --- 상대시간 포맷 (GB-507) ---
describe('formatRelativeTime', () => {
  const now = new Date('2026-07-18T12:00:00Z').getTime()
  const ago = (sec) => new Date(now - sec * 1000).toISOString()

  it('1분 미만은 "방금 전" (경계 30초)', () => {
    expect(formatRelativeTime(ago(30), now)).toBe('방금 전')
    expect(formatRelativeTime(ago(59), now)).toBe('방금 전')
  })

  it('분 단위는 "N분 전"', () => {
    expect(formatRelativeTime(ago(60), now)).toBe('1분 전')
    expect(formatRelativeTime(ago(600), now)).toBe('10분 전')
  })

  it('시간 단위는 "N시간 전"', () => {
    expect(formatRelativeTime(ago(3 * 3600), now)).toBe('3시간 전')
  })

  it('하루 이상은 "N일 전"', () => {
    expect(formatRelativeTime(ago(2 * 86400), now)).toBe('2일 전')
  })

  it('잘못된 날짜는 "방금 전"으로 폴백', () => {
    expect(formatRelativeTime('not-a-date', now)).toBe('방금 전')
  })
})

// --- 글자수 카운터 & 게시 게이팅 (GB-101~105) ---
describe('canPost / trimmedLength', () => {
  it('빈 값은 게시 불가 (GB-102)', () => {
    expect(canPost('')).toBe(false)
  })

  it('공백·줄바꿈만은 trim 후 0자라 게시 불가 (GB-103)', () => {
    expect(trimmedLength('   \n  ')).toBe(0)
    expect(canPost('   \n  ')).toBe(false)
  })

  it('1자 이상이면 게시 가능 (GB-101)', () => {
    expect(canPost('오늘 여기서 쉬다 갑니다')).toBe(true)
  })

  it('경계: 정확히 500자는 게시 가능, 501자는 불가 (GB-104/105)', () => {
    expect(canPost('a'.repeat(MAX_CONTENT))).toBe(true)
    expect(canPost('a'.repeat(MAX_CONTENT + 1))).toBe(false)
  })
})

// --- 맛집 태그 리듀서 최대 5개 (GB-302/303/304) ---
describe('toggleShopTag', () => {
  const shop = (id) => ({ id, name: `상점${id}` })
  const five = [1, 2, 3, 4, 5].map(shop)

  it('미선택 상점을 추가하면 {id,name}만 담아 next에 넣는다 (GB-302)', () => {
    const r = toggleShopTag([], { id: 'a', name: '카페 A', category: 'cafe' }, 5)
    expect(r.rejected).toBe(false)
    expect(r.next).toEqual([{ id: 'a', name: '카페 A' }])
  })

  it('선택된 상점을 재탭하면 제거된다 (GB-304)', () => {
    const r = toggleShopTag(five, shop(3), 5)
    expect(r.rejected).toBe(false)
    expect(r.next.map((s) => s.id)).toEqual([1, 2, 4, 5])
  })

  it('6개째 추가는 거부되고 목록은 그대로다 (GB-303)', () => {
    const r = toggleShopTag(five, shop(6), 5)
    expect(r.rejected).toBe(true)
    expect(r.next).toBe(five)
  })

  it('5개 상태에서 이미 선택된 것 해제는 거부되지 않는다', () => {
    const r = toggleShopTag(five, shop(2), 5)
    expect(r.rejected).toBe(false)
    expect(r.next).toHaveLength(4)
  })
})

// --- cursor append 병합 (GB-504/506) ---
describe('appendPage', () => {
  const e = (id) => ({ id, content: `c${id}` })

  it('다음 페이지를 뒤에 이어 붙인다', () => {
    const merged = appendPage([e(1), e(2)], [e(3), e(4)])
    expect(merged.map((x) => x.id)).toEqual([1, 2, 3, 4])
  })

  it('id가 겹치는 항목은 중복 없이 걸러진다 (GB-506 커서 안정성 방어)', () => {
    const merged = appendPage([e(1), e(2)], [e(2), e(3)])
    expect(merged.map((x) => x.id)).toEqual([1, 2, 3])
  })

  it('incoming이 비거나 없어도 안전하다 (GB-505 마지막 페이지)', () => {
    expect(appendPage([e(1)], []).map((x) => x.id)).toEqual([1])
    expect(appendPage([e(1)], undefined).map((x) => x.id)).toEqual([1])
  })
})
