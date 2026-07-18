<script>
  // CTA/보조 버튼 (§3·§8). 이벤트는 콜백 prop(onclick).
  // variant: primary(Island Yellow 채움) | ghost(테두리/투명).
  // loading이면 인라인 Spinner + 비활성(중복 제출 방지, §8).
  import Spinner from './Spinner.svelte'

  let {
    variant = 'primary',
    disabled = false,
    loading = false,
    type = 'button',
    onclick,
    children,
  } = $props()

  // 로딩 중엔 항상 비활성. 탭 타깃 최소 44px(§10).
  const isDisabled = $derived(disabled || loading)

  const VARIANTS = {
    primary: 'bg-island-yellow text-flow-black active:brightness-95',
    ghost: 'bg-transparent text-flow-black border border-gray-300 active:bg-gray-50',
  }
  const variantClass = $derived(VARIANTS[variant] ?? VARIANTS.primary)
</script>

<button
  {type}
  {onclick}
  disabled={isDisabled}
  class="relative inline-flex items-center justify-center gap-2 min-h-[44px] w-full rounded-xl px-4 py-3 text-base font-bold transition-[filter,background-color] disabled:opacity-50 disabled:cursor-not-allowed {variantClass}"
>
  {#if loading}
    <Spinner size="sm" />
  {/if}
  {@render children?.()}
</button>
