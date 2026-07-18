# Design.md — 프론트엔드 설계 단일 진실

> 이 문서는 "멈춰, 섬!" **프론트엔드 구현의 단일 진실**이다. 백엔드에서 시나리오 명세(`context/scenarios/`)가 했던 역할을, 프론트에서는 이 문서가 한다.
> 핵심 원칙 하나: **참조하되 복제하지 않는다.** 값의 집은 하나다. 이 문서는 배선도지 사전이 아니다.

---

## 0. 목적과 경계

### 이 문서가 하는 것
- **엔지니어링 구조** — 컴포넌트 분류, 앱 셸, 라우팅·가드
- **상태·데이터 계약** — API 클라이언트, localStorage 규약, 폴링
- **보편 인터랙션 상태** — loading / empty / error / offline를 한 번 정의해 재사용
- **토큰 바인딩** — 이미 정해진 디자인 토큰을 Tailwind에 묶는 규칙
- **한국어 카피 컨벤션** — 톤과 문구 규칙

### 이 문서가 **하지 않는** 것 (경계)
- **미감·비주얼 결정은 하지 않는다.** 색·타이포·간격·시각 스타일의 결정권은 **디자인팀(김다인·김민진·황설휘)과 Figma**에 있다. 이 문서는 그 결정을 *코드에 묶을* 뿐, 새 미감을 발명하지 않는다. (CLAUDE.md: "개발 쪽에서 art-direct 하지 않는다")
- **행동을 재정의하지 않는다.** 각 화면이 무엇을 하는지(Given/When/Then)는 `context/scenarios/`와 `context/wireframe-spec/`이 정한다. 이 문서는 *어떻게 보이고 반응하는지*만 다루고, *무엇이 유효한지*는 그쪽을 가리킨다.
- **API 계약을 재정의하지 않는다.** 엔드포인트·응답 형태·에러 코드는 백엔드(`context/db-schema.md` + `context/scenarios/00-overview.md`)가 정한다.

---

## 1. 진실의 출처와 우선순위

| 관심사 | 주인(단일 진실) | 이 문서의 역할 |
|---|---|---|
| 색·타이포·간격·시각 스타일 | **Figma** (`FILE_KEY: YNIN2Enlmk76E5iLkj60dR`), 디자인팀 | 토큰을 Tailwind에 바인딩 (§2) |
| 화면 행동·플로우 | `context/scenarios/` (GWT) + `context/wireframe-spec/` | 참조만, 인터랙션 표현으로 번역 (§8) |
| API·데이터 계약·에러코드 | `context/db-schema.md` + `context/scenarios/00-overview.md` 결정표 | 클라이언트로 소비 (§5) |
| localStorage 규약 | `00-overview.md` §localStorage 표준 규약 | 코드에 강제 (§5) |
| 컴포넌트 구조·앱 셸·라우팅·상태 | **이 문서** | 정의 |

**충돌 시 타이브레이크:**
- *룩*이 어긋나면 → **Figma가 이긴다.**
- *행동*이 어긋나면 → **시나리오 스펙이 이긴다.**
- *스냅샷(`context/figma/`)과 Figma 원본이 다르면* → **Figma 원본이 이긴다** (스냅샷은 썩는다 — §13).

---

## 2. 디자인 토큰과 Tailwind 바인딩

### 스택 사실
**Tailwind v4 (CSS-first).** `tailwind.config.js`는 없다. 토큰은 `frontend/src/app.css`의 `@theme` 블록에 CSS 변수로 산다. (리서치 문헌의 v3 `theme.extend` 방식은 우리에게 해당 없음.)

### 현재 바인딩된 토큰 (`app.css @theme`)
| 토큰 | 값 | 용도 |
|---|---|---|
| `--color-island-yellow` | `#FFEE00` | Primary. 브랜드/CTA |
| `--color-island-yellow-light` | `#FFFDE6` | 옅은 배경 |
| `--color-pause-white` | `#FFFFFF` | 바탕 |
| `--color-flow-black` | `#000000` | 텍스트/선 |
| `--color-header-bg` | `#1a1700` | 헤더 배경 |
| `--color-gray-50 … 900` | (표준 그레이) | 보조 UI |
| `--font-sans` | Pretendard Variable … | 본문 폰트 |

Tailwind 유틸리티로 자동 노출된다: `bg-island-yellow`, `text-flow-black`, `bg-header-bg` 등.

### 단방향 동기화 규칙 (안티-drift)
> **토큰 값은 코드에서 손으로 고치지 않는다.** 방향은 항상 **Figma(변수) → app.css `@theme`** 한 방향이다. "사람이 hex를 손으로 복사하는 순간 drift가 시작된다."
- Figma 토큰이 바뀌면 → `app.css @theme`를 그 값으로 갱신하는 것이 유일한 반영 경로. 컴포넌트에 하드코딩된 hex(`#FFEE00` 직접 타이핑) 금지 — 반드시 토큰 유틸리티를 쓴다.
- 새 색이 필요하면 임의로 만들지 말고 디자인팀에 요청 → Figma에 추가 → `@theme`에 반영.

---

## 3. 컴포넌트 분류와 인벤토리

### 2단 모델 (Atomic Design 안 씀 — 이유)
Atomic Design(atoms→molecules→organisms→templates→pages)은 **6화면 팝업에는 오버킬**이다("이게 molecule이냐 organism이냐" bikeshedding + 유지비). 어휘만 빌리고 **2단으로 접는다**:

```
src/components/   ← 공유 프리미티브 (재사용 UI 조각)
src/routes/       ← 화면 (한 라우트 = 한 파일)
src/lib/          ← 비-UI (api 클라이언트, 스토어, 유틸)
```
이미 레포 폴더 구조가 이렇다. 새 층을 만들지 않는다.

### 공유 컴포넌트 인벤토리
각 항목은 GOV.UK식 고정 틀로 문서화한다: **역할 · props · 쓰는 곳**. 구현 시 이 표가 계약이다.

| 컴포넌트 | 역할 | 주요 props | 쓰는 화면 |
|---|---|---|---|
| `Header` (존재) | 상단 고정 바 + 햄버거 메뉴 | `title?` | 전 화면 |
| `NavBar` (존재) | 햄버거 드로어(메인/메뉴/방명록) | `open`, `onClose` | 전 화면 |
| `Button` | CTA/보조 버튼 | `variant`(primary/ghost), `disabled`, `loading`, `onclick` | 전 화면 |
| `SeatCell` | 좌석 카드(A1~B3) | `seat`, `state`(available/taken/closed/selected), `onSelect` | 예약(§8) |
| `ShopCard` / `ShopBadge` | 참여 상점 카드·배지 | `shop` | 메뉴·방명록 |
| `GuestEntry` | 방명록 항목 카드 | `entry` (익명·상대시간·별점·태그) | 방명록 |
| `StarRating` | 별점 입력/표시 | `value`, `readonly`, `onChange` | 방명록 |
| `EmptyState` | 보편 빈 상태 (§6) | `message`, `action?` | 전역 |
| `ErrorState` | 보편 에러 + 재시도 (§6) | `message`, `onRetry` | 전역 |
| `Spinner` / `Skeleton` | 로딩 표현 (§6) | `size` | 전역 |
| `Toast` | 일시 알림 | `message`, `kind`(info/error) | 전역 |
| `BottomSheet` | 하단 시트(맛집 선택 등) | `open`, `onClose`, children | 방명록·인증 |
| `StatusBanner` | 상단 상태 배너("인증 완료"/"내 예약 보기") | `text`, `onClick?` | 메인·인증·예약 |

> **Svelte 5 runes** 사용. 컴포넌트 상태는 `$state`, 파생은 `$derived`, 부수효과는 `$effect`. props는 `$props()`. 이벤트는 콜백 prop(`onSelect`)으로 내린다(레거시 `createEventDispatcher` 지양).

---

## 4. 앱 셸 / 레이아웃

모든 라우트가 들어가는 고정 프레임. 화면마다 반복 정의하지 않는다. (`App.svelte`)

```
<div class="min-h-screen bg-white max-w-[430px] mx-auto shadow-lg relative">
  <Header />          ← 고정 상단
  <Router {routes} /> ← 화면 슬롯
  {토스트·모달·바텀시트 마운트 지점}
</div>
```
- **모바일 컬럼**: `max-w-[430px] mx-auto` — 폰 우선, 데스크톱은 가운데 정렬된 폰 폭(엣지 케이스, §10).
- **safe-area**: 헤더/하단 CTA는 `env(safe-area-inset-*)` 고려(iOS 노치·홈 인디케이터).
- **토스트/모달/바텀시트**는 셸 레벨의 단일 마운트 지점에 띄운다(각 화면이 제 자리에 심지 않음).
- **`/admin`은 이 셸 밖**의 별도 레이아웃(햄버거·모바일 컬럼 불필요) — 라우트 추가 필요(§7).

---

## 5. 상태와 데이터 계약

### API 클라이언트 (`src/lib/api.js`)
> 현재 `api.js`는 **목(mock) 데이터**다. 백엔드가 이미 구현·테스트 완료(127 pytest green)이므로, **실 API 호출로 교체**한다.

- 단일 래퍼 `apiFetch(path, opts)`:
  - base URL 환경변수(`import.meta.env.VITE_API_BASE`), 기본 `http://localhost:8000`.
  - **모든 요청에 `X-Device-Id` 헤더 자동 부착**(§device-id).
  - 에러 정규화: 백엔드 에러 봉투 `{ error: { code, message } }`(결정표 D-24)를 파싱해 `throw new ApiError(code, message, status)`. 화면은 `code`로 분기, `message`로 표시.
- 화면별 요청 상태는 표준 형태 `{ loading, data, error }`로 다룬다(§6가 이 셋을 렌더).

### device-id / localStorage 표준 규약 (D-07 강제)
> ⚠️ **현재 `api.js`의 키(`stop-island:verification`, `stop-island:reservation`)는 백엔드 계약과 어긋난다. 아래 표준으로 통일한다.** 단일 진실은 항상 서버 — localStorage는 캐시일 뿐, 불일치 시 서버 값으로 덮고 stale 키는 지운다.

| 키 | 값 | 쓰는 곳 → 읽는 곳 |
|---|---|---|
| `stop-island:device-id` | UUID (`crypto.randomUUID()`, 최초 부트 시 생성) | 앱 부트 → 모든 API `X-Device-Id` 헤더 |
| `stop-island:verify` | JSON `{ token?, verification_id, status, issued_date, shop_name? }` | 인증(03) → 메뉴·예약 가드·배너 |
| `stop-island:reservation-id` | reservation_id 문자열 | 예약 확정(04) → 메인 배너·예약 복구 |
| `stop-island:seat` | seat id 문자열 (D-26) | QR 부트(`?seat=`) → 메인 맥락·예약 확정. 최신 스캔이 덮어씀 |

**좌석별 QR (D-26)**: 각 좌석에 고유 QR(`/#/?seat=a3`). 앱 부트 시 해시 쿼리에서 `seat`를 읽어 `stop-island:seat`에 저장하고 예약 흐름 내내 이 값을 쓴다. **좌석 그리드 선택은 없다** — 좌석은 찍은 QR로 이미 정해졌다.

- 서버 재확인 경로: `GET /api/verify/status`, `GET /api/reservations/:id`. 진입/복구 시 이걸로 localStorage를 검증·갱신.

### 폴링 (D-12)
- **30초 폴링** 대상: 메인 현황(`GET /api/status`), 예약 좌석판(`GET /api/seats`). WebSocket/SSE 안 씀.
- 패턴: 화면 마운트 시 시작, `$effect` cleanup에서 해제. **`document.hidden`이면 폴링 일시정지**(백그라운드 탭 낭비 방지), `visibilitychange`/`online` 복귀 시 즉시 1회 재요청.
- 좌석 충돌의 최종 방어는 폴링이 아니라 **예약 API 트랜잭션**(선점 시 409) — 폴링은 화면 신선도용일 뿐.

---

## 6. 보편 인터랙션 상태 (loading / empty / error / offline)

> 화면마다 재발명하지 않는다. 한 번 정의하고 어디서나 재사용한다 — 모든 레퍼런스 디자인시스템이 갖춘, 가장 레버리지 큰 절.

| 상태 | 언제 | 표현 | 컴포넌트 |
|---|---|---|---|
| **loading** | 요청 진행 중 | 첫 로드=Skeleton, 액션 중=버튼 인라인 Spinner. 폴링 갱신은 조용히(깜빡임 없음) | `Skeleton` / `Spinner` |
| **empty** | 정상인데 데이터 0개 | "아직 …이 없어요" + (선택)액션. 에러 아님 | `EmptyState` |
| **error** | 요청 실패(4xx/5xx) | 화면 안 죽이고 그 영역에 문구 + `[다시 시도]` | `ErrorState` |
| **offline** | 네트워크 단절 | 골목 신호 끊김 대비. 소개·버튼은 유지, 숫자만 "—"로. 복귀 시 자동 채움 | 화면 로컬 + `online` 이벤트 |

**offline은 가정이 아니라 현실이다** — 7일 **오프라인 현장** 팝업, 골목 와이파이가 약하다(MAIN-501/502, VF-704 등). 화면 전체가 죽는 경우는 없어야 한다.

에러 표면 규칙: **인라인**(폼 필드·리스트 영역) 우선, 전역 실패만 **Toast**, 화면 전체 실패는 **ErrorState**. 무한 스피너 금지 — 타임아웃 후 error로 전환.

---

## 7. 내비게이션과 라우팅 가드

### 라우트 표 (`svelte-spa-router`)
| 경로 | 화면 | 가드 |
|---|---|---|
| `/` | Main | 없음 |
| `/menu` | Menu | 없음 |
| `/verify` | Verify | 이미 오늘 approved면 "오늘 인증 완료" 상태로 렌더(D-14) |
| `/reserve` | Reserve (이 자리 확정) | **유효 verify token + `stop-island:seat` 둘 다 있어야 진입**. 토큰 없으면 `/verify`, seat 없으면 메인으로("좌석 QR 안내"). D-14/D-26 |
| `/reservation/:id` | (예약 완료 화면 D-09) | 소유(device-id) 아니면 접근 불가 |
| `/guestbook` | Guestbook | 없음(인증 불필요) |
| `/admin` | Admin | **세션 없으면 로그인 게이트**(D-21). 셸 밖 레이아웃(§4) |

### 가드 구현
- 가드는 **클라이언트 낙관 + 서버 확정** 이중. 예: `/reserve` 진입 시 localStorage `stop-island:verify`로 1차 판단 → 실제 예약 API가 서버에서 최종 검증(토큰 만료면 `TOKEN_EXPIRED`/`TOKEN_NOT_FOUND`).
- **QR 진입 앱**: 첫 진입은 항상 `/`. 딥링크로 `/reserve`·`/reservation/:id`에 직접 들어와도 가드가 순서를 지킨다(건너뛰기 불가 — RSV-101/103).
- 뒤로가기: 헤더 back + 브라우저 back 모두 자연스러운 흐름 유지. 탭바·dot 인디케이터는 구현 안 함(D-15).

---

## 8. 폼과 검증 UX

*무엇이 유효한지*는 시나리오가 정한다(참조). 이 절은 *어떻게 보이고 반응하는지*만 정의한다.

**공통 규칙**
- 제출 버튼은 최소 요건 미충족 시 **비활성**(빈 방명록 등). 검증 시점: 파괴적이지 않은 건 blur, 최종은 submit.
- 제출 중엔 버튼 `loading`(중복 제출 방지). 실패해도 **입력 내용 보존** — 다시 누르면 됨.
- 에러는 **인라인**(해당 필드·영역 바로 아래).

**화면별**
- **인증(Verify)**: 사진 업로드 박스(카메라/갤러리) + "또는 상점 직접 선택" 드롭다운. 클라이언트 사전 검증: JPG/PNG·10MB 이하(서버 도달 전, VF-202~205). 미리보기 + X로 제거. 판정 결과에 따라 좌석으로 진행 / 사유 인라인 표시 후 재시도(사진 보존). "확인 중" 대기 화면 **없음**(무인 운영 — 애매해도 즉시 통과, D-05).
- **예약(Reserve) = 이 자리 확정 (D-26, 그리드 없음)**: `stop-island:seat`가 가리키는 **찍은 좌석 하나**를 보여주고("A3 · 4인석 · 창가 자리") **[이 자리(A3) 예약하기]** 버튼 하나. 성공 → 예약 완료 화면. 409 `SEAT_TAKEN` → "아쉽지만 방금 다른 분이 먼저 예약했어요" + "다른 빈 자리의 QR을 찍어주세요"(그리드가 없으니 재선택이 아니라 재스캔 유도). 좌석 상태는 `GET /api/seats`에서 해당 seat만 필터해 확인. `SeatCell` 그리드 로직은 폐기.
- **방명록(Guestbook)**: 본문(최대 500자, 글자수 카운터) + 선택 별점 + 선택 맛집 태그(최대 5, 바텀시트). 도배 방지 rate limit 초과 시 "잠시 후 다시 써주세요"(429, D-19). 게시 즉시 목록 최상단.

---

## 9. 모션과 전환

최소로. 값(easing·duration)이 Figma/토큰에 있으면 그걸 따르고, 없으면 절제된 기본.
- 라우트 전환: 가볍게(과한 슬라이드 지양). 스켈레톤 vs 스피너 정책은 §6.
- 바텀시트: 아래에서 위로 슬라이드 + 백드롭 페이드.
- 토스트: 2~3초 자동 소멸.
- `prefers-reduced-motion` 존중 — 모션 축소 설정이면 페이드/이동 제거.

---

## 10. 반응형 규칙

- **모바일 퍼스트.** 기준은 폰. **데스크톱은 엣지 케이스** — 가운데 정렬된 430px 컬럼으로 충분(§4). 별도 데스크톱 레이아웃 안 만든다.
- safe-area inset 반영(노치/홈 인디케이터).
- **탭 타깃 최소 44×44px**(좌석 셀·별점·버튼).
- 업로드는 모바일 카메라 직접 촬영 경로 우선.

---

## 11. 접근성 베이스라인

- **라우트 전환 시 포커스** 를 새 화면 상단(또는 제목)으로 이동.
- 모든 폼 입력에 `label`(별점·좌석엔 `aria-label`).
- **색 대비 리스크(플래그, 수정 아님)**: Island Yellow(`#FFEE00`) 위 흰 텍스트 / 흰 위 노란 텍스트는 WCAG 본문 대비 기준에 미달할 수 있다. 이는 **비주얼 결정이므로 디자인팀에 플래그**한다(개발이 임의로 색을 바꾸지 않음, §0). 텍스트는 검정 기반 권장.
- `<html lang="ko">`.
- 키보드 포커스 가시 상태 유지.

---

## 12. 한국어 카피 컨벤션

> 마이크로카피의 최종 소유는 기획/디자인팀. 이 표는 시나리오에 이미 쓰인 문구에서 뽑은 **일관성 규칙**이며, 새 카피가 필요하면 스펙 문구를 우선한다.

- **톤: 존댓말·친근체** ("~해요 / ~예요 / ~주세요"). 반말·과한 격식 지양. 인사말·이모지 남용 금지.
- **버튼**: 동작을 그대로 ("테이블 예약하기", "인증하기", "게시하기", "자리 비우기"). 누른 결과와 라벨이 일치.
- **에러 문구**: 무엇이 잘못됐고 어떻게 풀지. 사과·모호함 금지. 예: "오늘 결제한 영수증만 인정돼요", "이미 사용된 영수증이에요", "잠시 후 다시 써주세요".
- **빈 상태**: 다음 행동을 유도. 예: "아직 등록된 방명록이 없어요"(첫 글의 주인공).
- **날짜/시간**: 상대시간("10분 전"), 만료는 절대시각+남은시간("16:42까지 · 남은 1시간 58분"). 시간 기준은 서버 KST(D-01).
- **익명 표기**: 방명록 작성자는 항상 "익명 방문자".

---

## 13. Figma 동기화 유지 (안티-부패)

문서가 썩는 #1 원인은 "다른 데가 소유한 값을 복붙"하는 것. 이 문서와 코드가 Figma와 어긋나지 않게:
- **정본은 Figma.** 페이지: "작업", "웹 와이어프레임"(FILE_KEY `YNIN2Enlmk76E5iLkj60dR`).
- `context/figma/wireframes/*.png`와 `context/wireframe-spec/*`는 **스냅샷 — 썩을 수 있다.** 의심되면 Figma API로 다시 읽는다(레포 규칙).
- **토큰 변경 워크플로**: Figma 변수 변경 → `app.css @theme` 갱신을 *같은 커밋*에서. 코드에 하드코딩된 값이 생기면 이 동기화가 깨진다.
- 이 문서의 §2(토큰)·§8(행동 표현)이 스펙/피그마와 어긋나면 §1 우선순위로 판정.

---

## 부록 A. 구현 순서 제안 (프론트 웨이브)

백엔드처럼 "공유 계층 먼저, 그다음 화면 팬아웃":
1. **공유 계층**(단일 에이전트, 선행): `lib/api.js` 실 API 교체 + `X-Device-Id`/localStorage 표준 규약 + `lib/store`(verify/reservation 상태) + 보편 상태 컴포넌트(§6) + 라우팅 가드(§7). 이게 모든 화면의 계약.
2. **화면 팬아웃**(병렬, 충돌 없음): 메인 / 메뉴 / 인증 / 예약(+완료) / 방명록 / 관리자. 각 화면은 자기 라우트 파일 + 필요한 컴포넌트만.
3. 각 화면은 `context/wireframe-spec/`(룩) + `context/scenarios/`(행동) + 이 문서(구조·상태)를 함께 참조.

## 부록 B. user-journey.yaml 마킹과의 연결
`context/scenarios/user-journey.yaml`의 `status: be`(백엔드 완료)가 이 프론트 웨이브에서 화면 배선까지 끝나면 `done`으로, `fe`(순수 프론트)는 구현 시 `done`으로 승격한다. 마킹은 오케스트레이터가 단독 관리(동시 편집 충돌 방지).
