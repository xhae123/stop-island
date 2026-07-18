<script module>
  // 방명록 순수 로직 (§8, GB-1xx/5xx). UI 없이 단위 테스트한다(Guestbook.test.js).
  export const MAX_CONTENT = 500

  // 카운터는 원문 길이 기준(GB-103). trim 결과 길이는 게시 가능 판정용(GB-101~103).
  export function trimmedLength(text) {
    return text.trim().length
  }

  // trim 후 1~500자여야 게시 가능(GB-101/102/103/104). 공백만이면 0자라 불가.
  export function canPost(text) {
    const n = text.trim().length
    return n >= 1 && n <= MAX_CONTENT
  }

  // cursor 다음 페이지 append — id 기준 중복 제거(GB-504/506: keyset 커서라도 클라 방어).
  export function appendPage(existing, incoming) {
    const seen = new Set(existing.map((e) => e.id))
    const merged = existing.slice()
    for (const item of incoming ?? []) {
      if (!seen.has(item.id)) {
        seen.add(item.id)
        merged.push(item)
      }
    }
    return merged
  }
</script>

<script>
  // 방명록 화면 (§8, J4 / GB-*). 위 입력창(쓰기) + 아래 목록(읽기, 무한스크롤).
  // Header는 셸에서 마운트(§4) — 여기서 심지 않는다.
  import { onMount } from 'svelte'
  import { getGuestbook, postGuestbook, ApiError } from '../lib/api.js'
  import { showToast } from '../lib/toast.svelte.js'
  import GuestEntry from '../components/GuestEntry.svelte'
  import StarRating from '../components/StarRating.svelte'
  import ShopMultiSelect from '../components/ShopMultiSelect.svelte'
  import BottomSheet from '../components/BottomSheet.svelte'
  import Button from '../components/Button.svelte'
  import Skeleton from '../components/Skeleton.svelte'
  import EmptyState from '../components/EmptyState.svelte'
  import ErrorState from '../components/ErrorState.svelte'

  // --- 작성 상태 ---
  let content = $state('')
  let rating = $state(null) // 1~5 또는 null(선택)
  let selectedTags = $state([]) // [{id,name}] (최대 5, GB-302)
  let showRating = $state(false) // [별점 추가] 인라인 펼침(GB-201)
  let sheetOpen = $state(false) // 맛집 바텀시트(GB-301)
  let submitting = $state(false)

  const canSubmit = $derived(canPost(content))

  // --- 목록 상태 ---
  let entries = $state([])
  let cursor = $state(undefined) // 다음 페이지 커서(없으면 마지막)
  let hasMore = $state(true)
  let initialLoading = $state(true)
  let loadError = $state(false)
  let loadingMore = $state(false)

  let sentinelEl = $state(null)
  let listTopEl = $state(null)

  onMount(loadInitial)

  // 무한스크롤: 리스트 하단 sentinel 감지 → 다음 페이지(GB-504). 끝이면 관측 불필요.
  // $effect 유지: sentinelEl(bind:this, reactive)이 나타나고 사라질 때마다 옵저버를 다시 붙여야 한다.
  // 초기 로드는 이미 onMount(loadInitial)로 분리돼 있고, 이 effect는 sentinelEl만 읽어 self-invalidation 없음.
  $effect(() => {
    if (!sentinelEl) return
    const observer = new IntersectionObserver(
      (obs) => {
        if (obs[0].isIntersecting) loadMore()
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelEl)
    return () => observer.disconnect()
  })

  async function loadInitial() {
    initialLoading = true
    loadError = false
    try {
      const data = await getGuestbook()
      entries = data.items ?? []
      cursor = data.next_cursor
      hasMore = !!data.next_cursor
    } catch {
      loadError = true // GB-503: 목록 영역만 에러, 작성 폼은 정상
    } finally {
      initialLoading = false
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMore || !cursor) return
    loadingMore = true
    try {
      const data = await getGuestbook(cursor)
      entries = appendPage(entries, data.items) // 중복 없이 append(GB-504/506)
      cursor = data.next_cursor
      hasMore = !!data.next_cursor // GB-505: null이면 종료
    } catch {
      // 조용히 실패 — 다시 스크롤하면 재시도(무한 스피너 금지, §6)
    } finally {
      loadingMore = false
    }
  }

  async function handleSubmit() {
    if (!canSubmit || submitting) return // GB-404: 중복 제출 방지
    submitting = true
    try {
      const created = await postGuestbook({
        content: content.trim(),
        rating,
        shopTags: selectedTags.map((t) => t.id),
      })
      // GB-401/104: 게시 성공 → 목록 맨 위 즉시 추가 + 폼 리셋
      entries = [created, ...entries]
      content = ''
      rating = null
      selectedTags = []
      showRating = false
      listTopEl?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } catch (e) {
      // GB-402/403: 실패해도 입력 보존 — 다시 누르면 됨
      if (e instanceof ApiError && e.code === 'RATE_LIMITED') {
        showToast('잠시 후 다시 써주세요', 'error') // GB-403
      } else {
        showToast('게시에 실패했어요. 다시 시도해주세요', 'error') // GB-402
      }
    } finally {
      submitting = false
    }
  }

  function onRatingChange(next) {
    rating = next
  }

  function removeTag(shop) {
    selectedTags = selectedTags.filter((t) => t.id !== shop.id)
  }

  function toggleRatingPanel() {
    showRating = !showRating
  }
</script>

<div class="flex flex-col">
  <!-- 작성 폼 -->
  <section class="px-4 pt-5 pb-4">
    <div class="rounded-2xl border border-gray-200 bg-white p-3">
      <textarea
        bind:value={content}
        maxlength={MAX_CONTENT}
        rows="3"
        placeholder="오늘 카페 A에서 커피 사고 여기서 책 읽었어요…"
        aria-label="방명록 내용"
        class="w-full resize-none border-none bg-transparent text-[15px] leading-relaxed text-flow-black outline-none placeholder:text-gray-400"
      ></textarea>
      <div class="flex items-center justify-end">
        <span class="text-xs {content.length >= MAX_CONTENT ? 'font-medium text-flow-black' : 'text-gray-400'}">
          {content.length}/{MAX_CONTENT}
        </span>
      </div>

      <!-- 선택된 맛집 칩(GB-302/304) -->
      {#if selectedTags.length > 0}
        <div class="mt-2 flex flex-wrap gap-1.5">
          {#each selectedTags as tag (tag.id)}
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-full bg-island-yellow-light px-2.5 py-1 text-xs font-medium text-flow-black active:brightness-95"
              onclick={() => removeTag(tag)}
              aria-label="{tag.name} 태그 제거"
            >
              {tag.name}
              <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
          {/each}
        </div>
      {/if}

      <!-- 별점 인라인 패널(GB-201) -->
      {#if showRating}
        <div class="mt-2">
          <StarRating value={rating} onChange={onRatingChange} />
        </div>
      {/if}
    </div>

    <!-- 보조 액션: 맛집 추가 / 별점 추가 (50%씩) -->
    <div class="mt-3 flex gap-2">
      <button
        type="button"
        class="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-gray-200 bg-white py-2.5 text-sm font-medium text-gray-700 active:bg-gray-50"
        onclick={() => (sheetOpen = true)}
      >
        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 0115 0z" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        맛집 추가{selectedTags.length > 0 ? ` (${selectedTags.length})` : ''}
      </button>
      <button
        type="button"
        class="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-gray-200 bg-white py-2.5 text-sm font-medium text-gray-700 active:bg-gray-50"
        onclick={toggleRatingPanel}
        aria-expanded={showRating}
      >
        <span class="{rating != null ? 'text-island-yellow' : 'text-gray-400'}">★</span>
        {rating != null ? `${rating}점` : '별점 추가'}
      </button>
    </div>

    <!-- 게시하기 -->
    <div class="mt-3">
      <Button disabled={!canSubmit} loading={submitting} onclick={handleSubmit}>게시하기</Button>
    </div>
  </section>

  <!-- 목록 -->
  <div bind:this={listTopEl} class="px-4 pb-2">
    <p class="text-xs font-semibold text-gray-500">최근 방명록</p>
  </div>

  <section class="space-y-3 px-4 pb-10">
    {#if initialLoading}
      {#each [0, 1, 2] as _}
        <div class="space-y-3 rounded-2xl bg-gray-100 p-4">
          <div class="flex justify-between">
            <Skeleton class="h-3.5 w-20" />
            <Skeleton class="h-3.5 w-14" />
          </div>
          <Skeleton class="h-3.5 w-full" />
          <Skeleton class="h-3.5 w-3/4" />
        </div>
      {/each}
    {:else if loadError}
      <ErrorState message="불러오지 못했어요" onRetry={loadInitial} />
    {:else if entries.length === 0}
      <EmptyState message="아직 등록된 방명록이 없어요" />
    {:else}
      {#each entries as entry (entry.id)}
        <GuestEntry {entry} />
      {/each}

      {#if hasMore}
        <div bind:this={sentinelEl} class="flex justify-center py-4">
          {#if loadingMore}
            <svg class="h-5 w-5 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" class="opacity-20" />
              <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
            </svg>
          {/if}
        </div>
      {:else}
        <p class="py-4 text-center text-xs text-gray-400">마지막 방명록이에요</p>
      {/if}
    {/if}
  </section>
</div>

<!-- 맛집 선택 바텀시트(§4 셸 레벨 fixed) -->
<BottomSheet open={sheetOpen} onClose={() => (sheetOpen = false)}>
  {#snippet children()}
    <ShopMultiSelect selected={selectedTags} onChange={(next) => (selectedTags = next)} max={5} />
  {/snippet}
</BottomSheet>
