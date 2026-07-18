import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPoll } from './poll.js'

function setHidden(value) {
  Object.defineProperty(document, 'hidden', { value, configurable: true })
}

describe('createPoll', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('fires fn on each interval when visible (not immediately on start)', () => {
    setHidden(false)
    const fn = vi.fn()
    const stop = createPoll(fn, 1000)
    expect(fn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1000)
    expect(fn).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(2000)
    expect(fn).toHaveBeenCalledTimes(3)
    stop()
  })

  it('pauses ticks while document.hidden', () => {
    setHidden(true)
    const fn = vi.fn()
    const stop = createPoll(fn, 1000)
    vi.advanceTimersByTime(3000)
    expect(fn).not.toHaveBeenCalled()
    stop()
  })

  it('stop() clears the interval', () => {
    setHidden(false)
    const fn = vi.fn()
    const stop = createPoll(fn, 1000)
    stop()
    vi.advanceTimersByTime(5000)
    expect(fn).not.toHaveBeenCalled()
  })

  it('refires once on visibilitychange -> visible', () => {
    setHidden(false)
    const fn = vi.fn()
    const stop = createPoll(fn, 100000)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(fn).toHaveBeenCalledTimes(1)
    stop()
  })

  it('refires once on online', () => {
    setHidden(false)
    const fn = vi.fn()
    const stop = createPoll(fn, 100000)
    window.dispatchEvent(new Event('online'))
    expect(fn).toHaveBeenCalledTimes(1)
    stop()
  })
})
