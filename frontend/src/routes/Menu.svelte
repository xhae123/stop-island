<script>
  // 02 메뉴 선택 — 분기 화면 (§7 라우트 /menu, 가드 없음).
  // 두 갈래 카드는 라디오가 아니라 "탭 즉시 push"하는 내비게이션 아이템(D-16 · MENU-201/202).
  // 아래 참여 상점 배지 목록은 참고 정보 — 실패해도 카드 플로우는 정상 동작(J1.2-3).
  // Header/NavBar는 앱 셸(App.svelte)이 마운트한다 — 이 화면은 자기 헤더를 심지 않는다(§4).
  import { push } from 'svelte-spa-router'
  import { onMount, onDestroy } from 'svelte'
  import { getShops } from '../lib/api.js'
  import ShopBadge, { splitShops } from '../components/ShopBadge.svelte'
  import Skeleton from '../components/Skeleton.svelte'
  import EmptyState from '../components/EmptyState.svelte'
  import ErrorState from '../components/ErrorState.svelte'

  const MAX_BADGES = 3

  // 참여 상점 섹션의 요청 상태 (§6). 카드 내비게이션과 독립적이다.
  let loading = $state(true)
  let error = $state(false)
  let shops = $state([])

  // MENU-305: 응답 도착 전 이탈 시 뒤늦게 온 응답을 무시(unmount 후 상태 갱신·콘솔 에러 방지).
  let alive = true
  onDestroy(() => { alive = false })

  onMount(async () => {
    try {
      const data = await getShops()
      if (!alive) return
      shops = Array.isArray(data) ? data : []
    } catch {
      if (!alive) return
      error = true
    } finally {
      if (alive) loading = false
    }
  })

  // 상위 3개 배지 + "+n개" 축약 (그룹3 결정). 순수 함수는 ShopBadge에서 단위 테스트한다.
  const split = $derived(splitShops(shops, MAX_BADGES))

  // MENU-203: 카드 탭 즉시 push하되, 전환이 시작되면 후속 탭을 무시해 히스토리 중복 push를 막는다.
  let navigating = false
  function selectCard(path) {
    if (navigating) return
    navigating = true
    push(path)
  }
</script>

<section class="px-5 pt-6 pb-8">
  <h1 class="text-xl font-bold text-flow-black">무엇을 하시겠어요?</h1>
  <p class="mt-1 text-sm text-gray-500">이용 목적을 선택하세요</p>

  <!-- 두 갈래 카드 (탭 즉시 push, 라디오 아님). press 피드백은 active: 유틸리티로. -->
  <div class="mt-5 flex flex-col gap-3">
    <!-- 테이블 예약 → /verify (영수증 인증 선행) -->
    <button
      type="button"
      class="flex w-full items-center gap-4 rounded-2xl border border-gray-200 bg-white p-4 text-left transition-colors active:border-2 active:border-island-yellow active:bg-island-yellow-light"
      onclick={() => selectCard('/verify')}
      aria-label="이 자리 잡기 — 영수증 인증 후 예약 확정"
    >
      <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-island-yellow text-flow-black">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="4" y="6" width="16" height="3" rx="1" fill="currentColor" />
          <rect x="6" y="9" width="2" height="8" rx="0.5" fill="currentColor" />
          <rect x="16" y="9" width="2" height="8" rx="0.5" fill="currentColor" />
          <rect x="10" y="9" width="4" height="5" rx="0.5" fill="currentColor" opacity="0.4" />
        </svg>
      </span>
      <span class="min-w-0 flex-1">
        <span class="block text-base font-bold text-flow-black">이 자리 잡기</span>
        <span class="mt-0.5 block text-sm text-gray-500">영수증 인증 후 예약 확정</span>
      </span>
      <svg class="w-5 h-5 shrink-0 text-gray-400" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M7.5 5L12.5 10L7.5 15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <!-- 방명록 작성 → /guestbook (인증 불필요) -->
    <button
      type="button"
      class="flex w-full items-center gap-4 rounded-2xl border border-gray-200 bg-white p-4 text-left transition-colors active:border-2 active:border-island-yellow active:bg-island-yellow-light"
      onclick={() => selectCard('/guestbook')}
      aria-label="방명록 작성 — 후기 · 맛집 공유"
    >
      <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gray-100 text-flow-black">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M14.5 3.5L20.5 9.5L9 21H3V15L14.5 3.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M12 6L18 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          <path d="M3 21H21" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.4" />
        </svg>
      </span>
      <span class="min-w-0 flex-1">
        <span class="block text-base font-bold text-flow-black">방명록 작성</span>
        <span class="mt-0.5 block text-sm text-gray-500">후기 · 맛집 공유</span>
      </span>
      <svg class="w-5 h-5 shrink-0 text-gray-400" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M7.5 5L12.5 10L7.5 15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
  </div>

  <!-- 참여 상점 섹션 — 레이아웃 점프 방지 위해 실패/빈 목록에도 섹션은 유지(그룹3 결정). -->
  <div class="mt-6 rounded-2xl bg-gray-50 p-4">
    <p class="mb-3 text-sm font-medium text-gray-700">참여 상점</p>

    {#if loading}
      <div class="flex flex-wrap gap-2">
        {#each Array(3) as _}
          <Skeleton class="h-7 w-20 rounded-full" />
        {/each}
      </div>
    {:else if error}
      <!-- MENU-304: 재시도 버튼 없음(재진입/새로고침 시 재조회) -->
      <ErrorState message="참여 상점 정보를 불러오지 못했어요" />
    {:else if shops.length === 0}
      <!-- MENU-303 -->
      <EmptyState message="참여 상점을 준비 중이에요" />
    {:else}
      <div class="flex flex-wrap items-center gap-2">
        {#each split.badges as shop (shop.id)}
          <ShopBadge {shop} />
        {/each}
        {#if split.extra > 0}
          <span class="ml-1 text-sm text-gray-400">+{split.extra}개</span>
        {/if}
      </div>
    {/if}
  </div>
</section>
