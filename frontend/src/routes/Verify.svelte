<script module>
  // ── 순수 로직(테스트 대상, VF-*) — 컴포넌트 인스턴스와 무관하게 export ──

  // 클라이언트 사전 검증 규약(§8, VF-202~205): JPG/PNG · 10MB 이하만.
  export const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10,485,760 bytes
  export const ALLOWED_TYPES = ['image/jpeg', 'image/png']

  // 서버 도달 전 그 자리에서 차단. { ok } 또는 { ok:false, message }.
  // 왜 granular 문구인가: VF-202~205가 각각 다른 사유·조치를 정의한다(스펙 문구 우선, §12).
  export function validateImageFile(file) {
    if (!file) return { ok: false, message: '사진을 읽을 수 없어요. 다른 사진으로 다시 시도해주세요.' }

    const name = (file.name || '').toLowerCase()
    const isHeic = file.type === 'image/heic' || file.type === 'image/heif' || /\.(heic|heif)$/.test(name)
    if (isHeic) {
      return {
        ok: false,
        message: '지원하지 않는 사진 형식이에요(HEIC). 카메라로 다시 촬영하거나, 설정 > 카메라 > 포맷을 "높은 호환성"으로 바꿔주세요.',
      }
    }

    if (!ALLOWED_TYPES.includes(file.type)) {
      return { ok: false, message: 'JPG 또는 PNG 사진만 올릴 수 있어요.' }
    }

    if (file.size === 0) {
      return { ok: false, message: '사진을 읽을 수 없어요. 다른 사진으로 다시 시도해주세요.' }
    }

    if (file.size > MAX_FILE_SIZE) {
      return { ok: false, message: '파일이 너무 커요. 10MB 이하 사진으로 올려주세요.' }
    }

    return { ok: true }
  }

  // reason_code → 사용자 문구(03-verify.md 표). 서버가 message를 주면 그걸 우선하고,
  // 이 맵은 폴백/일관성 보장용. 알 수 없는 코드는 안전한 기본 문구.
  const REASON_MESSAGES = {
    NOT_RECEIPT: '영수증 사진이 아닌 것 같아요. 영수증이 잘 보이게 다시 찍어주세요.',
    MISSING_REQUIRED_FIELD: '영수증 정보를 읽지 못했어요. 상호명이 잘 보이게 다시 찍어주세요.',
    NOT_TODAY: '오늘 결제한 영수증만 인정돼요.',
    SHOP_NOT_PARTICIPATING: '참여 상점의 영수증이 아니에요. 참여 상점 목록을 확인해주세요.',
    DUPLICATE_RECEIPT: '이미 사용된 영수증이에요.',
    // 최소 결제금액 정책(📌 5,000원 — 파트너 협의 후 확정, 서버 설정값). 500원짜리로 자리 잡는 것 방지.
    UNDER_MIN_AMOUNT: '최소 결제금액(5,000원) 이상 영수증만 인정돼요.',
    REVOKED_BY_AUDIT: '운영진 확인 결과 인증이 취소되었어요. 다시 인증해주세요.',
    INVALID_IMAGE: '이미지를 읽을 수 없어요. 다른 사진으로 다시 시도해주세요.',
    INVALID_REQUEST: '영수증 사진을 올리거나 상점을 선택해주세요.',
  }

  export function reasonMessage(reasonCode) {
    return REASON_MESSAGES[reasonCode] ?? '인증에 실패했어요. 다시 시도해주세요.'
  }
</script>

<script>
  // 영수증 인증(03) — VF-* / J2.1~J2.3.
  // Header는 셸 마운트(App.svelte) — 자기 헤더를 심지 않는다.
  import { onMount } from 'svelte'
  import { push } from 'svelte-spa-router'
  import { verifyReceipt, getShops, getVerifyStatus, ApiError } from '../lib/api.js'
  import { saveVerify, clearVerify, loadVerify, seat, loadSeat } from '../lib/store.svelte.js'
  import Button from '../components/Button.svelte'
  import Spinner from '../components/Spinner.svelte'
  import { showToast } from '../lib/toast.svelte.js'

  // 찍은 자리 맥락(D-26): seat 있으면 "A3 자리 인증"으로 어느 자리를 위한 인증인지 보여준다.
  loadSeat()
  const seatLabel = $derived(seat.id ? seat.id.toUpperCase() : '')

  // 클라이언트 시계를 KST로 근사(D-01). 서버가 최종 진실 — 여기선 issued_date 저장용.
  function todayKST() {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date())
  }

  /** @type {'checking' | 'form' | 'done'} */
  let phase = $state('checking')

  // 사진
  let file = $state(null)
  let previewUrl = $state(null)
  let fileError = $state('') // 클라이언트 사전 검증 인라인 문구
  /** @type {HTMLInputElement} */
  let fileInputEl = $state(null)

  // 상점 직접 선택
  let shops = $state([])
  let shopsLoading = $state(false)
  let shopsError = $state(false)
  let selectedShopId = $state('')
  let shopTouched = $state(false) // 사용자가 드롭다운을 직접 건드렸는가(프리필 우선순위, VF-605)

  // 제출/결과
  let submitting = $state(false)
  let resultError = $state('') // 서버 판정 사유(rejected/retry) 또는 장애·네트워크 인라인 문구
  let revokedBanner = $state(false) // 감사 무효화 후 재진입(VF-505)
  let ocrOutage = $state(false) // OCR 장애 → 상점 선택 강조(VF-701)

  // done 상태
  let doneShopName = $state('')

  // 상점 선택 섹션 스크롤 타깃(장애 시 포커스 유도)
  /** @type {HTMLElement} */
  let manualSectionEl = $state(null)

  const canSubmit = $derived(!!file || !!selectedShopId)

  // ── 진입/상태 복원 (영역 1) ──
  // onMount인 이유: 진입 시 1회 서버 인증 상태 조회다. $effect로 두면 init()이 phase(reactive)를
  // 읽고(가드) 또 phase를 써서(done/form) self-invalidate → 마운트 로직이 재실행될 여지가 생긴다.
  // 마운트 1회 실행이 의도이므로 onMount가 정확하다.
  onMount(init)

  async function init() {
    try {
      // 단일 진실은 서버(D-14). 당일 인증 상태를 받아 localStorage를 동기화.
      const server = await getVerifyStatus()

      if (server && server.status === 'approved' && server.verification_id) {
        // VF-102/104/303/603: 방식(photo/manual)·감사 플래그와 무관하게 동일한 "오늘 인증 완료".
        saveVerify({
          token: server.token,
          verification_id: server.verification_id,
          status: 'approved',
          issued_date: server.issued_date ?? todayKST(),
          shop_name: server.shop_name,
        })
        doneShopName = server.shop_name ?? ''
        phase = 'done'
        return
      }

      if (server && server.status === 'rejected' && server.reason_code === 'REVOKED_BY_AUDIT') {
        // VF-505: 감사 무효화 후 재진입 — stale 토큰 삭제 + 배너, 폼으로.
        clearVerify()
        revokedBanner = true
      } else {
        // VF-105: 서버가 당일 인증 없음(none) → 로컬 stale 제거.
        clearVerify()
      }
    } catch (e) {
      // offline(VF-704 계열): 로컬 캐시로 낙관 복원. 없으면 폼.
      const local = loadVerify()
      if (local && local.status === 'approved' && local.token && local.issued_date === todayKST()) {
        doneShopName = local.shop_name ?? ''
        phase = 'done'
        return
      }
    }

    phase = 'form'
    loadShops()
  }

  async function loadShops() {
    shopsLoading = true
    shopsError = false
    try {
      shops = await getShops()
    } catch {
      shopsError = true
    } finally {
      shopsLoading = false
    }
  }

  // ── 파일 선택·미리보기 (영역 2) ──
  function openFilePicker() {
    fileInputEl?.click()
  }

  function onFileChange(e) {
    const selected = e.target.files?.[0]
    // 같은 파일 재선택(VF-207) 허용: value 초기화.
    e.target.value = ''
    if (!selected) return

    const res = validateImageFile(selected)
    if (!res.ok) {
      fileError = res.message
      return
    }
    setFile(selected)
  }

  function setFile(f) {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    file = f
    previewUrl = URL.createObjectURL(f)
    fileError = ''
    resultError = '' // 새 파일 → 이전 서버 사유 초기화
  }

  function removeFile() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    file = null
    previewUrl = null
    fileError = ''
    if (fileInputEl) fileInputEl.value = ''
  }

  // 미리보기 디코딩 실패(손상 파일, VF-205): 이미지 로드 에러 시 되돌린다.
  function onPreviewError() {
    removeFile()
    fileError = '사진을 읽을 수 없어요. 다른 사진으로 다시 시도해주세요.'
  }

  function onShopChange(e) {
    shopTouched = true
    selectedShopId = e.target.value
  }

  // ── 제출 (영역 3~7) ──
  async function submit() {
    if (submitting) return
    if (!file && !selectedShopId) {
      // 버튼 비활성이라 통상 도달 불가지만 방어(VF-604).
      resultError = '영수증 사진을 올리거나 상점을 선택해주세요'
      return
    }

    submitting = true
    resultError = ''
    revokedBanner = false

    try {
      const res = await verifyReceipt({
        image: file ?? undefined,
        shopId: selectedShopId || undefined,
      })

      if (res.status === 'approved') {
        // VF-301/501/601: 대기 화면 없이 즉시 좌석으로. 배너는 04가 표시.
        saveVerify({
          token: res.token,
          verification_id: res.verification_id,
          status: 'approved',
          issued_date: todayKST(),
          shop_name: res.shop_name,
        })
        push('/reserve')
        return
      }

      // rejected | retry (VF-401~406): 사유 인라인, 사진 보존, 재시도 가능.
      resultError = res.message || reasonMessage(res.reason_code)
      // VF-605: 사용자가 드롭다운을 안 건드렸으면 OCR이 특정한 상점으로 프리필.
      if (res.matched_shop_id && !shopTouched) {
        selectedShopId = String(res.matched_shop_id)
      }
    } catch (e) {
      await handleSubmitError(e)
    } finally {
      submitting = false
    }
  }

  async function handleSubmitError(e) {
    if (e instanceof ApiError) {
      if (e.code === 'OCR_UNAVAILABLE') {
        // VF-701/702 (D-25): 상점 직접 선택으로 유도(manual → 즉시 승인).
        ocrOutage = true
        resultError = e.message || '사진 인증이 지금 어려워요. 아래에서 상점을 직접 선택해주세요.'
        if (shops.length === 0 && !shopsLoading) loadShops()
        queueMicrotask(() => manualSectionEl?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
        return
      }
      if (e.code === 'ALREADY_VERIFIED_TODAY') {
        // VF-801/901: 이미 당일 인증 존재 → 서버 재조회로 done 동기화.
        await syncToDone()
        return
      }
      // 그 외 4xx/5xx: 서버 message 우선.
      resultError = e.message || '인증에 실패했어요. 다시 시도해주세요.'
      return
    }
    // 네트워크 단절(VF-704): 사진 보존, 재시도 유도.
    resultError = '연결이 불안정해요. 다시 시도해주세요.'
  }

  async function syncToDone() {
    try {
      const server = await getVerifyStatus()
      if (server && server.status === 'approved' && server.verification_id) {
        saveVerify({
          token: server.token,
          verification_id: server.verification_id,
          status: 'approved',
          issued_date: server.issued_date ?? todayKST(),
          shop_name: server.shop_name,
        })
        doneShopName = server.shop_name ?? ''
        phase = 'done'
        return
      }
    } catch {
      // 무시하고 안내만.
    }
    showToast('오늘은 이미 인증을 완료했어요.', 'info')
  }

  // ── 🛠 테스트 전용(배포 전 제거) — OCR 결과 3분기를 시뮬레이트 ──
  // 실제 OCR이 붙으면 confirm/manual UI는 그대로 쓰고, 이 진입 버튼만 교체된다.
  let testMode = $state('menu') // 'menu' | 'confirm' | 'manual'
  let recognized = $state(null) // OCR이 읽은(시뮬레이트) 정보 { shopId, shopName }

  // ② 옳은 영수증: OCR이 잘 읽음 → "이거 맞아요?" 확인 단계
  // recognized = OCR 추출 결과(시뮬레이트). 실제로는 사업자번호로 상점 매칭 + 일시·금액·승인번호 추출.
  async function testRecognized() {
    resultError = ''
    if (shops.length === 0) await loadShops()
    const s = shops[0]
    recognized = {
      shopId: s ? String(s.id) : '',
      shopName: s ? s.name : '카페 A',
      dateTime: '오늘 14:32',
      amount: '8,000원',
      approvalTail: '****1234',
    }
    testMode = 'confirm'
  }

  // ① 이미 쓰인 영수증: 확인 단계 없이 즉시 거부(재시도 가능)
  function testDuplicate() {
    testMode = 'menu'
    resultError = reasonMessage('DUPLICATE_RECEIPT')
  }

  // ④ 금액 미달 영수증: 최소 결제금액 정책 위반 → 거부
  function testUnderMin() {
    testMode = 'menu'
    resultError = reasonMessage('UNDER_MIN_AMOUNT')
  }

  // ③ 인식 잘 안 됨: 상점 직접 선택 흐름
  async function testUnreadable() {
    resultError = ''
    if (shops.length === 0) await loadShops()
    testMode = 'manual'
  }

  // 확인/직접선택 확정 → 실제 manual 인증(백엔드 즉시 승인) → 진짜 토큰 → 예약으로.
  async function confirmVerify(shopId) {
    if (submitting) return
    submitting = true
    resultError = ''
    try {
      const res = await verifyReceipt({ shopId: shopId ? String(shopId) : undefined })
      if (res.status === 'approved') {
        saveVerify({
          token: res.token,
          verification_id: res.verification_id,
          status: 'approved',
          issued_date: todayKST(),
          shop_name: res.shop_name,
        })
        push('/reserve')
        return
      }
      resultError = res.message || reasonMessage(res.reason_code)
      testMode = 'menu'
    } catch (e) {
      await handleSubmitError(e)
    } finally {
      submitting = false
    }
  }

  // 컴포넌트 파기 시 objectURL 정리. onMount의 cleanup으로 두는 이유: 이 정리는 오직 실제
  // 언마운트에만 돌아야 한다. $effect의 cleanup은 재실행마다 돌 수 있어 살아있는 미리보기 URL을
  // 조기 revoke할 위험이 있다. onMount cleanup은 언마운트 1회만 보장된다.
  onMount(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  })
</script>

<div class="flex min-h-[calc(100vh-56px)] flex-col px-5 pb-8 pt-5">
  {#if phase === 'checking'}
    <div class="flex flex-1 items-center justify-center text-gray-400">
      <Spinner size="lg" />
    </div>

  {:else if phase === 'done'}
    <!-- VF-102/801/J2.3: 오늘 이미 인증됨 — 폼 대신 상태 + 좌석 이동 -->
    <div class="flex flex-1 flex-col items-center justify-center gap-4 text-center">
      <div class="flex h-16 w-16 items-center justify-center rounded-full bg-island-yellow">
        <svg class="h-8 w-8 text-flow-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
      </div>
      <h2 class="text-xl font-bold text-flow-black">오늘 인증 완료</h2>
      <p class="text-sm text-gray-500">
        {#if doneShopName}
          <span class="font-semibold text-flow-black">{doneShopName}</span> 영수증으로 인증했어요.
        {/if}
        오늘은 이미 인증을 완료했어요.
      </p>
    </div>
    <div class="mt-auto pt-6">
      <Button onclick={() => push('/reserve')}>이 자리 예약하러 가기</Button>
    </div>

  {:else}
    <!-- 업로드 폼 -->
    {#if revokedBanner}
      <div class="mb-4 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700">
        운영진 확인 결과 인증이 취소되었어요. 다시 인증해주세요.
      </div>
    {/if}

    {#if seatLabel}
      <p class="mb-2 text-sm font-semibold text-flow-black">{seatLabel} 자리 인증</p>
    {/if}
    <p class="mb-5 text-sm leading-relaxed text-gray-500">
      행궁동 참여 상점의 영수증을 촬영하거나 올려주세요.<br />
      당일 결제 영수증만 인정돼요.
    </p>

    <!-- ⛔ 테스트: 실제 인증 폼(사진 픽커·상점 직접 선택·인증하기)을 임시 비활성화. 복구 시 {#if false} → {#if true}. -->
    {#if false}
    <input
      bind:this={fileInputEl}
      type="file"
      accept="image/jpeg,image/png"
      capture="environment"
      class="hidden"
      onchange={onFileChange}
    />

    {#if previewUrl}
      <!-- preview: 썸네일 + X 제거 -->
      <div class="relative w-full overflow-hidden rounded-2xl border border-gray-200 bg-gray-50">
        <img
          src={previewUrl}
          alt="선택한 영수증 미리보기"
          class="max-h-72 w-full object-contain"
          onerror={onPreviewError}
        />
        <button
          type="button"
          class="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-flow-black/70 text-pause-white"
          onclick={removeFile}
          aria-label="사진 제거"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M4 4L12 12M12 4L4 12" stroke="white" stroke-width="1.6" stroke-linecap="round" />
          </svg>
        </button>
      </div>
      <button
        type="button"
        class="mt-2 w-full py-2 text-sm text-gray-400 transition-colors hover:text-gray-600"
        onclick={openFilePicker}
      >
        다른 사진으로 바꾸기
      </button>
    {:else}
      <!-- empty: 사진 올리는 박스 -->
      <button
        type="button"
        class="flex aspect-[4/3] w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-island-yellow bg-island-yellow-light transition-colors active:brightness-95"
        onclick={openFilePicker}
      >
        <svg class="h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.2">
          <path stroke-linecap="round" stroke-linejoin="round"
            d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
        </svg>
        <span class="text-sm font-semibold text-flow-black">영수증 촬영 또는 업로드</span>
        <span class="text-xs text-gray-400">JPG / PNG · 최대 10MB</span>
      </button>
    {/if}

    {#if fileError}
      <p class="mt-2.5 text-sm leading-relaxed text-red-500">{fileError}</p>
    {/if}

    {#if resultError}
      <div class="mt-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-relaxed text-red-600">
        {resultError}
      </div>
    {/if}

    <!-- 또는 상점 직접 선택 -->
    <div class="my-6 flex items-center gap-3 text-xs text-gray-400">
      <span class="h-px flex-1 bg-gray-200"></span>
      또는
      <span class="h-px flex-1 bg-gray-200"></span>
    </div>

    <div
      bind:this={manualSectionEl}
      class="rounded-2xl border p-4 transition-colors {ocrOutage ? 'border-island-yellow bg-island-yellow-light' : 'border-transparent'}"
    >
      <label for="shop-select" class="mb-2 block text-sm text-gray-500">상점 직접 선택</label>
      {#if shopsLoading}
        <div class="flex items-center gap-2 py-2 text-sm text-gray-400">
          <Spinner size="sm" /> 상점 목록을 불러오고 있어요…
        </div>
      {:else if shopsError}
        <p class="py-2 text-sm text-gray-500">
          상점 목록을 불러오지 못했어요.
          <button type="button" class="underline" onclick={loadShops}>다시 시도</button>
        </p>
      {:else}
        <select
          id="shop-select"
          class="w-full rounded-xl border border-gray-300 bg-pause-white px-4 py-3 text-sm text-flow-black"
          value={selectedShopId}
          onchange={onShopChange}
        >
          <option value="" disabled>상점을 선택하세요</option>
          {#each shops as shop}
            <option value={String(shop.id)}>{shop.name}</option>
          {/each}
        </select>
      {/if}
    </div>

    <div class="mt-6">
      <Button loading={submitting} disabled={!canSubmit} onclick={submit}>
        <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
        인증하기
      </Button>
      <p class="mt-3 text-center text-xs text-gray-400">인증은 하루 1회만 가능합니다</p>
    </div>
    {/if}
    <!-- /⛔ 비활성화 끝 -->

    <!-- 🛠 테스트 전용(배포 전 제거): OCR 결과 3분기 시뮬레이트 -->
    <div class="rounded-2xl border-2 border-dashed border-flow-black p-4">
      {#if testMode === 'menu'}
        <p class="mb-3 text-xs font-bold text-gray-500">테스트 · 영수증 인식 결과</p>
        {#if resultError}
          <div class="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-relaxed text-red-600">
            {resultError}
          </div>
        {/if}
        <div class="space-y-2">
          <Button onclick={testRecognized}>옳은 영수증 (잘 읽힘)</Button>
          <Button variant="ghost" onclick={testDuplicate}>이미 쓰인 영수증</Button>
          <Button variant="ghost" onclick={testUnderMin}>금액이 부족한 영수증</Button>
          <Button variant="ghost" onclick={testUnreadable}>인식이 잘 안 됨</Button>
        </div>

      {:else if testMode === 'confirm'}
        <!-- ② 옳은 영수증 → "이거 맞아요?" 확인 -->
        <p class="text-sm font-bold text-flow-black">영수증을 읽었어요</p>
        <p class="mb-4 mt-0.5 text-xs text-gray-500">아래 정보가 맞는지 확인해주세요.</p>
        <div class="mb-4 divide-y divide-gray-100 rounded-xl bg-gray-50 px-4 py-1 text-sm">
          <div class="flex items-center justify-between py-2.5">
            <span class="text-gray-500">가게</span><span class="font-bold text-flow-black">{recognized?.shopName}</span>
          </div>
          <div class="flex items-center justify-between py-2.5">
            <span class="text-gray-500">결제 일시</span><span class="font-bold text-flow-black">{recognized?.dateTime}</span>
          </div>
          <div class="flex items-center justify-between py-2.5">
            <span class="text-gray-500">결제 금액</span><span class="font-bold text-flow-black">{recognized?.amount}</span>
          </div>
          <div class="flex items-center justify-between py-2.5">
            <span class="text-gray-500">승인번호</span><span class="font-mono font-bold text-flow-black">{recognized?.approvalTail}</span>
          </div>
        </div>
        <div class="space-y-2">
          <Button loading={submitting} onclick={() => confirmVerify(recognized?.shopId)}>네, 맞아요 · 인증하기</Button>
          <Button variant="ghost" onclick={() => (testMode = 'manual')}>아니요, 직접 선택할게요</Button>
        </div>

      {:else}
        <!-- ③ 인식 안 됨 / "아니요" → 상점 직접 선택 -->
        <p class="text-sm font-bold text-flow-black">상점을 직접 선택해주세요</p>
        <p class="mb-3 mt-0.5 text-xs text-gray-500">영수증을 잘 못 읽었어요. 결제한 참여 상점을 골라주세요.</p>
        {#if shopsLoading}
          <div class="flex items-center gap-2 py-2 text-sm text-gray-400"><Spinner size="sm" /> 상점 목록을 불러오고 있어요…</div>
        {:else if shopsError}
          <p class="py-2 text-sm text-gray-500">상점 목록을 불러오지 못했어요. <button type="button" class="underline" onclick={loadShops}>다시 시도</button></p>
        {:else}
          <select
            class="w-full rounded-xl border border-gray-300 bg-pause-white px-4 py-3 text-sm text-flow-black"
            value={selectedShopId}
            onchange={onShopChange}
          >
            <option value="" disabled>상점을 선택하세요</option>
            {#each shops as shop}
              <option value={String(shop.id)}>{shop.name}</option>
            {/each}
          </select>
        {/if}
        <div class="mt-3 space-y-2">
          <Button loading={submitting} disabled={!selectedShopId} onclick={() => confirmVerify(selectedShopId)}>이 상점으로 인증</Button>
          <Button variant="ghost" onclick={() => (testMode = 'menu')}>뒤로</Button>
        </div>
      {/if}
      <p class="mt-3 text-center text-[10px] text-gray-400">테스트 전용 · 배포 전 위 비활성화 블록 복구</p>
    </div>
  {/if}
</div>
