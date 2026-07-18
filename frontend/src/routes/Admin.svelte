<script module>
  // 순수 로직 (테스트 대상). 렌더링과 무관해 Admin.test.js에서 직접 import 한다.

  // 남은 시간(ms)을 "남은 1시간 58분" / "남은 58분" / "만료됨"으로 (§12).
  export function remainingLabel(diffMs) {
    if (diffMs <= 0) return '만료됨'
    const mins = Math.floor(diffMs / 60000)
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return h > 0 ? `남은 ${h}시간 ${m}분` : `남은 ${m}분`
  }

  // 예약 만료 표기 = 절대시각(KST) + 남은시간 (§12: "16:42까지 · 남은 1시간 58분").
  export function formatExpiry(expiresAt, nowMs = Date.now()) {
    if (!expiresAt) return ''
    const end = new Date(expiresAt).getTime()
    if (Number.isNaN(end)) return ''
    const abs = new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(end)
    return `${abs}까지 · ${remainingLabel(end - nowMs)}`
  }

  // 백엔드 GET /api/admin/stats 실제 응답에서 미감사 수를 읽는다(verifications.needs_audit 중첩).
  // 값이 없으면 0. 통계 카드/감사 배지가 같은 소스를 쓰도록 한 곳에 모은다.
  function needsAuditOf(raw) {
    return raw?.verifications?.needs_audit ?? 0
  }

  // 통계 원본 → 숫자 카드 배열 (ADM-701). 그래프 없음, 카드만.
  // 형태는 백엔드 실 응답(라이브 캡처)에 고정한다:
  //   { date, today_visitors, verifications:{approved,rejected,needs_audit}, seats:{available,open_total,total} }
  // 오늘 누적 예약/방명록 수는 백엔드 stats 계약에 없어 카드에서 제외한다(허수 0 표시 금지).
  // tab 필드가 있으면 그 탭으로 이동하는 탭 가능 카드다(미감사 → 감사 탭).
  export function deriveStats(raw) {
    const visitors = raw?.today_visitors ?? 0
    const approved = raw?.verifications?.approved ?? 0
    const rejected = raw?.verifications?.rejected ?? 0
    const needsAudit = needsAuditOf(raw)
    const available = raw?.seats?.available ?? 0
    const openTotal = raw?.seats?.open_total ?? 0

    return [
      { key: 'visitors', label: '오늘 방문자', value: `${visitors}`, hint: '당일 인증 성공' },
      { key: 'verification', label: '인증 현황', value: `승인 ${approved} · 거부 ${rejected}`, hint: '오늘' },
      { key: 'audit', label: '미감사', value: `${needsAudit}`, hint: '탭하면 감사 큐로', tab: 'audit' },
      { key: 'seats', label: '좌석 현황', value: `${available} / ${openTotal}`, hint: '빈자리 / 열린 좌석' },
    ]
  }

  // needs_audit 배지 숫자 도출: 감사 목록이 로드됐으면 그 길이, 아니면 통계값(중첩) 폴백.
  export function auditBadgeCount(auditItems, statsRaw) {
    if (Array.isArray(auditItems)) return auditItems.length
    return needsAuditOf(statsRaw)
  }
</script>

<script>
  // 관리자 원격 모니터링 (ADM-* · J6, D-21·D-22).
  // /admin은 App.svelte가 모바일 컬럼 셸 밖에서 렌더한다(햄버거·공용 Header 없음).
  // 이 화면은 내부 운영 도구라 브랜드 미감을 재현하지 않고 기능 위주 심플 레이아웃(design.md §0 경계).
  import {
    adminLogin,
    getAudit,
    auditOk,
    auditRevoke,
    adminListReservations,
    setSeatOpen,
    adminReleaseReservation,
    deleteGuestbook,
    createShop,
    updateShop,
    getStats,
    getSeats,
    adminGetShops,
    getGuestbook,
    ApiError,
  } from '../lib/api.js'
  import { onMount } from 'svelte'
  import { createPoll } from '../lib/poll.js'
  import { showToast } from '../lib/toast.svelte.js'
  import { timeAgo } from '../lib/utils.js'
  import Button from '../components/Button.svelte'
  import Spinner from '../components/Spinner.svelte'
  import Skeleton from '../components/Skeleton.svelte'
  import EmptyState from '../components/EmptyState.svelte'
  import ErrorState from '../components/ErrorState.svelte'

  // 'checking' 최초 세션 확인 중 → 'login' 게이트 → 'ready' 콘텐츠
  let authState = $state('checking')
  let password = $state('')
  let loginLoading = $state(false)
  let loginError = $state('')

  const TABS = [
    { id: 'stats', label: '통계' },
    { id: 'audit', label: '감사' },
    { id: 'seats', label: '좌석·예약' },
    { id: 'guestbook', label: '방명록' },
    { id: 'shops', label: '상점' },
  ]
  let activeTab = $state('stats')

  // --- 데이터 상태 ---
  let statsRaw = $state(null)
  let statsLoading = $state(false)
  let statsError = $state(false)

  let auditItems = $state(null) // null=미로드, []=빈
  let auditLoading = $state(false)
  let auditError = $state(false)
  let auditBusyId = $state(null)

  let reservations = $state(null)
  let reservationsLoading = $state(false)
  let reservationsError = $state(false)
  let reservationBusyId = $state(null)

  // 좌석 열림 상태: 별도 admin 조회 엔드포인트를 추가하지 않고 공개 GET /api/seats를 재사용한다.
  // 공개 응답의 status(closed면 is_open=false 파생)를 isOpen으로 환원해 실제 닫힌 좌석도 정확히 표시한다.
  // 초기값은 6석 all-open으로 두되, 좌석 탭 진입 시 서버 상태로 덮어쓴다.
  let seats = $state(
    ['a1', 'a2', 'a3', 'b1', 'b2', 'b3'].map(id => ({ id, label: id.toUpperCase(), isOpen: true })),
  )
  let seatBusyId = $state(null)

  let guestbook = $state(null)
  let guestbookLoading = $state(false)
  let guestbookError = $state(false)
  let guestbookBusyId = $state(null)

  let shops = $state(null)
  let shopsLoading = $state(false)
  let shopsError = $state(false)
  let shopBusyId = $state(null)
  let editingShopId = $state(null)
  let shopEdit = $state({ name: '', category: '', sortOrder: 0 })
  // 신규 상점 폼
  let newShop = $state({ id: '', name: '', category: '', sortOrder: 0 })
  let newShopError = $state('')
  let newShopBusy = $state(false)

  const auditBadge = $derived(auditBadgeCount(auditItems, statsRaw))
  const statCards = $derived(deriveStats(statsRaw))

  // 401(세션 만료/미인증)은 어느 호출에서든 로그인 게이트로 되돌린다 (ADM-104·105).
  function handleAuthError(e) {
    if (e instanceof ApiError && e.status === 401) {
      authState = 'login'
      password = ''
      showToast('세션이 만료됐어요. 다시 로그인해주세요', 'error')
      return true
    }
    return false
  }

  // --- 최초 세션 확인: getStats 401이면 로그인 게이트, 아니면 콘텐츠 (ADM-105·107) ---
  // onMount인 이유: 진입 시 1회 세션 확인이다. $effect로 두면 authState(reactive)를 읽고(가드)
  // 또 authState를 써서('ready'/'login') self-invalidate → 마운트 로직 재실행 여지가 생긴다.
  // 1회 실행이 의도이므로 onMount가 정확하다. (아래 탭 로더/폴링은 activeTab 변화에 재실행돼야 해서 $effect 유지)
  onMount(() => {
    if (authState !== 'checking') return
    getStats()
      .then(data => {
        statsRaw = data
        authState = 'ready'
      })
      .catch(e => {
        if (e instanceof ApiError && e.status === 401) {
          authState = 'login'
        } else {
          // 세션은 유효하나 서버 오류 — 콘텐츠로 진입하고 통계 영역에 에러 표시
          statsError = true
          authState = 'ready'
        }
      })
  })

  async function handleLogin(e) {
    e?.preventDefault?.()
    if (!password || loginLoading) return
    loginLoading = true
    loginError = ''
    try {
      await adminLogin(password)
      authState = 'ready'
      activeTab = 'stats'
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        loginError = '시도가 너무 많아요. 5분 후 다시 시도해주세요'
      } else if (err instanceof ApiError && err.status === 401) {
        loginError = '비밀번호가 올바르지 않아요'
      } else {
        loginError = '로그인에 실패했어요. 잠시 후 다시 시도해주세요'
      }
    } finally {
      loginLoading = false
    }
  }

  // --- 탭별 로더 (활성 탭만 로드/폴링) ---
  async function loadStats() {
    statsLoading = true
    try {
      statsRaw = await getStats()
      statsError = false
    } catch (e) {
      if (!handleAuthError(e)) statsError = true
    } finally {
      statsLoading = false
    }
  }

  async function loadAudit() {
    auditLoading = true
    try {
      const data = await getAudit()
      auditItems = Array.isArray(data) ? data : (data?.items ?? [])
      auditError = false
    } catch (e) {
      if (!handleAuthError(e)) auditError = true
    } finally {
      auditLoading = false
    }
  }

  async function loadReservations() {
    reservationsLoading = true
    try {
      const data = await adminListReservations()
      reservations = Array.isArray(data) ? data : (data?.items ?? [])
      reservationsError = false
    } catch (e) {
      if (!handleAuthError(e)) reservationsError = true
    } finally {
      reservationsLoading = false
    }
  }

  async function loadSeats() {
    // 공개 /api/seats 재사용. status='closed'만 is_open=false로 환원한다
    // (taken/available은 예약 유무일 뿐 열림 상태는 open이다).
    try {
      const data = await getSeats()
      if (Array.isArray(data)) {
        seats = data.map(s => ({ id: s.id, label: s.label, isOpen: s.status !== 'closed' }))
      }
    } catch (e) {
      handleAuthError(e) // 실패해도 좌석 토글은 낙관적 로컬 상태로 계속 동작
    }
  }

  async function loadGuestbook() {
    guestbookLoading = true
    try {
      const data = await getGuestbook()
      guestbook = data?.items ?? (Array.isArray(data) ? data : [])
      guestbookError = false
    } catch (e) {
      if (!handleAuthError(e)) guestbookError = true
    } finally {
      guestbookLoading = false
    }
  }

  async function loadShops() {
    shopsLoading = true
    try {
      // 관리자 목록: 비활성 상점까지 전부(GET /api/admin/shops). 공개 getShops는 활성만 주므로,
      // 비활성 상점을 재활성화하려면 여기서 전체를 받아야 한다.
      const data = await adminGetShops()
      shops = Array.isArray(data) ? data : (data?.items ?? [])
      shopsError = false
    } catch (e) {
      if (!handleAuthError(e)) shopsError = true
    } finally {
      shopsLoading = false
    }
  }

  // 활성 탭 진입 시 로드 + (통계/감사) 폴링. createPoll의 stop을 cleanup으로 반환.
  // $effect 유지: activeTab(reactive)이 바뀔 때마다 이전 탭 폴링을 정리하고 새 탭을 로드해야 한다.
  // 로더들은 statsRaw 등만 쓰고 authState/activeTab은 안 써서 self-invalidation 없음. destroyed 락 없음.
  $effect(() => {
    if (authState !== 'ready') return
    const tab = activeTab
    if (tab === 'stats') {
      loadStats()
      return createPoll(loadStats, 60000)
    }
    if (tab === 'audit') {
      loadAudit()
      return createPoll(loadAudit, 60000)
    }
    if (tab === 'seats') {
      loadSeats()
      loadReservations()
      return
    }
    if (tab === 'guestbook') {
      loadGuestbook()
      return
    }
    if (tab === 'shops') {
      loadShops()
      return
    }
  })

  // --- 감사 판정 (ADM-211/212/213/214/215) ---
  function removeAudit(id) {
    if (Array.isArray(auditItems)) auditItems = auditItems.filter(v => auditId(v) !== id)
  }

  async function onAuditOk(v) {
    const id = auditId(v)
    auditBusyId = id
    try {
      await auditOk(id)
      removeAudit(id)
      showToast('문제없음으로 처리했어요', 'info')
    } catch (e) {
      handleAuditActionError(e, id)
    } finally {
      auditBusyId = null
    }
  }

  async function onAuditRevoke(v) {
    const id = auditId(v)
    if (!confirm('이 인증을 무효화할까요? 연결된 예약도 해제돼요')) return
    auditBusyId = id
    try {
      await auditRevoke(id)
      removeAudit(id)
      showToast('인증을 무효화하고 예약을 해제했어요', 'info')
    } catch (e) {
      handleAuditActionError(e, id)
    } finally {
      auditBusyId = null
    }
  }

  // 409 ALREADY_PROCESSED: 이미 처리된 것 = 판정이 반영됐다는 뜻이라 카드 제거 (ADM-214·215).
  function handleAuditActionError(e, id) {
    if (handleAuthError(e)) return
    if (e instanceof ApiError && e.status === 409) {
      removeAudit(id)
      showToast('이미 처리된 항목이에요', 'error')
      loadAudit()
      return
    }
    showToast('처리에 실패했어요. 잠시 후 다시 시도해주세요', 'error')
  }

  // --- 좌석 열기/닫기 (ADM-301/302/303) ---
  async function toggleSeat(seat) {
    const next = !seat.isOpen
    if (!next && !confirm('이 좌석을 닫을까요? 진행 중인 예약은 유지되고 새 예약만 막혀요')) return
    seatBusyId = seat.id
    try {
      await setSeatOpen(seat.id, next)
      seats = seats.map(s => (s.id === seat.id ? { ...s, isOpen: next } : s))
      showToast(next ? '좌석을 열었어요' : '좌석을 닫았어요', 'info')
    } catch (e) {
      if (!handleAuthError(e)) showToast('좌석 상태 변경에 실패했어요', 'error')
    } finally {
      seatBusyId = null
    }
  }

  // --- 예약 수동 해제 (ADM-402/403/405) ---
  async function releaseReservation(r) {
    const id = reservationId(r)
    if (!confirm('이 예약을 해제할까요? 좌석이 즉시 빈자리가 돼요')) return
    reservationBusyId = id
    try {
      await adminReleaseReservation(id)
      reservations = (reservations ?? []).filter(x => reservationId(x) !== id)
      showToast('예약을 해제했어요', 'info')
    } catch (e) {
      if (handleAuthError(e)) return
      if (e instanceof ApiError && e.status === 409) {
        reservations = (reservations ?? []).filter(x => reservationId(x) !== id)
        showToast('이미 종료된 예약이에요', 'error')
        loadReservations()
      } else {
        showToast('해제에 실패했어요. 잠시 후 다시 시도해주세요', 'error')
      }
    } finally {
      reservationBusyId = null
    }
  }

  // --- 방명록 삭제 (ADM-501/502) ---
  async function removeGuestbook(entry) {
    const id = entry.id
    if (!confirm('이 글을 삭제할까요? 되돌릴 수 없어요')) return
    guestbookBusyId = id
    try {
      await deleteGuestbook(id)
      guestbook = (guestbook ?? []).filter(g => g.id !== id)
      showToast('글을 삭제했어요', 'info')
    } catch (e) {
      if (handleAuthError(e)) return
      if (e instanceof ApiError && e.status === 404) {
        guestbook = (guestbook ?? []).filter(g => g.id !== id)
        showToast('이미 삭제된 글이에요', 'error')
      } else {
        showToast('삭제에 실패했어요. 잠시 후 다시 시도해주세요', 'error')
      }
    } finally {
      guestbookBusyId = null
    }
  }

  // --- 상점 추가/수정/비활성 (ADM-601/602/603/604) ---
  async function addShop() {
    if (!newShop.id || !newShop.name || newShopBusy) return
    newShopBusy = true
    newShopError = ''
    try {
      const created = await createShop({
        id: newShop.id.trim(),
        name: newShop.name.trim(),
        category: newShop.category.trim(),
        sortOrder: Number(newShop.sortOrder) || 0,
      })
      shops = [...(shops ?? []), created ?? { ...newShop, is_active: true }]
      newShop = { id: '', name: '', category: '', sortOrder: 0 }
      showToast('상점을 추가했어요', 'info')
    } catch (e) {
      if (handleAuthError(e)) return
      if (e instanceof ApiError && e.status === 409) {
        newShopError = '이미 있는 상점 ID예요'
      } else {
        newShopError = '추가에 실패했어요. 잠시 후 다시 시도해주세요'
      }
    } finally {
      newShopBusy = false
    }
  }

  function startEditShop(shop) {
    editingShopId = shop.id
    shopEdit = {
      name: shop.name ?? '',
      category: shop.category ?? '',
      sortOrder: shop.sort_order ?? 0,
    }
  }

  async function saveShop(shop) {
    shopBusyId = shop.id
    try {
      const patch = {
        name: shopEdit.name.trim(),
        category: shopEdit.category.trim(),
        sortOrder: Number(shopEdit.sortOrder) || 0,
      }
      const updated = await updateShop(shop.id, patch)
      shops = (shops ?? []).map(s =>
        s.id === shop.id ? (updated ?? { ...s, name: patch.name, category: patch.category, sort_order: patch.sortOrder }) : s,
      )
      editingShopId = null
      showToast('상점 정보를 수정했어요', 'info')
    } catch (e) {
      if (!handleAuthError(e)) showToast('수정에 실패했어요', 'error')
    } finally {
      shopBusyId = null
    }
  }

  async function toggleShopActive(shop) {
    const next = !(shop.is_active ?? true)
    if (!next && !confirm('이 상점을 비활성화할까요? 신규 인증·태그에서 제외돼요')) return
    shopBusyId = shop.id
    try {
      const updated = await updateShop(shop.id, { isActive: next })
      shops = (shops ?? []).map(s =>
        s.id === shop.id ? (updated ?? { ...s, is_active: next }) : s,
      )
      showToast(next ? '상점을 활성화했어요' : '상점을 비활성화했어요', 'info')
    } catch (e) {
      if (!handleAuthError(e)) showToast('변경에 실패했어요', 'error')
    } finally {
      shopBusyId = null
    }
  }

  // --- id 추출 헬퍼 (백엔드 응답 키 방어) ---
  function auditId(v) {
    return v?.id ?? v?.verification_id
  }
  function reservationId(r) {
    return r?.id ?? r?.reservation_id
  }
  function seatLabelOf(r) {
    return r?.seat_label ?? r?.seat?.label ?? (r?.seat_id ? String(r.seat_id).toUpperCase() : '—')
  }
  function auditReason(v) {
    return v?.reason_code ?? v?.audit_reason ?? v?.flag_reason ?? ''
  }
</script>

<div class="mx-auto max-w-2xl px-4 py-4">
  <header class="mb-4 flex items-center justify-between">
    <h1 class="text-lg font-bold text-flow-black">멈춰, 섬! · 관리자</h1>
    {#if authState === 'ready'}
      <span class="text-xs text-gray-400">원격 모니터링</span>
    {/if}
  </header>

  {#if authState === 'checking'}
    <div class="flex justify-center py-16 text-gray-400"><Spinner size="lg" /></div>
  {:else if authState === 'login'}
    <!-- 로그인 게이트 (ADM-101/102/103/105, D-21) -->
    <form class="mx-auto mt-10 flex max-w-xs flex-col gap-3" onsubmit={handleLogin}>
      <label class="text-sm font-medium text-gray-700" for="admin-pw">관리자 비밀번호</label>
      <input
        id="admin-pw"
        type="password"
        bind:value={password}
        autocomplete="current-password"
        class="min-h-[44px] rounded-xl border border-gray-300 px-3 py-2 text-base focus:border-flow-black focus:outline-none"
        placeholder="비밀번호"
      />
      {#if loginError}
        <p class="text-sm text-red-600">{loginError}</p>
      {/if}
      <Button type="submit" loading={loginLoading} disabled={!password}>로그인</Button>
    </form>
  {:else}
    <!-- 탭 바 -->
    <nav class="mb-4 flex gap-1 overflow-x-auto border-b border-gray-200">
      {#each TABS as tab (tab.id)}
        <button
          type="button"
          onclick={() => (activeTab = tab.id)}
          class="relative min-h-[44px] whitespace-nowrap px-3 py-2 text-sm font-medium transition-colors {activeTab ===
          tab.id
            ? 'border-b-2 border-flow-black text-flow-black'
            : 'text-gray-500'}"
        >
          {tab.label}
          {#if tab.id === 'audit' && auditBadge > 0}
            <span
              class="ml-1 inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-xs font-bold text-white"
              >{auditBadge}</span
            >
          {/if}
        </button>
      {/each}
    </nav>

    <!-- === 통계 === -->
    {#if activeTab === 'stats'}
      {#if statsLoading && !statsRaw}
        <div class="grid grid-cols-2 gap-3">
          {#each Array(6) as _}
            <Skeleton class="h-20 w-full" />
          {/each}
        </div>
      {:else if statsError && !statsRaw}
        <ErrorState message="통계를 불러오지 못했어요" onRetry={loadStats} />
      {:else}
        <div class="grid grid-cols-2 gap-3">
          {#each statCards as card (card.key)}
            <button
              type="button"
              disabled={!card.tab}
              onclick={() => card.tab && (activeTab = card.tab)}
              class="flex flex-col items-start rounded-xl border border-gray-200 bg-white p-3 text-left disabled:cursor-default {card.tab
                ? 'active:bg-gray-50'
                : ''}"
            >
              <span class="text-xs text-gray-500">{card.label}</span>
              <span class="mt-1 text-xl font-bold text-flow-black">{card.value}</span>
              {#if card.hint}<span class="mt-0.5 text-[11px] text-gray-400">{card.hint}</span>{/if}
            </button>
          {/each}
        </div>
      {/if}

    <!-- === 감사 큐 === -->
    {:else if activeTab === 'audit'}
      {#if auditLoading && auditItems === null}
        <div class="flex flex-col gap-3">
          {#each Array(3) as _}<Skeleton class="h-28 w-full" />{/each}
        </div>
      {:else if auditError && auditItems === null}
        <ErrorState message="감사 큐를 불러오지 못했어요" onRetry={loadAudit} />
      {:else if !auditItems || auditItems.length === 0}
        <EmptyState message="감사할 인증이 없어요" />
      {:else}
        <ul class="flex flex-col gap-3">
          {#each auditItems as v (auditId(v))}
            <li class="rounded-xl border border-gray-200 bg-white p-3">
              <div class="mb-2 flex items-center gap-2 text-xs">
                <span class="rounded bg-gray-100 px-2 py-0.5 font-medium text-gray-600"
                  >{v.method === 'manual' ? '직접선택' : '사진'}</span
                >
                {#if auditReason(v)}
                  <span class="rounded bg-amber-100 px-2 py-0.5 font-medium text-amber-700"
                    >{auditReason(v)}</span
                  >
                {/if}
                <span class="ml-auto text-gray-400">{v.created_at ? timeAgo(v.created_at) : ''}</span>
              </div>

              {#if v.method === 'manual'}
                <p class="mb-2 text-sm text-gray-700">
                  상점 직접 선택: {v.ocr_store_name ?? v.shop_id ?? '알 수 없음'}
                </p>
              {:else if v.image_url}
                <a href={v.image_url} target="_blank" rel="noreferrer" class="mb-2 block">
                  <img
                    src={v.image_url}
                    alt="영수증"
                    class="max-h-40 w-full rounded-lg object-contain"
                    onerror={e => (e.currentTarget.style.display = 'none')}
                  />
                </a>
              {:else}
                <p class="mb-2 rounded-lg bg-gray-50 px-3 py-4 text-center text-xs text-gray-400">
                  이미지를 불러올 수 없어요
                </p>
              {/if}

              <dl class="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-gray-600">
                <div><dt class="inline text-gray-400">상호</dt> {v.ocr_store_name ?? '—'}</div>
                <div><dt class="inline text-gray-400">결제일</dt> {v.ocr_date ?? '—'}</div>
                <div>
                  <dt class="inline text-gray-400">확신도</dt>
                  {v.confidence != null ? v.confidence : '—'}
                </div>
                <div class="col-span-2">
                  <dt class="inline text-gray-400">연결 예약</dt>
                  {v.reservation ? seatLabelOf(v.reservation) : (v.seat_label ?? '예약 없음')}
                </div>
              </dl>

              <div class="flex gap-2">
                <div class="flex-1">
                  <Button
                    variant="ghost"
                    loading={auditBusyId === auditId(v)}
                    onclick={() => onAuditOk(v)}>문제없음</Button
                  >
                </div>
                <div class="flex-1">
                  <button
                    type="button"
                    disabled={auditBusyId === auditId(v)}
                    onclick={() => onAuditRevoke(v)}
                    class="min-h-[44px] w-full rounded-xl border border-red-300 px-4 py-3 text-base font-bold text-red-600 active:bg-red-50 disabled:opacity-50"
                    >어뷰징—무효화</button
                  >
                </div>
              </div>
            </li>
          {/each}
        </ul>
      {/if}

    <!-- === 좌석·예약 === -->
    {:else if activeTab === 'seats'}
      <section class="mb-6">
        <h2 class="mb-2 text-sm font-bold text-gray-700">좌석 열기/닫기</h2>
        <div class="grid grid-cols-3 gap-2">
          {#each seats as seat (seat.id)}
            <button
              type="button"
              disabled={seatBusyId === seat.id}
              onclick={() => toggleSeat(seat)}
              class="flex min-h-[56px] flex-col items-center justify-center rounded-xl border px-2 py-2 text-sm font-bold disabled:opacity-50 {seat.isOpen
                ? 'border-gray-300 bg-white text-flow-black'
                : 'border-gray-200 bg-gray-100 text-gray-400'}"
            >
              <span>{seat.label}</span>
              <span class="text-[11px] font-medium">{seat.isOpen ? '열림 · 탭하면 닫기' : '닫힘 · 탭하면 열기'}</span>
            </button>
          {/each}
        </div>
      </section>

      <section>
        <h2 class="mb-2 text-sm font-bold text-gray-700">진행 중인 예약</h2>
        {#if reservationsLoading && reservations === null}
          <div class="flex flex-col gap-2">
            {#each Array(2) as _}<Skeleton class="h-16 w-full" />{/each}
          </div>
        {:else if reservationsError && reservations === null}
          <ErrorState message="예약을 불러오지 못했어요" onRetry={loadReservations} />
        {:else if !reservations || reservations.length === 0}
          <EmptyState message="진행 중인 예약이 없어요" />
        {:else}
          <ul class="flex flex-col gap-2">
            {#each reservations as r (reservationId(r))}
              <li class="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-3">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-bold text-flow-black">{seatLabelOf(r)}</span>
                    <span class="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-500"
                      >{r.method === 'manual' ? '직접선택' : '사진'}</span
                    >
                    {#if r.needs_audit}
                      <span class="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-700"
                        >미감사</span
                      >
                    {/if}
                  </div>
                  <p class="mt-0.5 text-xs text-gray-500">{formatExpiry(r.expires_at)}</p>
                </div>
                <button
                  type="button"
                  disabled={reservationBusyId === reservationId(r)}
                  onclick={() => releaseReservation(r)}
                  class="min-h-[44px] shrink-0 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 active:bg-gray-50 disabled:opacity-50"
                  >예약 해제</button
                >
              </li>
            {/each}
          </ul>
        {/if}
      </section>

    <!-- === 방명록 === -->
    {:else if activeTab === 'guestbook'}
      {#if guestbookLoading && guestbook === null}
        <div class="flex flex-col gap-2">
          {#each Array(4) as _}<Skeleton class="h-16 w-full" />{/each}
        </div>
      {:else if guestbookError && guestbook === null}
        <ErrorState message="방명록을 불러오지 못했어요" onRetry={loadGuestbook} />
      {:else if !guestbook || guestbook.length === 0}
        <EmptyState message="방명록 글이 없어요" />
      {:else}
        <ul class="flex flex-col gap-2">
          {#each guestbook as entry (entry.id)}
            <li class="flex items-start gap-3 rounded-xl border border-gray-200 bg-white p-3">
              <div class="min-w-0 flex-1">
                <p class="text-sm text-flow-black whitespace-pre-wrap break-words">{entry.content}</p>
                <p class="mt-1 text-[11px] text-gray-400">
                  익명 방문자 · {entry.created_at ? timeAgo(entry.created_at) : ''}
                </p>
              </div>
              <button
                type="button"
                disabled={guestbookBusyId === entry.id}
                onclick={() => removeGuestbook(entry)}
                class="min-h-[44px] shrink-0 rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-600 active:bg-red-50 disabled:opacity-50"
                >삭제</button
              >
            </li>
          {/each}
        </ul>
      {/if}

    <!-- === 상점 === -->
    {:else if activeTab === 'shops'}
      <section class="mb-6 rounded-xl border border-gray-200 bg-white p-3">
        <h2 class="mb-2 text-sm font-bold text-gray-700">상점 추가</h2>
        <div class="flex flex-col gap-2">
          <input
            bind:value={newShop.id}
            placeholder="슬러그 (예: cafe-haeng)"
            class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-flow-black focus:outline-none"
          />
          <input
            bind:value={newShop.name}
            placeholder="상점 이름"
            class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-flow-black focus:outline-none"
          />
          <div class="flex gap-2">
            <input
              bind:value={newShop.category}
              placeholder="카테고리"
              class="min-h-[44px] flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-flow-black focus:outline-none"
            />
            <input
              bind:value={newShop.sortOrder}
              type="number"
              placeholder="정렬"
              class="min-h-[44px] w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-flow-black focus:outline-none"
            />
          </div>
          {#if newShopError}<p class="text-sm text-red-600">{newShopError}</p>{/if}
          <Button loading={newShopBusy} disabled={!newShop.id || !newShop.name} onclick={addShop}
            >추가</Button
          >
        </div>
      </section>

      {#if shopsLoading && shops === null}
        <div class="flex flex-col gap-2">
          {#each Array(4) as _}<Skeleton class="h-14 w-full" />{/each}
        </div>
      {:else if shopsError && shops === null}
        <ErrorState message="상점을 불러오지 못했어요" onRetry={loadShops} />
      {:else if !shops || shops.length === 0}
        <EmptyState message="등록된 상점이 없어요" />
      {:else}
        <ul class="flex flex-col gap-2">
          {#each shops as shop (shop.id)}
            <li class="rounded-xl border border-gray-200 bg-white p-3">
              {#if editingShopId === shop.id}
                <div class="flex flex-col gap-2">
                  <input
                    bind:value={shopEdit.name}
                    placeholder="이름"
                    class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-flow-black focus:outline-none"
                  />
                  <div class="flex gap-2">
                    <input
                      bind:value={shopEdit.category}
                      placeholder="카테고리"
                      class="min-h-[44px] flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-flow-black focus:outline-none"
                    />
                    <input
                      bind:value={shopEdit.sortOrder}
                      type="number"
                      class="min-h-[44px] w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-flow-black focus:outline-none"
                    />
                  </div>
                  <div class="flex gap-2">
                    <button
                      type="button"
                      onclick={() => (editingShopId = null)}
                      class="min-h-[44px] flex-1 rounded-lg border border-gray-300 text-sm font-medium text-gray-600"
                      >취소</button
                    >
                    <button
                      type="button"
                      disabled={shopBusyId === shop.id}
                      onclick={() => saveShop(shop)}
                      class="min-h-[44px] flex-1 rounded-lg bg-island-yellow text-sm font-bold text-flow-black disabled:opacity-50"
                      >저장</button
                    >
                  </div>
                </div>
              {:else}
                <div class="flex items-center gap-3">
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2">
                      <span class="text-sm font-bold text-flow-black">{shop.name}</span>
                      {#if !(shop.is_active ?? true)}
                        <span class="rounded bg-gray-200 px-1.5 py-0.5 text-[11px] text-gray-500"
                          >비활성</span
                        >
                      {/if}
                    </div>
                    <p class="text-[11px] text-gray-400">{shop.category ?? ''} · {shop.id}</p>
                  </div>
                  <button
                    type="button"
                    onclick={() => startEditShop(shop)}
                    class="min-h-[44px] shrink-0 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 active:bg-gray-50"
                    >수정</button
                  >
                  <button
                    type="button"
                    disabled={shopBusyId === shop.id}
                    onclick={() => toggleShopActive(shop)}
                    class="min-h-[44px] shrink-0 rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-50 {(shop.is_active ??
                    true)
                      ? 'border-gray-300 text-gray-700 active:bg-gray-50'
                      : 'border-island-yellow bg-island-yellow text-flow-black'}"
                    >{(shop.is_active ?? true) ? '비활성화' : '활성화'}</button
                  >
                </div>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    {/if}
  {/if}
</div>
