// device-id 관리 (D-07)
// 로그인 없는 익명 식별자. 최초 부트 시 1회 생성해 localStorage에 영구 보관하고,
// 모든 API 요청의 X-Device-Id 헤더로 재사용한다. 서버는 이 헤더가 없으면 400을 낸다.

const DEVICE_ID_KEY = 'stop-island:device-id'

// 왜 lazy-getter인가: 앱 어디서든 첫 호출 시점에 생성/영속을 보장.
// localStorage에 있으면 재사용, 없으면 새로 만들어 저장한다(create-once).
export function getDeviceId() {
  let id = localStorage.getItem(DEVICE_ID_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(DEVICE_ID_KEY, id)
  }
  return id
}
