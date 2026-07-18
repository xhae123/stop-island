<script>
  // 햄버거 드로어 (§8, MAIN-403/404). 항목은 메인/메뉴/방명록 3개.
  // Header가 open/onClose로 제어한다(스스로 열림 상태를 갖지 않음).
  import { push, router } from 'svelte-spa-router'

  let { open = false, onClose } = $props()

  const navItems = [
    { path: '/', label: '메인' },
    { path: '/menu', label: '메뉴 선택' },
    { path: '/guestbook', label: '방명록' },
  ]

  function navigate(path) {
    onClose?.()
    push(path)
  }
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="fixed inset-0 z-40 bg-black/50" onclick={() => onClose?.()}></div>
  <nav class="fixed top-0 right-0 z-50 h-full w-64 bg-header-bg px-4 pt-16 shadow-xl">
    <button
      class="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full bg-white/10"
      onclick={() => onClose?.()}
      aria-label="닫기"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M4 4L12 12M12 4L4 12" stroke="white" stroke-width="1.5" stroke-linecap="round" />
      </svg>
    </button>
    <ul class="space-y-1">
      {#each navItems as item}
        <li>
          <button
            class="w-full rounded-lg px-4 py-3 text-left text-sm transition-colors {router.location === item.path ? 'bg-white/10 text-pause-white' : 'text-white/80 hover:bg-white/5 hover:text-pause-white'}"
            onclick={() => navigate(item.path)}
          >
            {item.label}
          </button>
        </li>
      {/each}
    </ul>
  </nav>
{/if}
