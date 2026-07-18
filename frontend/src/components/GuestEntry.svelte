<script module>
  // 상대시간 포맷 (GB-507). now를 주입 가능하게 해 테스트 결정성을 확보한다(Guestbook.test.js).
  // 1분 미만 "방금 전" / 시간 미만 "N분 전" / 하루 미만 "N시간 전" / 그 외 "N일 전".
  // 서버 created_at(ISO 8601, KST 기준 §12)을 클라이언트에서 상대값으로 변환.
  export function formatRelativeTime(iso, now = Date.now()) {
    const sec = Math.floor((now - new Date(iso).getTime()) / 1000)
    if (!Number.isFinite(sec) || sec < 60) return '방금 전'
    if (sec < 3600) return `${Math.floor(sec / 60)}분 전`
    if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`
    return `${Math.floor(sec / 86400)}일 전`
  }
</script>

<script>
  // 방명록 항목 카드 (§3, GB-501/507/601/602).
  // 작성자는 항상 "익명 방문자"(§12). 본문은 텍스트 바인딩이라 코드/HTML도 글자로만 보인다(XSS 방어, GB-601).
  // entry: { id, content, rating?, shop_tags:[{shop_id,name}], created_at }
  import StarRating from './StarRating.svelte'

  let { entry } = $props()

  const relative = $derived(formatRelativeTime(entry.created_at))
  const tags = $derived(entry.shop_tags ?? [])
</script>

<article class="rounded-2xl bg-gray-100 px-4 py-4">
  <div class="mb-2 flex items-center justify-between">
    <span class="text-xs font-semibold text-gray-700">익명 방문자</span>
    <span class="text-xs text-gray-400">{relative}</span>
  </div>

  <p class="whitespace-pre-wrap break-words text-sm leading-relaxed text-gray-800">{entry.content}</p>

  {#if entry.rating != null}
    <div class="mt-2">
      <StarRating value={entry.rating} readonly />
    </div>
  {/if}

  {#if tags.length > 0}
    <div class="mt-3 flex flex-wrap gap-1.5">
      {#each tags as tag (tag.shop_id)}
        <span class="rounded-full bg-island-yellow-light px-2.5 py-1 text-xs font-medium text-flow-black">
          {tag.name}
        </span>
      {/each}
    </div>
  {/if}
</article>
