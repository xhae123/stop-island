import { describe, it, expect } from 'vitest'
import { splitShops } from './ShopBadge.svelte'

// "+N개" 축약 경계 (그룹3 결정 · MENU-301/302/303).
const shopsOf = (n) =>
  Array.from({ length: n }, (_, i) => ({ id: `s${i}`, name: `상점${i}`, category: 'cafe' }))

describe('splitShops', () => {
  it('빈 목록: 배지 없음, extra 0 (MENU-303)', () => {
    expect(splitShops([], 3)).toEqual({ badges: [], extra: 0 })
  })

  it('max 이하(2개): 배지 2개, "+n개" 미표시 (MENU-302)', () => {
    const { badges, extra } = splitShops(shopsOf(2), 3)
    expect(badges).toHaveLength(2)
    expect(extra).toBe(0)
  })

  it('정확히 max개(3개): extra 0', () => {
    expect(splitShops(shopsOf(3), 3).extra).toBe(0)
  })

  it('max 초과(15개): 배지 3개 + extra 12 (MENU-301)', () => {
    const { badges, extra } = splitShops(shopsOf(15), 3)
    expect(badges).toHaveLength(3)
    expect(extra).toBe(12)
  })

  it('비배열 입력(null/undefined) 방어: 빈 결과', () => {
    expect(splitShops(null, 3)).toEqual({ badges: [], extra: 0 })
    expect(splitShops(undefined, 3)).toEqual({ badges: [], extra: 0 })
  })
})
