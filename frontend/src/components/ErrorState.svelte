<script>
  // 보편 에러 + 재시도 (§6). 화면을 죽이지 않고 해당 영역에 문구 + [다시 시도].
  // message: 무엇이 잘못됐는지(§12). onRetry: 재시도 콜백(있을 때만 버튼 노출).
  import Button from './Button.svelte'

  let { message = '문제가 생겼어요. 잠시 후 다시 시도해주세요.', onRetry } = $props()
</script>

<div class="flex flex-col items-center justify-center gap-4 px-6 py-12 text-center">
  <p class="text-sm text-gray-600">{message}</p>
  {#if onRetry}
    <div class="w-full max-w-xs">
      <Button variant="ghost" onclick={onRetry}>다시 시도</Button>
    </div>
  {/if}
</div>
