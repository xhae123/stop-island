// 테스트 환경 셋업. 이 jsdom 조합에서 localStorage.clear가 없어 테스트가 깨진다 —
// Map 기반 메모리 스토리지로 확정 교체한다(브라우저 Storage와 동일 API).
class MemStorage {
  #m = new Map()
  getItem(k) {
    return this.#m.has(k) ? this.#m.get(k) : null
  }
  setItem(k, v) {
    this.#m.set(k, String(v))
  }
  removeItem(k) {
    this.#m.delete(k)
  }
  clear() {
    this.#m.clear()
  }
  key(i) {
    return [...this.#m.keys()][i] ?? null
  }
  get length() {
    return this.#m.size
  }
}

Object.defineProperty(globalThis, 'localStorage', {
  value: new MemStorage(),
  configurable: true,
  writable: true,
})
