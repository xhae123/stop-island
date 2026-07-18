<script>
  // 하단 시트 (§9). 맛집 선택 등 화면 내 선택 UI에 사용.
  // position: fixed라 어디서 마운트하든 뷰포트 전체를 덮는다(사실상 셸 레벨). 화면은
  // <BottomSheet open onClose>...children...</BottomSheet> 형태로 로컬에 렌더한다.
  // open: 표시 여부. onClose: 백드롭/닫기 콜백. children: 시트 내용 스니펫.
  import { fade, fly } from 'svelte/transition'

  let { open = false, onClose, children } = $props()

  // 모션 축소 설정이면 이동/페이드 시간을 0으로(§9·§11).
  const reduced =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const dur = reduced ? 0 : 250

  // 백드롭 클릭·ESC로 닫기.
  function onKeydown(e) {
    if (e.key === 'Escape') onClose?.()
  }
</script>

<svelte:window on:keydown={open ? onKeydown : undefined} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-[70] bg-black/50"
    transition:fade={{ duration: dur }}
    onclick={() => onClose?.()}
  ></div>
  <div
    class="fixed inset-x-0 bottom-0 z-[80] mx-auto max-w-[430px] rounded-t-2xl bg-pause-white p-4 shadow-xl"
    style="padding-bottom: calc(1rem + env(safe-area-inset-bottom));"
    transition:fly={{ y: 300, duration: dur }}
    role="dialog"
    aria-modal="true"
  >
    <!-- 드래그 핸들(장식) -->
    <div class="mx-auto mb-3 h-1 w-10 rounded-full bg-gray-300"></div>
    {@render children?.()}
  </div>
{/if}
