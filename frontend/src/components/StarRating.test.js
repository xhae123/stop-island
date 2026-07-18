import { describe, it, expect } from 'vitest'
import { toggleStar } from './StarRating.svelte'

// 별점 탭 토글 로직 (GB-201~203).
describe('toggleStar', () => {
  it('미선택(null)에서 4번째 별을 탭하면 4를 선택한다 (GB-201)', () => {
    expect(toggleStar(null, 4)).toBe(4)
  })

  it('다른 별을 탭하면 값이 그 별로 바뀐다 (GB-202)', () => {
    expect(toggleStar(4, 2)).toBe(2)
  })

  it('현재 선택된 별을 다시 탭하면 해제되어 null이 된다 (GB-203)', () => {
    expect(toggleStar(4, 4)).toBeNull()
  })

  it('경계: 1점/5점도 재탭 해제된다', () => {
    expect(toggleStar(1, 1)).toBeNull()
    expect(toggleStar(5, 5)).toBeNull()
  })
})
