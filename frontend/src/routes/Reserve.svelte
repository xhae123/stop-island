<script>
  // 04 이 자리 확정 (RSV-*, D-26). 좌석 그리드는 폐기 — 좌석은 찍은 QR로 이미 정해졌다.
  // 이 화면은 stop-island:seat가 가리키는 "찍은 자리 하나"를 보여주고 [이 자리 예약하기] 확정 1회를 담당한다.
  // 헤더/드로어는 App 셸이 마운트한다. 진입 가드(D-14·D-26: 토큰 없음→/verify, seat 없음→/)는
  // App의 wrap(conditions)이 처리. 이 화면은 (1) active 예약 보유 시 완료 화면 리다이렉트(RSV-104),
  //          (2) 찍은 자리 상태 30초 폴링, (3) 확정/선점(409)/토큰만료 처리를 담당한다.
  import { onMount } from 'svelte'
  import { push } from 'svelte-spa-router'
  import { getSeatStatus, reserve, ApiError } from '../lib/api.js'
  import {
    verify, loadVerify,
    seat, loadSeat,
    saveReservationId, clearVerify, reconcileReservation,
  } from '../lib/store.svelte.js'
  import { createPoll } from '../lib/poll.js'
  import { showToast } from '../lib/toast.svelte.js'
  import { seatSubLabel, seatUnavailableMessage, canConfirmSeat, SEAT_TAKEN_MESSAGE, RESCAN_MESSAGE } from './reserveLogic.js'
  import Button from '../components/Button.svelte'
  import Skeleton from '../components/Skeleton.svelte'
  import ErrorState from '../components/ErrorState.svelte'

  let seatInfo = $state(null) // 찍은 자리의 서버 상태 { id, label, capacity, position_label, state }
  let loadState = $state('loading') // loading | ready | error (첫 로드만; 폴링 실패는 무음 — RSV-403)
  let confirming = $state(false) // 확정 요청 중(더블탭 방지 — RSV-504)
  let redirecting = $state(false) // active 예약 리다이렉트 판정 중

  let destroyed = false

  // 표시 라벨: 서버 label 우선, 없으면 seat id를 대문자로.
  const seatLabel = $derived(seatInfo?.label ?? (seat.id ? seat.id.toUpperCase() : ''))
  const seatState = $derived(seatInfo?.state ?? null)
  // 찍은 자리가 사용 중/운영 중지 → 확정 불가, 재스캔 안내(D-26).
  const unavailable = $derived(loadState === 'ready' && seatInfo != null && seatState !== 'available')
  // seat id는 있는데 좌석 목록에 없음(알 수 없는 QR) → 재스캔 안내.
  const seatMissing = $derived(loadState === 'ready' && (!seat.id || seatInfo == null))

  // 찍은 자리 상태 재요청. 폴링 실패는 직전 데이터 유지(RSV-403), 첫 로드 실패만 표면화(RSV-204).
  async function fetchSeat() {
    try {
      const s = await getSeatStatus(seat.id)
      if (destroyed) return
      seatInfo = s
      loadState = 'ready'
    } catch {
      if (loadState === 'loading') loadState = 'error'
    }
  }

  function retryLoad() {
    loadState = 'loading'
    fetchSeat()
  }

  // 마운트: verify/seat 하이드레이트 → active 예약 있으면 완료 화면으로(RSV-104) → 아니면 좌석 상태 폴링 시작.
  // onMount로 하는 이유: 이건 1회성 마운트 사이드이펙트다. $effect로 두면 loadVerify()/loadSeat()가
  // seat.id(reactive)를 쓰고 fetchSeat()가 그걸 읽어 self-invalidate → effect 재실행 → cleanup이
  // destroyed=true를 걸어 loadState가 영영 'loading'에 갇힌다(스켈레톤 고정 버그). onMount는 정확히
  // 1회 실행되고 cleanup은 실제 언마운트에만 돌아 destroyed가 올바르게 세팅된다.
  onMount(() => {
    loadVerify()
    loadSeat()
    let stop = () => {}

    ;(async () => {
      try {
        const r = await reconcileReservation()
        if (destroyed) return
        // GET /api/reservations/:id 응답은 reservation_id 키를 쓴다(seat는 중첩).
        if (r && r.reservation_id) {
          redirecting = true
          push(`/reservation/${r.reservation_id}`)
          return
        }
      } catch {
        // 네트워크 오류 등은 무시하고 진행(로컬 예약 id는 store가 유지).
      }
      if (destroyed) return
      await fetchSeat()
      if (destroyed) return
      // 확정 요청 중엔 폴링 스킵(응답 뒤섞임 방지). 확정 성공 시 완료 화면으로 떠나므로 사실상 1회성.
      stop = createPoll(() => { if (!confirming) fetchSeat() }, 30000)
    })()

    return () => {
      destroyed = true
      stop()
    }
  })

  async function confirm() {
    if (confirming || seatState !== 'available') return // 연타·비가용 방어(RSV-504)
    confirming = true
    try {
      const res = await reserve({ seatId: seat.id, verifyToken: verify.current?.token })
      saveReservationId(res.reservation_id) // D-10
      push(`/reservation/${res.reservation_id}`) // 성공 → 완료 화면(RSV-501)
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.code === 'SEAT_TAKEN') {
          // 409 선점: 그리드가 없으니 재선택이 아니라 재스캔 유도(D-26). 상태 갱신 → unavailable UI.
          showToast(SEAT_TAKEN_MESSAGE, 'error')
          await fetchSeat()
        } else if (e.code === 'TOKEN_EXPIRED' || e.code === 'TOKEN_NOT_FOUND') {
          // 자정 경과 등 토큰 만료: 재인증으로(RSV-503).
          clearVerify()
          showToast('인증이 만료되었어요. 오늘 영수증으로 다시 인증해주세요', 'error')
          push('/verify')
        } else if (e.code === 'ALREADY_RESERVED') {
          // 응답 유실·두 탭 경합 복구: 이미 내 예약이 있음(RSV-506·105).
          // 백엔드가 409 봉투 밖에 기존 reservation_id를 함께 실어준다(e.body.reservation_id).
          const existingId = e.body?.reservation_id
          if (existingId) {
            saveReservationId(existingId)
            push(`/reservation/${existingId}`)
          } else {
            showToast('이미 예약이 되어 있어요', 'info')
          }
        } else {
          showToast(e.message || '예약을 확정하지 못했어요. 다시 시도해주세요', 'error')
        }
      } else {
        // 네트워크/타임아웃(RSV-505).
        showToast('예약을 확정하지 못했어요. 다시 시도해주세요', 'error')
      }
    } finally {
      confirming = false
    }
  }
</script>

{#if !redirecting}
  <!-- 인증 완료 배너(정적, RSV-102) -->
  <div class="flex items-center gap-2 bg-island-yellow px-5 py-3">
    <svg class="h-5 w-5 shrink-0 text-flow-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
      <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
    </svg>
    <span class="text-sm font-semibold text-flow-black">
      {verify.current?.shop_name ?? '영수증'} 영수증 인증 완료
    </span>
  </div>

  <div class="flex min-h-[calc(100vh-104px)] flex-col px-5 pt-6 pb-10">
    {#if loadState === 'loading'}
      <Skeleton class="h-40 w-full rounded-2xl" />
    {:else if loadState === 'error'}
      <ErrorState message="좌석 정보를 불러오지 못했어요" onRetry={retryLoad} />

    {:else if seatMissing}
      <!-- 알 수 없는 좌석 QR: 재스캔 안내(D-26) -->
      <div class="flex flex-1 flex-col items-center justify-center gap-3 text-center">
        <h1 class="text-lg font-bold text-flow-black">좌석을 찾을 수 없어요</h1>
        <p class="text-sm text-gray-500">{RESCAN_MESSAGE}</p>
      </div>

    {:else if unavailable}
      <!-- 찍은 자리가 사용 중/운영 중지: 확정 버튼 없이 재스캔 안내(D-26) -->
      <div class="flex flex-1 flex-col items-center justify-center gap-3 text-center">
        <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-gray-100 text-lg font-extrabold text-gray-400">
          {seatLabel}
        </div>
        <h1 class="text-lg font-bold text-flow-black">{seatUnavailableMessage(seatState)}</h1>
        <p class="text-sm text-gray-500">{RESCAN_MESSAGE}</p>
      </div>

    {:else}
      <!-- 찍은 자리 확정(D-26): 좌석 하나 + [이 자리 예약하기] 버튼 하나 -->
      <div class="flex flex-1 flex-col">
        <p class="text-sm text-gray-500">이 자리를 예약할게요</p>
        <div class="mt-4 rounded-2xl border-2 border-island-yellow bg-island-yellow-light px-5 py-6">
          <div class="flex items-center gap-4">
            <div class="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-island-yellow text-2xl font-extrabold text-flow-black">
              {seatLabel}
            </div>
            <div class="min-w-0">
              <p class="text-lg font-bold text-flow-black">{seatLabel} 자리</p>
              <p class="mt-0.5 text-sm text-gray-600">
                {seatSubLabel(seatState, seatInfo?.capacity)}{seatInfo?.position_label ? ` · ${seatInfo.position_label}` : ''}
              </p>
            </div>
          </div>
        </div>

        <div class="mt-auto pt-8">
          <Button onclick={confirm} disabled={!canConfirmSeat(seatState, confirming)} loading={confirming}>
            이 자리({seatLabel}) 예약하기
          </Button>
        </div>
      </div>
    {/if}
  </div>
{/if}
