<script>
  // 예약 여정 전체를 관통하는 상단 프로그레스(D-26).
  // 셸에 한 번 마운트되어 라우트에 따라 단계가 차오른다 — 화면마다 재구현하지 않는다.
  // 자리(QR 스캔) → 인증 → 예약 → 착석.
  let { step = 0 } = $props() // 0 자리 · 1 인증 · 2 예약 · 3 착석
  const STEPS = ['자리', '인증', '예약', '착석']
</script>

<nav class="flex items-start px-5 py-3.5" aria-label="예약 진행 단계">
  {#each STEPS as label, i}
    <div class="flex w-12 shrink-0 flex-col items-center gap-1.5">
      <div
        class="flex h-[20px] w-[20px] items-center justify-center rounded-full text-[10px] font-black transition-colors
          {i < step
          ? 'bg-flow-black text-pause-white'
          : i === step
            ? 'bg-flow-black text-pause-white ring-2 ring-island-yellow ring-offset-1'
            : 'bg-gray-200 text-gray-400'}"
        aria-current={i === step ? 'step' : undefined}
      >
        {#if i < step}
          <svg class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fill-rule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0L3.3 9.7a1 1 0 011.4-1.4L8.5 12l6.8-6.7a1 1 0 011.4 0z" clip-rule="evenodd" />
          </svg>
        {:else}
          {i + 1}
        {/if}
      </div>
      <span
        class="text-[11px] font-bold {i === step ? 'text-flow-black' : i < step ? 'text-flow-black/55' : 'text-gray-400'}"
        >{label}</span
      >
    </div>

    {#if i < STEPS.length - 1}
      <!-- 커넥터: 다음 단계 전까지 채워짐. dot 세로 중심(약 10px)에 맞춰 정렬. -->
      <div class="mt-[9px] h-[3px] flex-1 rounded-full {i < step ? 'bg-flow-black' : 'bg-gray-200'}"></div>
    {/if}
  {/each}
</nav>
