import { describe, it, expect, beforeEach } from 'vitest'
import { getDeviceId } from './device.js'

const KEY = 'stop-island:device-id'

describe('getDeviceId', () => {
  beforeEach(() => localStorage.clear())

  it('creates a uuid once and persists it', () => {
    expect(localStorage.getItem(KEY)).toBeNull()
    const id = getDeviceId()
    expect(id).toMatch(/^[0-9a-f-]{36}$/i)
    expect(localStorage.getItem(KEY)).toBe(id)
  })

  it('reuses the same id on subsequent calls', () => {
    const first = getDeviceId()
    const second = getDeviceId()
    expect(second).toBe(first)
  })

  it('reuses an id already in localStorage', () => {
    localStorage.setItem(KEY, 'preexisting-id')
    expect(getDeviceId()).toBe('preexisting-id')
  })
})
