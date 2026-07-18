<script module>
  // 맛집 태그 선택 순수 리듀서 (GB-302/303/304).
  // 이미 선택된 상점을 재탭하면 해제, 미선택이면 추가하되 max(기본 5)를 넘으면 거부(rejected:true).
  // rejected일 때 호출부가 "5개까지" 안내를 띄운다. 순수 함수라 Guestbook.test.js에서 단위 검증.
  export function toggleShopTag(selected, shop, max = 5) {
    const exists = selected.some((s) => s.id === shop.id)
    if (exists) {
      return { next: selected.filter((s) => s.id !== shop.id), rejected: false }
    }
    if (selected.length >= max) {
      return { next: selected, rejected: true }
    }
    return { next: [...selected, { id: shop.id, name: shop.name }], rejected: false }
  }
</script>

<script>
  // 맛집 태그 선택 바텀시트 내용 (§8, GB-301~305). BottomSheet 안에 렌더된다.
  // selected: 현재 선택된 [{id,name}] (Guestbook이 소유). onChange(next). max: 최대 개수(기본 5).
  import { onMount } from 'svelte'
  import { getShops } from '../lib/api.js'
  import Spinner from './Spinner.svelte'
  import ErrorState from './ErrorState.svelte'

  let { selected = [], onChange, max = 5 } = $props()

  let shops = $state([])
  let loading = $state(true)
  let error = $state(false)
  let limitHit = $state(false) // 6개째 시도 시 안내 노출(GB-303)

  async function load() {
    loading = true
    error = false
    try {
      // 서버가 is_active=true·sort_order 정렬로 내려준다(GB-301). 방어적으로 비활성만 한 번 더 거른다.
      const list = await getShops()
      shops = (list ?? []).filter((s) => s.is_active !== false)
    } catch {
      error = true
    } finally {
      loading = false
    }
  }

  onMount(load)

  function toggle(shop) {
    const { next, rejected } = toggleShopTag(selected, shop, max)
    limitHit = rejected
    if (!rejected) onChange?.(next)
  }

  function isSelected(shop) {
    return selected.some((s) => s.id === shop.id)
  }
</script>

<div>
  <h2 class="mb-3 text-base font-bold text-flow-black">맛집 추가</h2>

  {#if loading}
    <div class="flex justify-center py-10 text-gray-400">
      <Spinner />
    </div>
  {:else if error}
    <ErrorState message="목록을 불러오지 못했어요" onRetry={load} />
  {:else if shops.length === 0}
    <p class="py-10 text-center text-sm text-gray-500">참여 상점을 준비 중이에요</p>
  {:else}
    {#if limitHit}
      <p class="mb-2 text-xs font-medium text-flow-black">맛집 태그는 {max}개까지 붙일 수 있어요</p>
    {/if}
    <ul class="max-h-[50vh] space-y-1 overflow-y-auto">
      {#each shops as shop (shop.id)}
        {@const active = isSelected(shop)}
        <li>
          <button
            type="button"
            class="flex min-h-[44px] w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors {active
              ? 'bg-island-yellow-light font-medium text-flow-black'
              : 'text-gray-700 active:bg-gray-50'}"
            aria-pressed={active}
            onclick={() => toggle(shop)}
          >
            <span>{shop.name}</span>
            {#if active}
              <svg class="h-4 w-4 text-flow-black" viewBox="0 0 20 20" fill="none">
                <path d="M4 10l4 4 8-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            {:else}
              <span class="h-4 w-4 rounded border border-gray-300"></span>
            {/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
