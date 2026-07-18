// 셸 레벨 토스트 메커니즘 (§4·§6)
// 화면이 자기 자리에 토스트를 심지 않는다. App.svelte가 단일 <Toast>를 마운트하고
// 이 스토어의 상태를 바인딩한다. 화면은 showToast()만 호출한다.

// 반응형 컨테이너. App의 Toast 마운트가 구독한다.
export const toast = $state({ message: '', kind: 'info', visible: false })

let timer = null

// message를 kind(info|error)로 duration(ms) 동안 표시. 2~3초 자동 소멸(§9).
export function showToast(message, kind = 'info', duration = 2500) {
  toast.message = message
  toast.kind = kind
  toast.visible = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    toast.visible = false
  }, duration)
}

export function hideToast() {
  toast.visible = false
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}
