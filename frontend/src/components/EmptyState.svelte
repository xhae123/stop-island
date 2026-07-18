<script>
  // 보편 빈 상태 (§6). "정상인데 데이터 0개" — 에러 아님.
  // message: 다음 행동을 유도하는 문구(§12). action: 선택 스니펫(버튼 등).
  let { message, action } = $props()
</script>

<div class="flex flex-col items-center justify-center gap-4 px-6 py-12 text-center">
  <p class="text-sm text-gray-500">{message}</p>
  {#if action}
    <div class="w-full max-w-xs">
      {@render action()}
    </div>
  {/if}
</div>
