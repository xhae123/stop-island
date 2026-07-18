<script>
  // 예약 완료 화면 (D-09, J3). 본인 확인용 — QR·종이 없는 명예 시스템(RSV-601).
  // 마운트 시 서버에서 예약을 확정 조회하고, 남은 시간 카운트다운 + 주기적 서버 재확인으로
  // 만료(RSV-604)·감사/관리자 취소(RSV-608)를 화면에 반영한다. 소유 아님(403/404)은 조용히 메인으로.
  import { push } from 'svelte-spa-router'
  import { getReservation, cancelReservation, ApiError } from '../lib/api.js'
  import { reservation, clearReservation } from '../lib/store.svelte.js'
  import { showToast } from '../lib/toast.svelte.js'
  import { formatRemaining } from './reserveLogic.js'
  import Button from '../components/Button.svelte'
  import Skeleton from '../components/Skeleton.svelte'
  import ErrorState from '../components/ErrorState.svelte'

  let { params } = $props()
  const id = $derived(params?.id)

  let phase = $state('loading') // loading | active | expired | cancelled | error
  let res = $state(null)
  let errMsg = $state('')
  let now = $state(Date.now())
  let releasing = $state(false)
  let showConfirm = $state(false)
  let expiryChecked = false // 남은 시간 0 도달 시 서버 재확인 1회 가드

  // 표시 값(형태 방어: seat 객체 우선, 없으면 평면 필드 폴백).
  const seatLabel = $derived(res?.seat?.label ?? res?.seat_label ?? res?.label ?? '내 자리')
  const capacity = $derived(res?.seat?.capacity ?? res?.capacity ?? null)
  const positionLabel = $derived(res?.seat?.position_label ?? res?.position_label ?? '')

  // 절대 만료 시각 "HH:MM" (서버 KST 기준, D-01).
  const expiresClock = $derived.by(() => {
    if (!res?.expires_at) return ''
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(new Date(res.expires_at))
  })

  const remainingSec = $derived(
    res?.expires_at ? Math.floor((new Date(res.expires_at).getTime() - now) / 1000) : 0,
  )

  function apply(r) {
    res = r
    if (!r || r.status === 'expired') {
      phase = 'expired'
      clearReservation()
    } else if (r.status === 'cancelled') {
      phase = 'cancelled'
      clearReservation()
    } else {
      phase = 'active'
      expiryChecked = false
    }
  }

  async function load() {
    phase = 'loading'
    try {
      apply(await getReservation(id))
    } catch (e) {
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
        // 소유 아님/없음 → 조용히 메인으로(RSV-801·803). 내 저장 id면 정리.
        if (reservation.id === id) clearReservation()
        push('/')
        return
      }
      errMsg = e?.message || '예약을 불러오지 못했어요.'
      phase = 'error'
    }
  }

  // 마운트 로드 + id(route param)가 바뀌면 재로드. $effect를 유지하는 이유: 같은 컴포넌트가
  // 재사용되며 /reservation/:id의 id만 바뀌는 전환에 반드시 재실행돼야 한다(onMount는 1회뿐이라 부적합).
  // self-invalidation 없음: id만 읽고 load()는 id를 쓰지 않는다. destroyed 락 플래그도 없다.
  $effect(() => {
    if (id) load()
  })

  // active 동안: 30초마다 카운트다운 표시 갱신 + 60초마다 서버 재확인(만료/취소 감지 — RSV-604·608).
  // $effect 유지: 타이머 설치가 phase==='active'에 게이트돼 있어 phase 변화에 따라 켜지고 꺼져야 한다
  // (onMount로 두면 만료/취소 후에도 폴링이 안 멈춘다). phase만 읽고 setInterval 콜백은 비동기라
  // effect 본문에서 phase를 즉시 쓰지 않아 self-invalidation 루프는 없다. destroyed 락 플래그도 없다.
  $effect(() => {
    if (phase !== 'active') return
    const clock = setInterval(() => { now = Date.now() }, 30000)
    const sync = setInterval(async () => {
      try { apply(await getReservation(id)) } catch { /* 무음 유지 */ }
    }, 60000)
    return () => { clearInterval(clock); clearInterval(sync) }
  })

  // 남은 시간이 0에 도달하면 즉시(다음 60초 주기 기다리지 않고) 서버로 만료 확정(RSV-604, D-01).
  // $effect 유지: remainingSec(now 파생)가 0을 넘는 순간에 반응해야 하는 진짜 리액티브 로직이다.
  // expiryChecked는 일반 let(비reactive) 1회 가드라 써도 재실행을 유발하지 않는다 → self-invalidation 없음.
  $effect(() => {
    if (phase === 'active' && remainingSec <= 0 && !expiryChecked && res?.expires_at) {
      expiryChecked = true
      getReservation(id).then(apply).catch(() => {})
    }
  })

  async function release() {
    releasing = true
    try {
      await cancelReservation(id) // 만료 스윕과 경합해도 서버가 멱등 처리(RSV-606)
      clearReservation()
      showConfirm = false
      showToast('이용해주셔서 감사해요', 'info')
      push('/')
    } catch {
      // 실패 시 완료 화면·예약 유지(RSV-605)
      showConfirm = false
      showToast('자리 비우기에 실패했어요. 다시 시도해주세요', 'error')
    } finally {
      releasing = false
    }
  }
</script>

{#if phase === 'loading'}
  <div class="flex flex-col items-center gap-4 px-6 pt-16">
    <Skeleton class="h-16 w-24 rounded-2xl" />
    <Skeleton class="h-4 w-40" />
    <Skeleton class="h-4 w-56" />
  </div>

{:else if phase === 'error'}
  <ErrorState message={errMsg} onRetry={load} />

{:else if phase === 'active'}
  <div class="flex flex-col px-6 pt-10 pb-10">
    <div class="mb-6 flex flex-col items-center">
      <div class="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-island-yellow">
        <svg class="h-8 w-8 text-flow-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
      </div>
      <h1 class="text-xl font-bold text-flow-black">예약이 확정됐어요</h1>
      <p class="mt-1 text-sm text-gray-500">내 자리와 이용 시간을 확인하는 화면이에요</p>
    </div>

    <!-- 좌석·시간 카드 -->
    <div class="mb-6 rounded-2xl bg-gray-50 px-6 py-6 text-center">
      <p class="mb-1 text-5xl font-extrabold tracking-tight text-flow-black">{seatLabel}</p>
      <p class="mb-5 text-sm font-medium text-gray-600">
        {#if capacity}{capacity}인석{/if}{positionLabel ? ` · ${positionLabel}` : ''}
      </p>
      <div class="rounded-xl bg-island-yellow-light px-4 py-3">
        <p class="text-sm font-semibold text-flow-black">{expiresClock}까지 이용 가능</p>
        <p class="mt-0.5 text-xs text-gray-600">남은 시간 {formatRemaining(remainingSec)}</p>
      </div>
    </div>

    <!-- 기대치 설정(D-27): 알림 없이 자동 만료 — 유저가 나가기 전에 규칙을 알도록 -->
    <div class="mb-6 rounded-2xl border border-gray-100 bg-white px-5 py-4">
      <p class="text-[13px] leading-relaxed text-gray-600">
        시간이 되면 <span class="font-semibold text-flow-black">자동으로 자리가 정리</span>돼요.
        따로 <span class="font-semibold text-flow-black">알림은 가지 않으니</span> 남은 시간을 확인해주세요.
      </p>
      <p class="mt-1.5 text-[13px] leading-relaxed text-gray-600">
        더 머물고 싶으면 시간 안에 <span class="font-semibold text-flow-black">다시 잡을 수 있어요.</span>
      </p>
    </div>

    <div class="space-y-3">
      <Button onclick={() => push('/guestbook')}>방명록 쓰기</Button>
      <Button variant="ghost" onclick={() => (showConfirm = true)}>자리 비우기</Button>
    </div>
  </div>

  <!-- 자리 비우기 확인 다이얼로그(RSV-602·603) -->
  {#if showConfirm}
    <div class="fixed inset-0 z-[70] mx-auto flex max-w-[430px] items-end justify-center bg-black/40 px-4 pb-6"
         style="padding-bottom: calc(1.5rem + env(safe-area-inset-bottom));">
      <div class="w-full rounded-2xl bg-white p-5 shadow-xl">
        <p class="mb-1 text-base font-bold text-flow-black">자리를 비울까요?</p>
        <p class="mb-5 text-sm text-gray-500">예약이 취소돼요</p>
        <div class="space-y-2">
          <Button onclick={release} loading={releasing}>비우기</Button>
          <Button variant="ghost" onclick={() => (showConfirm = false)} disabled={releasing}>취소</Button>
        </div>
      </div>
    </div>
  {/if}

{:else}
  <!-- 만료(RSV-604) / 취소(RSV-608·J2.1d-2) 공통 종료 상태 화면. 취소 사유는 구분하지 않는다(D-09). -->
  <div class="flex flex-col items-center px-6 pt-16 pb-10 text-center">
    <div class="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-gray-100">
      <svg class="h-8 w-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l2.5 2.5M12 3a9 9 0 100 18 9 9 0 000-18z" />
      </svg>
    </div>
    <h1 class="mb-2 text-xl font-bold text-flow-black">
      {phase === 'cancelled' ? '예약이 취소되었어요' : '이용 시간이 끝났어요'}
    </h1>
    <p class="mb-8 text-sm text-gray-500">
      {phase === 'cancelled' ? seatLabel : '오늘 다시 예약할 수 있어요'}
    </p>
    <div class="w-full max-w-xs">
      <Button onclick={() => push('/')}>메인으로</Button>
    </div>
  </div>
{/if}
