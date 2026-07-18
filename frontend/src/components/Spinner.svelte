<script>
  // 로딩 스피너 (§6). 액션 중 버튼 인라인 또는 영역 로딩에 사용.
  // size: px 숫자 또는 'sm'|'md'|'lg'. color는 currentColor를 따라 부모 텍스트 색 상속.
  let { size = 'md' } = $props()

  const SIZES = { sm: 16, md: 24, lg: 40 }
  const px = $derived(typeof size === 'number' ? size : (SIZES[size] ?? SIZES.md))
</script>

<svg
  class="animate-spin"
  style="width: {px}px; height: {px}px;"
  viewBox="0 0 24 24"
  fill="none"
  role="status"
  aria-label="로딩 중"
>
  <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" class="opacity-20" />
  <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
</svg>
