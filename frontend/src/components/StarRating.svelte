<script module>
  // 별점 탭 토글 순수 로직 (GB-201~203). 현재 선택값과 같은 별을 재탭하면 해제(null).
  // 순수 함수라 UI 없이 단위 테스트 가능(StarRating.test.js).
  export function toggleStar(current, tapped) {
    return current === tapped ? null : tapped
  }
</script>

<script>
  // 별점 입력/표시 (§8, GB-201~203).
  // value: 1~5 또는 null. readonly: 표시 전용(GuestEntry 카드). onChange(next|null).
  // 탭 타깃 최소 44px(§10). 색은 토큰만 사용(§2).
  let { value = null, readonly = false, onChange } = $props()

  const STARS = [1, 2, 3, 4, 5]
  const filled = $derived(value ?? 0)

  function handleTap(star) {
    if (readonly) return
    onChange?.(toggleStar(value, star))
  }
</script>

{#if readonly}
  <div class="flex items-center gap-0.5" aria-label={value != null ? `별점 ${value}점` : '별점 없음'}>
    {#each STARS as star}
      <span
        class="text-base leading-none {star <= filled ? 'text-island-yellow' : 'text-gray-300'}"
        aria-hidden="true">★</span>
    {/each}
    {#if value != null}
      <span class="ml-1 text-xs text-gray-500">{value}점</span>
    {/if}
  </div>
{:else}
  <div class="flex items-center gap-0.5" role="radiogroup" aria-label="별점 선택">
    {#each STARS as star}
      <button
        type="button"
        class="flex h-11 w-11 items-center justify-center text-2xl leading-none transition-transform active:scale-110 {star <= filled ? 'text-island-yellow' : 'text-gray-300'}"
        aria-label="{star}점"
        aria-pressed={value != null && star <= value}
        onclick={() => handleTap(star)}>★</button>
    {/each}
    {#if value != null}
      <span class="ml-1 text-sm font-medium text-gray-600">{value}점</span>
    {/if}
  </div>
{/if}
