<script>
  // 🛠 테스트 전용 툴바 — 배포 전 제거(App.svelte에서 <DevTools/> 한 줄만 지우면 됨).
  // 물리 QR·여러 기기 없이 플로우를 돌려보기 위한 개발 보조 장치.
  import { getSeats } from '../lib/api.js'

  let open = $state(false)
  const SEATS = ['a1', 'a2', 'a3', 'b1', 'b2', 'b3']

  // 특정 좌석 QR 스캔 시뮬레이트: 해시에 seat 심고 리로드(부트가 다시 파싱).
  function enterSeat(id) {
    window.location.hash = '#/?seat=' + id
    window.location.reload()
  }

  // 빈 좌석 하나 골라 진입(가장 흔한 해피패스).
  async function qrPassAvailable() {
    let id = 'a1'
    try {
      const seats = await getSeats()
      id = (seats.find((s) => s.state === 'available') ?? seats[0])?.id ?? 'a1'
    } catch {
      // 조회 실패 시 a1 폴백
    }
    enterSeat(id)
  }

  // 내가 했던 것 초기화(DB 아님): localStorage의 stop-island:* 전부 제거 → 완전 새 방문자 → 게이트로.
  function resetMe() {
    Object.keys(localStorage)
      .filter((k) => k.startsWith('stop-island:'))
      .forEach((k) => localStorage.removeItem(k))
    window.location.hash = '#/'
    window.location.reload()
  }

  // 새 기기 시뮬레이트: device-id + 내 인증/예약만 제거(자리 QR 맥락은 유지) → 다른 폰인 척.
  // 중복 영수증·1일 1인증(기기 기준) 테스트용.
  function newDevice() {
    ;['stop-island:device-id', 'stop-island:verify', 'stop-island:reservation-id'].forEach((k) =>
      localStorage.removeItem(k),
    )
    window.location.reload()
  }
</script>

<!-- 우하단: 상단 프로그레스 바와 겹치지 않게. 펼치면 위로 열린다. -->
<div class="fixed bottom-4 right-3 z-[60] flex flex-col-reverse items-end gap-2">
  <button
    onclick={() => (open = !open)}
    class="rounded-full border-2 border-dashed border-flow-black bg-pause-white px-3 py-1.5 text-xs font-bold text-flow-black shadow active:brightness-95"
  >
    🛠 TEST {open ? '▲' : '▼'}
  </button>

  {#if open}
    <div class="w-52 space-y-2.5 rounded-2xl border-2 border-dashed border-flow-black bg-pause-white p-3 text-xs shadow-lg">
      <button onclick={qrPassAvailable} class="w-full rounded-lg bg-island-yellow px-3 py-2 font-bold text-flow-black active:brightness-95">
        🎫 QR 통과 (빈자리)
      </button>

      <div>
        <p class="mb-1 font-semibold text-gray-500">좌석 QR 진입</p>
        <div class="grid grid-cols-3 gap-1">
          {#each SEATS as s}
            <button onclick={() => enterSeat(s)} class="rounded-md bg-gray-100 py-1.5 font-bold text-flow-black active:bg-gray-200">
              {s.toUpperCase()}
            </button>
          {/each}
        </div>
      </div>

      <button onclick={resetMe} class="w-full rounded-lg bg-flow-black px-3 py-2 font-bold text-pause-white active:brightness-110">
        ↺ 내 상태 초기화
      </button>
      <button onclick={newDevice} class="w-full rounded-lg border border-gray-300 px-3 py-2 font-semibold text-gray-600 active:bg-gray-50">
        📱 새 기기 (device 교체)
      </button>

      <p class="text-[10px] leading-tight text-gray-400">테스트 전용 · 배포 전 제거</p>
    </div>
  {/if}
</div>
