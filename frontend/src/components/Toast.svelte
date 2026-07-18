<script>
  // 일시 알림 (§6·§9). 전역 실패만 토스트로(인라인 우선 원칙).
  // 프레젠테이션 전용 — 표시 여부/타이머는 셸 스토어(lib/toast.svelte.js)가 관리한다.
  // kind: info(검정) | error(빨강 계열). 셸 폭(430px) 안에 하단 고정.
  let { message, kind = 'info' } = $props()

  const KINDS = {
    info: 'bg-flow-black text-pause-white',
    error: 'bg-red-600 text-pause-white',
  }
  const kindClass = $derived(KINDS[kind] ?? KINDS.info)
</script>

<div
  class="pointer-events-none fixed inset-x-0 bottom-0 z-[60] mx-auto flex max-w-[430px] justify-center px-4 pb-6"
  style="padding-bottom: calc(1.5rem + env(safe-area-inset-bottom));"
  role="status"
  aria-live="polite"
>
  <div class="pointer-events-auto rounded-xl px-4 py-3 text-sm font-medium shadow-lg {kindClass}">
    {message}
  </div>
</div>
