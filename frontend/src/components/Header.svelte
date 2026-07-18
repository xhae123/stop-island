<script>
  // 셸 상단 고정 바 (§4). App.svelte에 단 한 번 마운트한다 — 화면은 자기 헤더를 심지 않는다.
  // 왼쪽: 루트가 아니면 back(브라우저 흐름 유지). 가운데: title 또는 브랜드. 오른쪽: 햄버거.
  // 드로어(NavBar) 열림 상태를 여기서 소유한다.
  import { pop, push, router } from 'svelte-spa-router'
  import NavBar from './NavBar.svelte'

  let { title = '' } = $props()

  let open = $state(false)

  // QR 진입 앱: 첫 화면은 항상 '/'. 루트가 아닐 때만 back 노출(§7).
  const showBack = $derived((router.location ?? '/') !== '/')
</script>

<header
  class="sticky top-0 z-50 flex items-center justify-between bg-header-bg px-4 py-3"
  style="padding-top: calc(0.75rem + env(safe-area-inset-top));"
>
  {#if showBack}
    <button
      class="flex h-8 w-8 items-center justify-center rounded-full hover:bg-white/10"
      onclick={() => pop()}
      aria-label="뒤로가기"
    >
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M12.5 15L7.5 10L12.5 5" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
  {:else}
    <div class="w-8"></div>
  {/if}

  <button class="text-sm font-semibold tracking-tight text-pause-white" onclick={() => push('/')}>
    {title || '멈춰, 섬!'}
  </button>

  <button
    class="flex h-8 w-8 items-center justify-center rounded-full bg-white/10"
    onclick={() => (open = true)}
    aria-label="메뉴 열기"
  >
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2 4H14M2 8H14M2 12H14" stroke="white" stroke-width="1.5" stroke-linecap="round" />
    </svg>
  </button>
</header>

<NavBar {open} onClose={() => (open = false)} />
