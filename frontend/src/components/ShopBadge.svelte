<script module>
  // 참여 상점 배지 목록의 축약 로직 (그룹3 결정 · MENU-301/302).
  // 상위 max개를 배지로, 나머지 개수를 extra로 분리한다. extra<=0이면 "+n개"를 표시하지 않는다.
  // 순수 함수로 분리한 이유: "+N개" 경계(0개/2개/정확히 max개/초과)를 화면 렌더 없이 단위 테스트하기 위해.
  export function splitShops(shops, max = 3) {
    const list = Array.isArray(shops) ? shops : []
    return {
      badges: list.slice(0, max),
      extra: Math.max(0, list.length - max),
    }
  }
</script>

<script>
  // 참여 상점 배지/칩 (§3 ShopBadge). Island Yellow pill + 검정 텍스트.
  // props: shop { id, name, category }. 토큰 유틸리티만 사용(NO hex, §2).
  let { shop } = $props()
</script>

<span class="inline-flex items-center rounded-full bg-island-yellow px-3 py-1 text-sm font-medium text-flow-black">
  {shop.name}
</span>
