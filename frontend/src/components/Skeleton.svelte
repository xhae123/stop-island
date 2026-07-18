<script>
  // 스켈레톤 로딩 (§6). 첫 로드 시 골격을 보여줘 레이아웃 점프를 막는다.
  // 크기는 class로 지정(예: class="h-6 w-32"). rounded는 기본 제공.
  let { class: className = 'h-4 w-full' } = $props()
</script>

<div class="animate-pulse rounded bg-gray-200 {className}"></div>
