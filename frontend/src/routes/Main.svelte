<script module>
  // 순수 헬퍼 (테스트 대상). 현황 숫자 표시: 값이 없으면 신호 나쁨 대비 "—" 폴백.
  // 화면이 죽지 않도록 숫자 자리만 비운다(§6 offline, MAIN-204/501).
  export function formatCount(value) {
    return value === null || value === undefined ? '—' : String(value)
  }
</script>

<script>
  // 01 메인 (MAIN-*, J1.1). 헤더/드로어는 App 셸이 마운트하므로 여기선 본문만 렌더한다.
  import { onMount } from 'svelte'
  import { push } from 'svelte-spa-router'
  import { getStatus, getSeatStatus } from '../lib/api.js'
  import { reservation, reconcileReservation, loadReservationId, seat, saveSeat, parseSeatParam } from '../lib/store.svelte.js'
  import { seatUnavailableMessage } from './reserveLogic.js'
  import { createPoll } from '../lib/poll.js'
  import Button from '../components/Button.svelte'
  import Skeleton from '../components/Skeleton.svelte'
  // formatCount는 위 <script module>에서 선언 — 인스턴스 스코프에서 바로 쓴다.

  // status: 마지막 성공 값을 유지(폴링 실패해도 되돌리지 않음, MAIN-205).
  let status = $state(null)
  let firstLoad = $state(true) // 최초 로딩 스켈레톤 vs "—" 폴백 구분
  let statusError = $state(false) // 신호 나쁨 인디케이터
  let banner = $state(null) // active 예약(있으면 재진입 정책 우선 노출, D-28)
  let ended = $state(false) // 직전 예약이 종료(만료·취소)된 채 재진입(D-28)

  // 이번 진입의 좌석은 오직 URL QR(`?seat=`)로만 결정한다(D-26). 유저는 무조건 좌석 QR로 진입.
  // QR 없이 들어오면 stale localStorage 좌석을 쓰지 않고 "QR 유도" 상태로 보낸다.
  const entrySeat = parseSeatParam(window.location.hash)
  let seatInfo = $state(null) // { id, label, capacity, position_label, state } | null
  const seatLabel = $derived(seatInfo?.label ?? (entrySeat ? entrySeat.toUpperCase() : ''))
  // guide(QR 없음) | loading(QR 있고 해소중) | available(잡기 가능) | unavailable(사용중/운영중지)
  const seatContext = $derived.by(() => {
    if (!entrySeat) return 'guide'
    if (!seatInfo) return 'loading'
    return seatInfo.state === 'available' ? 'available' : 'unavailable'
  })

  // 컴포넌트 파괴 후 뒤늦게 도착한 응답 무시(MAIN-207).
  let destroyed = false
  // 이전 요청이 아직 안 끝났으면 이번 폴링 주기는 스킵(중복 요청 금지, MAIN-503).
  let inFlight = false

  async function fetchStatus() {
    if (inFlight) return
    inFlight = true
    try {
      const s = await getStatus()
      if (destroyed) return
      status = s
      statusError = false
    } catch {
      if (destroyed) return
      statusError = true // 값은 유지, 최초 실패면 status가 null이라 "—"로 표시됨
    } finally {
      inFlight = false
      if (!destroyed) firstLoad = false
    }
  }

  // 찍은 자리 상태 해소(D-26). seat.id 없으면 skip. 실패 시 직전 값 유지(맥락은 조용히 생략).
  async function fetchSeat() {
    if (!seat.id) return
    try {
      const s = await getSeatStatus(seat.id)
      if (destroyed) return
      seatInfo = s
    } catch {
      // 신호 나쁨: 직전 seatInfo 유지(화면 안 죽임, §6).
    }
  }

  // 내 예약 배너: 진입 시 1회 서버 확정(D-10, MAIN-301). 네트워크 오류면 조용히 숨김(MAIN-305).
  async function reconcile() {
    const prior = loadReservationId() // 재진입 시 직전 예약 흔적(종료 판정용)
    try {
      const r = await reconcileReservation()
      if (destroyed) return
      banner = r // active면 재진입 정책(이용 중) 우선 노출
      ended = !r && !!prior // 예약이 있었는데 지금 없음 = 종료(만료·취소)
    } catch {
      if (destroyed) return
      banner = null // 상태 불명 — 조용히(localStorage는 store가 보존)
    }
  }

  // 마운트 1회 사이드이펙트는 onMount로. $effect로 하면 loadSeat()가 seat.id(reactive)를
  // 쓰고 fetchSeat()가 그걸 읽어 self-invalidate → effect 재실행 → cleanup이 destroyed=true를
  // 걸어 firstLoad가 영영 안 꺼지는 버그가 난다.
  onMount(() => {
    if (entrySeat) saveSeat(entrySeat) // 이번 QR 좌석 저장(다운스트림 verify/reserve가 사용)
    fetchStatus() // 마운트 즉시 1회(createPoll은 즉발하지 않음)
    if (entrySeat) fetchSeat() // QR로 들어온 경우만 좌석 상태 해소
    reconcile()
    // 30초 폴링(hidden 시 정지, 복귀 시 재요청) — 현황 + 찍은 자리 상태 함께 신선하게.
    const stopPoll = createPoll(() => { fetchStatus(); fetchSeat() }, 30000)
    window.addEventListener('online', reconcile) // 온라인 복귀 시 예약도 재확인(MAIN-502)
    return () => {
      destroyed = true
      stopPoll()
      window.removeEventListener('online', reconcile)
    }
  })
</script>

<!-- ══ 재진입 정책(D-28) — 이용 중이면 그 자리 우선, 새 예약 차단(한 자리 규칙).
     예약 종료 후 재진입엔 부드러운 안내. 그 외엔 도착 경험(D-26). -->
{#if banner}
  <!-- ① 이미 이용 중 — 재진입 시 최우선. 다른 자리 QR을 찍어도 새로 못 잡음 -->
  <section class="hero relative overflow-hidden bg-island-yellow px-6 pb-9 pt-9">
    <svg class="zig absolute inset-x-0 top-0 h-3.5 w-full text-flow-black/80" viewBox="0 0 140 8" preserveAspectRatio="none" fill="none" aria-hidden="true">
      <polyline points="0,7 10,1 20,7 30,1 40,7 50,1 60,7 70,1 80,7 90,1 100,7 110,1 120,7 130,1 140,7" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
    </svg>
    <p class="pill reveal d0 mt-3 inline-flex items-center gap-1.5 rounded-full bg-flow-black px-3 py-1.5 text-xs font-extrabold text-island-yellow">이용 중</p>
    <p class="reveal d1 mt-6 text-sm font-bold tracking-wide text-flow-black/55">이용 중인 자리</p>
    <div class="seat -mt-1 flex items-end gap-3">
      <span class="text-[92px] font-black leading-[0.82] tracking-tighter text-flow-black">{banner.seat?.label ?? ''}</span>
      <span class="reveal d3 mb-4 text-2xl font-bold text-flow-black/70">자리</span>
    </div>
    {#if banner.seat?.capacity}
      <p class="reveal d3 mt-3 text-base font-semibold text-flow-black/70">{banner.seat.capacity}인석{#if banner.seat.position_label} · {banner.seat.position_label}{/if}</p>
    {/if}
  </section>

  <section class="px-6 pt-7">
    {#if entrySeat && entrySeat.toUpperCase() !== (banner.seat?.label ?? '')}
      <div class="reveal d4 rounded-2xl bg-gray-50 px-5 py-4 text-sm leading-relaxed text-gray-600">
        <span class="font-bold text-flow-black">{entrySeat.toUpperCase()}</span> 자리를 새로 찍으셨네요. 한 번에 <span class="font-bold text-flow-black">한 자리</span>만 이용할 수 있어요 — 옮기려면 지금 자리를 비운 뒤 그 자리 QR을 다시 찍어주세요.
      </div>
    {:else}
      <p class="reveal d4 text-[15px] font-medium leading-relaxed text-flow-black">지금 이 자리를 이용하고 있어요.<br />남은 시간과 이용 정보를 확인해보세요.</p>
    {/if}
  </section>

  <section class="reveal d5 px-5 pt-7 pb-10">
    <Button variant="primary" onclick={() => push('/reservation/' + reservation.id)}>내 자리 보기</Button>
    <button onclick={() => push('/guestbook')} class="mt-3 block w-full text-center text-sm font-semibold text-gray-500 underline underline-offset-4 active:text-flow-black">방명록 구경하기</button>
  </section>

{:else if !entrySeat}
  <!-- ② 자리 없이 진입(예약 종료 후 바로 열기 등) — QR 유도 미니 안내 -->
  <section class="flex min-h-[60vh] flex-col items-center justify-center px-8 text-center">
    {#if ended}
      <p class="mb-4 rounded-full bg-flow-black px-4 py-1.5 text-xs font-bold text-pause-white">이전 이용이 끝났어요</p>
    {/if}
    <h1 class="text-xl font-extrabold leading-snug text-flow-black">테이블의 QR을 찍어<br />다시 시작해주세요</h1>
    <p class="mt-3 text-sm font-medium leading-relaxed text-gray-500">앉고 싶은 자리의 QR을 스캔하면<br />바로 이용할 수 있어요.</p>
    <button onclick={() => push('/guestbook')} class="mt-8 text-sm font-semibold text-gray-500 underline underline-offset-4 active:text-flow-black">방명록 구경하기</button>
  </section>

{:else}
  <!-- ③ 도착 경험(D-26) — 스캔 완료 순간을 히어로로 -->
  {#if ended}
    <div class="bg-flow-black px-5 py-3 text-center text-xs font-semibold text-pause-white">
      이전 이용이 끝났어요 · 이 자리를 다시 잡을 수 있어요
    </div>
  {/if}
  <!-- 도착 히어로 (Island Yellow) -->
  <section class="hero relative overflow-hidden bg-island-yellow px-6 pb-9 pt-9">
  <!-- 지그재그 모티브(파라솔 펼침·도시 리듬) — 위에서 그려진다 -->
  <svg class="zig absolute inset-x-0 top-0 h-3.5 w-full text-flow-black/80" viewBox="0 0 140 8" preserveAspectRatio="none" fill="none" aria-hidden="true">
    <polyline points="0,7 10,1 20,7 30,1 40,7 50,1 60,7 70,1 80,7 90,1 100,7 110,1 120,7 130,1 140,7" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
  </svg>

  <p class="pill reveal d0 mt-3 inline-flex items-center gap-1.5 rounded-full bg-flow-black px-3 py-1.5 text-xs font-extrabold text-island-yellow">
    <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fill-rule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0L3.3 9.7a1 1 0 011.4-1.4L8.5 12l6.8-6.7a1 1 0 011.4 0z" clip-rule="evenodd" />
    </svg>
    QR 스캔 완료
  </p>

  <p class="reveal d1 mt-6 text-sm font-bold tracking-wide text-flow-black/55">당신의 자리</p>
  <div class="seat -mt-1 flex items-end gap-3">
    <span class="text-[92px] font-black leading-[0.82] tracking-tighter text-flow-black">{seatLabel}</span>
    <span class="reveal d3 mb-4 text-2xl font-bold text-flow-black/70">자리</span>
  </div>
  <p class="reveal d3 mt-3 text-base font-semibold text-flow-black/70">
    {#if seatInfo}{seatInfo.capacity}인석{#if seatInfo.position_label} · {seatInfo.position_label}{/if}{:else}자리 확인 중…{/if}
  </p>
</section>

{#if seatContext === 'unavailable'}
  <!-- 이미 사용 중/운영 중지: 다른 빈 자리 재스캔 유도 -->
  <section class="px-6 pt-7 pb-10">
    <p class="reveal text-lg font-bold text-flow-black">{seatUnavailableMessage(seatInfo?.state)}</p>
    <div class="reveal d1 mt-4 rounded-2xl bg-gray-50 px-5 py-4 text-center text-sm leading-relaxed text-gray-600">
      {#if !firstLoad && status?.available_seats > 0}
        지금 <span class="font-bold text-flow-black">{status.available_seats}석</span> 비어 있어요 —<br />앉고 싶은 빈 자리의 QR을 찍어주세요
      {:else}
        빈 자리의 QR을 찍어주세요
      {/if}
    </div>
    <button onclick={() => push('/guestbook')} class="reveal d1 mt-6 block w-full text-center text-sm font-semibold text-gray-500 underline underline-offset-4 active:text-flow-black">
      방명록 구경하기
    </button>
  </section>
{:else}
  <!-- 값 제안 — 흐름 단계는 상단 프로그레스가 담당(중복 제거) -->
  <section class="px-6 pt-7">
    <p class="reveal d4 text-[15px] font-medium leading-relaxed text-flow-black">
      참여 상점 영수증 <span class="font-bold">한 장</span>이면<br />오늘 하루, 이 자리는 <span class="font-bold">당신 거</span>예요.
    </p>
  </section>

  <!-- CTA 주연: 자리는 이미 QR로 정해졌으니 바로 인증으로 -->
  <section class="reveal d7 px-5 pt-7 pb-5">
    {#if seatContext === 'available'}
      <Button variant="primary" onclick={() => push('/verify')}>이 자리 잡기</Button>
    {:else}
      <!-- 자리 상태 확인 중: 살짝 눌린 느낌으로 대기 -->
      <div class="flex h-[52px] items-center justify-center rounded-2xl bg-island-yellow/50 text-sm font-bold text-flow-black/50">
        자리 확인 중…
      </div>
    {/if}
  </section>

  <!-- 조연: 현황 한 줄 + 방명록 -->
  <section class="reveal d7 px-6 pb-10 text-center">
    <p class="mb-3 text-sm text-gray-500">
      {#if firstLoad}
        <span class="text-gray-300">현황 불러오는 중…</span>
      {:else if statusError}
        <span class="text-gray-400">현황을 불러오지 못했어요</span>
      {:else}
        지금 빈 자리 <span class="font-bold text-flow-black">{formatCount(status?.available_seats)}</span>석 · 오늘 <span class="font-bold text-flow-black">{formatCount(status?.today_visitors)}</span>명 방문
      {/if}
    </p>
    <button onclick={() => push('/guestbook')} class="text-sm font-semibold text-gray-500 underline underline-offset-4 active:text-flow-black">
      방명록 구경하기
    </button>
  </section>
{/if}
{/if}

<style>
  /* 도착 오케스트레이션 — 스캔 완료의 결정적 순간. prefers-reduced-motion 존중. */
  .zig {
    stroke-dasharray: 260;
    stroke-dashoffset: 260;
    animation: zigDraw 900ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
  }
  @keyframes zigDraw { to { stroke-dashoffset: 0; } }

  .reveal { opacity: 0; animation: rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) forwards; }
  @keyframes rise {
    from { opacity: 0; transform: translateY(14px); }
    to { opacity: 1; transform: none; }
  }

  /* 좌석 번호 — 크고 확신에 찬 등장 */
  .seat { opacity: 0; animation: seatIn 0.75s cubic-bezier(0.2, 1, 0.3, 1) 0.18s forwards; }
  @keyframes seatIn {
    from { opacity: 0; transform: translateY(26px) scale(0.9); }
    to { opacity: 1; transform: none; }
  }

  .d0 { animation-delay: 0.05s; }
  .d1 { animation-delay: 0.28s; }
  .d3 { animation-delay: 0.44s; }
  .d4 { animation-delay: 0.52s; }
  .d5 { animation-delay: 0.6s; }
  .d6 { animation-delay: 0.68s; }
  .d7 { animation-delay: 0.8s; }

  @media (prefers-reduced-motion: reduce) {
    .zig, .reveal, .seat {
      animation: none;
      opacity: 1;
      transform: none;
      stroke-dashoffset: 0;
    }
  }
</style>
