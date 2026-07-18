<script>
  // 앱 셸 (§4·§7). 라우트 표 + /reserve 가드 + 셸 레벨 토스트 마운트.
  // /admin은 모바일 컬럼 셸 밖의 별도 레이아웃으로 렌더한다.
  import Router, { push, router } from 'svelte-spa-router'
  import { wrap } from 'svelte-spa-router/wrap'
  import Header from './components/Header.svelte'
  import Toast from './components/Toast.svelte'
  import ScanGate from './components/ScanGate.svelte'
  import DevTools from './components/DevTools.svelte'
  import FlowProgress from './components/FlowProgress.svelte'
  import { toast, showToast } from './lib/toast.svelte.js'
  import { requireVerify, requireSeat, VERIFY_REDIRECT, SEAT_REDIRECT } from './lib/guard.js'
  import { parseSeatParam, saveSeat, loadSeat } from './lib/store.svelte.js'

  import Main from './routes/Main.svelte'
  import Menu from './routes/Menu.svelte'
  import Verify from './routes/Verify.svelte'
  import Reserve from './routes/Reserve.svelte'
  import Reservation from './routes/Reservation.svelte'
  import Guestbook from './routes/Guestbook.svelte'
  import Admin from './routes/Admin.svelte'

  // QR 부트(D-26): 해시 쿼리스트링(`#/?seat=a3`)에서 seat를 읽어 저장한다. 최신 스캔이 덮어쓴다.
  // 없으면 기존 값을 메모리로 하이드레이트(유지) — 공유 링크 등으로 seat 없이 진입할 수 있다.
  const bootSeat = parseSeatParam(window.location.hash)
  if (bootSeat) saveSeat(bootSeat)
  else loadSeat()

  const routes = {
    '/': Main,
    '/menu': Menu,
    '/verify': Verify,
    // /reserve 가드(D-14·D-26): 유효한 당일 verify 토큰 + 찍은 seat 둘 다 있어야 진입.
    '/reserve': wrap({ component: Reserve, conditions: [requireVerify, requireSeat] }),
    '/reservation/:id': Reservation,
    '/guestbook': Guestbook,
    '/admin': Admin,
  }

  // 가드 실패 시 리다이렉트(서버 확정은 예약 API가 별도 수행).
  // 토큰이 없으면 인증으로, 토큰은 있는데 seat가 없으면 메인으로 보내고 좌석 QR 스캔을 안내한다(D-26).
  function onConditionsFailed() {
    if (!requireVerify()) {
      push(VERIFY_REDIRECT)
      return
    }
    push(SEAT_REDIRECT)
    showToast('현장 좌석의 QR을 찍어주세요', 'info')
  }

  // /admin은 셸 밖 레이아웃(햄버거·모바일 컬럼 없음, §4).
  const isAdmin = $derived((router.location ?? '/').startsWith('/admin'))

  // QR 게이트(D-26): 좌석 QR 없이 루트로 진입하면(= QR 안 탐) 풀스크린 온보딩으로 막는다.
  // QR은 항상 `/#/?seat=xxx`로 랜딩하므로, 루트인데 seat 쿼리가 없으면 QR을 안 탄 것.
  const seatInUrl = $derived(new URLSearchParams(router.querystring ?? '').get('seat'))
  // 게이트(D-26): 루트 + seat 없음 + 예약 흔적 없음일 때만. 예약 보유자는 QR 없이 열어도
  // 통과시켜 자기 예약을 보게 한다(D-28 재진입). stale 예약이면 Main이 정리 후 유도한다.
  const showGate = $derived(
    (router.location ?? '/') === '/' && !seatInUrl && !localStorage.getItem('stop-island:reservation-id'),
  )

  // 예약 여정 상단 프로그레스(D-26): 라우트 → 단계. 여정 밖(방명록·관리자·게이트)이면 -1(숨김).
  // 자리(0) → 인증(1) → 예약(2) → 착석/완료(3).
  const flowStep = $derived.by(() => {
    const l = router.location ?? '/'
    if (l === '/' && seatInUrl) return 0
    if (l === '/verify') return 1
    if (l === '/reserve') return 2
    if (l.startsWith('/reservation')) return 3
    return -1
  })

</script>

{#if showGate}
  <!-- QR 안 타고 진입 → 풀스크린 게이트. 메인 콘텐츠·헤더 숨김. 다음 행동은 QR 스캔뿐. -->
  <ScanGate />
{:else if isAdmin}
  <div class="min-h-screen bg-gray-50">
    <Router {routes} on:conditionsFailed={onConditionsFailed} />
  </div>
{:else}
  <div class="relative mx-auto min-h-screen max-w-[430px] bg-white shadow-lg">
    <Header />
    <!-- 예약 여정 상단 프로그레스 — 흐름을 지나는 동안 계속 노출(자리→인증→예약→착석) -->
    {#if flowStep >= 0}
      <div class="border-b border-gray-100">
        <FlowProgress step={flowStep} />
      </div>
    {/if}
    <Router {routes} on:conditionsFailed={onConditionsFailed} />
  </div>
{/if}

<!-- 셸 레벨 토스트 단일 마운트 지점(§4). 화면은 lib/toast.svelte.js의 showToast()만 호출. -->
{#if toast.visible}
  <Toast message={toast.message} kind={toast.kind} />
{/if}

<!-- 🛠 테스트 전용 툴바(우상단). 배포 전 이 한 줄 제거. -->
<DevTools />
