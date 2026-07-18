// 폴링 유틸 (D-12)
// 30초 간격 폴링. 백그라운드 탭 낭비를 막기 위해 document.hidden이면 일시정지하고,
// 탭 복귀(visibilitychange)·네트워크 복귀(online) 시 즉시 1회 재요청한다.
// 화면의 $effect에서 시작하고 cleanup에서 stop()을 호출하는 패턴으로 쓴다.

// fn: 매 tick 실행할 함수(보통 async 데이터 재요청). intervalMs 기본 30초.
// 반환: stop() — 인터벌·이벤트 리스너를 모두 해제.
export function createPoll(fn, intervalMs = 30000) {
  let timer = null

  // 숨김 상태면 tick을 건너뛴다(백그라운드 낭비 방지). 표시 상태에서만 실행.
  function tick() {
    if (document.hidden) return
    fn()
  }

  function start() {
    if (timer) return
    timer = setInterval(tick, intervalMs)
  }

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    document.removeEventListener('visibilitychange', onVisible)
    window.removeEventListener('online', onOnline)
  }

  // 탭이 다시 보이면 밀린 신선도를 즉시 1회 채운다.
  function onVisible() {
    if (!document.hidden) fn()
  }

  // 네트워크 복귀 시에도 즉시 1회.
  function onOnline() {
    fn()
  }

  document.addEventListener('visibilitychange', onVisible)
  window.addEventListener('online', onOnline)
  start()

  return stop
}
