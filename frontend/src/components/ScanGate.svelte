<script>
  // QR 게이트(D-26): 좌석 QR 없이 들어온 사용자를 위한 풀스크린 온보딩.
  // 유저는 무조건 테이블의 QR로 진입한다 — QR을 안 탔다면 이 서비스를 이용할 진입점이 없다.
  // 그래서 메인 콘텐츠(현황·예약·방명록)를 보여주지 않고 이 화면으로 막아 QR 스캔으로 유도한다.
  // 실제 유저의 다음 행동은 "폰으로 QR 스캔"뿐이다(테스트용 통과 버튼은 App 셸 우상단).
</script>

<div class="fixed inset-0 z-40 flex flex-col items-center justify-center gap-9 bg-island-yellow px-8 text-center">
  <p class="text-sm font-extrabold tracking-widest text-flow-black/60">멈춰, 섬!</p>

  <!-- QR 스캔 심볼 -->
  <div class="flex h-32 w-32 items-center justify-center rounded-[28px] border-4 border-flow-black bg-pause-white">
    <svg class="h-16 w-16 text-flow-black" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M3 3h7v7H3V3zm2 2v3h3V5H5z" />
      <path d="M14 3h7v7h-7V3zm2 2v3h3V5h-3z" />
      <path d="M3 14h7v7H3v-7zm2 2v3h3v-3H5z" />
      <path d="M14 14h3v3h-3v-3zm5 0h2v2h-2v-2zm-5 5h3v2h-3v-2zm5 0h2v2h-2v-2z" />
    </svg>
  </div>

  <div class="space-y-3">
    <h1 class="text-2xl font-extrabold leading-snug text-flow-black">
      테이블의 QR을 찍어<br />시작해주세요
    </h1>
    <p class="text-sm font-medium leading-relaxed text-flow-black/70">
      자리마다 붙은 QR 코드를 폰으로 스캔하면<br />그 자리에서 바로 이용할 수 있어요.
    </p>
  </div>
</div>
