# 01 메인 — Given/When/Then 시나리오

> **한 줄 요약**: QR 스캔 랜딩(`/`)의 **QR 게이트(D-26)** → **도착 랜딩(찍은 자리 중심)** → **재진입 정책(D-28)** 을 커버한다. device_id 생성/재사용, 셸 레벨 흐름 프로그레스, 현황 조연 한 줄(30초 폴링), 내 예약(=이용 중) 우선 노출, 네트워크 장애·재방문·자정 경계 복구를 포함한다.
>
> **이 파일은 구현 코드를 단일 진실로 삼아 조정되었다** — `frontend/src/App.svelte`(셸·게이트·프로그레스), `components/ScanGate.svelte`(게이트), `components/FlowProgress.svelte`(프로그레스), `routes/Main.svelte`(랜딩 3분기), `lib/store.svelte.js`(seat/reservation reconcile) 기준.

**커버 범위**
- **QR 게이트 (D-26)** — 좌석 QR 없이 루트 진입 → 풀스크린 온보딩만 노출(현황·CTA·방명록 전부 숨김). QR은 `/#/?seat=a3`로 좌석을 운반
- 최초 진입 & device_id 생성/재사용 (D-07) — 게이트 뒤 첫 API 호출 시 부착
- **도착 랜딩 (D-26)** — 좌석 QR 진입 → "QR 스캔 완료" 배지 + "당신의 자리 · A3" 히어로 + CTA **[이 자리 잡기] → 곧바로 `/verify`**(메뉴 건너뜀)
- **셸 레벨 흐름 프로그레스** — 자리→인증→예약→착석 4단계를 라우트에 따라 표시(화면마다 재구현 안 함)
- 현황 조연 한 줄 — `GET /api/status` 로딩/성공/실패 + 30초 폴링 (D-12) + unmount 정리 + 빈자리 0석 (D-13)
- **재진입 정책 (D-28)** — active 예약 보유 → "이용 중 · {좌석} · [내 자리 보기]" 우선 / 예약 종료(만료·취소) 후 → "이전 이용이 끝났어요" 안내
- 햄버거 메뉴 (D-15, 메인/메뉴 선택/방명록) + 방명록 링크
- 오프라인/느린 네트워크, 재방문, 자정 넘긴 재방문 (D-01, D-08)

> 📌 결정: localStorage 키 이름을 확정한다 — device_id는 `stop-island:device-id`(D-07), verify 상태는 `stop-island:verify`(03-verify 공통 전제), 예약 ID는 `stop-island:reservation-id`(D-10), 찍은 좌석은 `stop-island:seat`(D-26 — QR 부트 시 `?seat=`에서 기록). 이하 시나리오는 이 키 이름을 전제로 한다.

> 📌 결정(구현 조정, D-26): **이번 진입의 좌석은 오직 URL 쿼리(`?seat=`)로만 결정한다.** 메인은 stale localStorage 좌석을 이번 진입 맥락으로 재사용하지 않는다(`Main.svelte`의 `entrySeat = parseSeatParam(window.location.hash)`). localStorage `stop-island:seat`는 다운스트림(verify/reserve 확정)이 읽을 값을 보존할 뿐이고, QR 없이 열면 메인은 "QR 유도" 상태로 간다. 이는 "새 QR을 안 찍었는데 옛날 자리로 되돌아가는" 혼선을 막는다.

---

## 기능 영역: QR 게이트 (D-26)

### 그룹 7 — 좌석 QR 없이 진입한 사용자 차단

> 📌 결정(D-26): 유저는 **무조건 테이블의 QR로 진입**한다. QR을 안 탔으면 이 서비스를 이용할 진입점이 없다. 그래서 셸(`App.svelte`)이 `showGate` 조건에서 **풀스크린 온보딩(`ScanGate`)** 만 렌더하고 메인 콘텐츠·헤더·프로그레스·방명록을 전부 숨긴다. 게이트 조건 = `location === '/'` **AND** URL에 `seat` 쿼리 없음 **AND** localStorage `stop-island:reservation-id` 없음. 즉 예약 보유자는 QR·seat 없이 열어도 게이트를 통과시켜 자기 예약을 보게 한다(D-28 재진입).

#### MAIN-701 QR 없이 루트 진입 — 게이트 노출 (정상·경계)
- Given: URL이 `/`(해시 `#/`, `?seat=` 없음)이고 localStorage에 `stop-island:reservation-id`가 없다
- When: 주소창 직접 입력·공유 링크 등으로 진입한다
- Then: 풀스크린 온보딩만 렌더된다 — "테이블의 QR을 찍어 시작해주세요" + "자리마다 붙은 QR 코드를 폰으로 스캔하면…". **헤더·햄버거·흐름 프로그레스·현황·CTA·방명록 링크는 노출되지 않는다**
- And: 이 화면은 어떤 API도 호출하지 않는다(정적 온보딩). 서버·localStorage 변화 없음

#### MAIN-702 좌석 QR로 진입 — 게이트 통과 (정상)
- Given: 게이트가 뜰 조건이었으나 QR로 좌석을 운반해 들어온다
- When: `/#/?seat=a3`로 진입한다(URL에 `seat` 쿼리 존재)
- Then: 게이트를 건너뛰고 셸(헤더·흐름 프로그레스) + 메인 도착 랜딩(그룹 6)을 렌더한다
- And: 서버 상태 변화 없음. localStorage `stop-island:seat`='a3' 저장(부트, 그룹 6)

#### MAIN-703 예약 보유자가 QR 없이 재진입 — 게이트 통과 (경계·복구, D-28)
- Given: URL에 `seat` 쿼리는 없지만 localStorage `stop-island:reservation-id`가 존재한다(직전에 예약함)
- When: QR 없이 `/`를 연다(앱 재오픈·공유 링크)
- Then: 게이트를 통과시켜 메인을 렌더한다 — 서버 재조회(reconcile) 결과 active면 "이용 중" 우선 노출(MAIN-301), stale(만료·취소)면 메인이 조용히 정리하고 QR 유도(MAIN-303/703 연계)
- And: 서버 상태 변화 없음(조회만). stale였다면 localStorage `stop-island:reservation-id` 삭제

#### MAIN-704 게이트에서의 유일한 다음 행동 (오류·복구)
- Given: 게이트가 떠 있다
- When: 사용자가 화면을 조작하려 한다
- Then: 게이트에는 상호작용 요소가 없다 — 실제 다음 행동은 "폰으로 테이블 QR 스캔"뿐이다(테스트용 강제 통과 버튼은 셸의 개발 툴바에만 존재, 배포 시 제거)
- And: 서버·localStorage 변화 없음

- **동시성**: 해당 없음 — 게이트 표시 여부는 단일 탭의 URL·localStorage 스냅샷으로만 결정되며 경합 자원이 없다.

---

## 기능 영역: 셸 레벨 흐름 프로그레스 (D-26)

### 그룹 8 — 자리→인증→예약→착석 진행 표시

> 📌 결정(D-26): 예약 여정을 관통하는 상단 프로그레스(`FlowProgress`)는 **셸(`App.svelte`)에 한 번 마운트**되어 라우트에 따라 단계가 차오른다 — 화면마다 재구현하지 않는다. 단계 매핑: `/`+`?seat=`→**자리(0)** · `/verify`→**인증(1)** · `/reserve`→**예약(2)** · `/reservation/*`→**착석(3)**. 여정 밖(seat 없는 메인·방명록·관리자·게이트)은 `-1`로 숨긴다.

#### MAIN-801 좌석 QR 메인 — 자리 단계 표시 (정상)
- Given: `/#/?seat=a3`로 도착 랜딩이 떠 있다
- When: 셸이 라우트를 평가한다
- Then: 상단 프로그레스가 4단계 중 **자리(0)** 를 현재 단계로 표시한다(이후 단계는 회색). 메인 화면 본문은 흐름 단계를 다시 그리지 않는다(중복 제거)
- And: 서버·localStorage 변화 없음

#### MAIN-802 흐름 밖 화면 — 프로그레스 숨김 (경계)
- Given: seat 없는 메인(재진입 QR 유도·이용 중 배너), 또는 방명록/관리자 화면이다
- When: 셸이 라우트를 평가한다
- Then: `flowStep === -1`이므로 프로그레스 바를 렌더하지 않는다
- And: 서버·localStorage 변화 없음

- **오류·동시성·복구**: 해당 없음 — 프로그레스는 라우트에서 파생된 순수 표시 상태이며 자체 데이터 요청·경합·저장이 없다.

---

## 기능 영역: 최초 진입 & device_id (D-07)

### 그룹 1 — device_id 생성과 식별

> 📌 결정(구현): device_id는 앱 부트가 아니라 **첫 API 요청 시** `X-Device-Id`로 부착된다(`lib/api.js` → `getDeviceId()`). 게이트 화면(MAIN-701)은 API를 호출하지 않으므로, 게이트를 통과해 메인이 `GET /api/status` 등을 부를 때 생성/재사용이 확정된다.

#### MAIN-101 QR 스캔 최초 진입 — device_id 신규 생성 (정상)
- Given: 이 브라우저로 서비스에 접속한 적이 없다 (localStorage에 `stop-island:device-id` 없음)
- When: 좌석 QR로 진입해 메인이 첫 API를 호출한다
- Then: `crypto.randomUUID()`로 device_id를 생성해 localStorage `stop-island:device-id`에 저장한다
- And: 이후 모든 API 요청(`GET /api/status` 포함)에 `X-Device-Id` 헤더가 붙는다. 서버 상태 변화 없음(status는 읽기 전용)

#### MAIN-102 재방문 — device_id 재사용 (정상·복구)
- Given: localStorage에 `stop-island:device-id`가 이미 존재한다
- When: `/`에 재진입한다
- Then: 새 UUID를 생성하지 않고 기존 값을 그대로 `X-Device-Id` 헤더에 사용한다
- And: localStorage 값 변화 없음. 서버 상태 변화 없음

#### MAIN-103 localStorage 사용 불가 환경 (오류)
- Given: 시크릿 모드/브라우저 설정으로 localStorage 쓰기가 예외를 던진다
- When: `/`에 진입한다
- Then: 앱이 크래시하지 않고, 메모리 변수에만 device_id를 보관하여 세션을 계속한다
- And: 화면은 정상 렌더. 서버 상태 변화 없음. localStorage는 미변경(쓰기 실패)

> 📌 결정: localStorage 불가 시 메모리 폴백으로 동작한다. 새로고침하면 device_id가 바뀌어 당일 인증/예약 재확인이 불가능하지만, v1에서는 별도 경고 없이 수용한다(규모상 극소수 케이스).

#### MAIN-104 X-Device-Id 헤더 누락 요청 (오류)
- Given: 클라이언트 결함 또는 외부 도구로 헤더 없이 API를 호출한다
- When: `GET /api/status`가 `X-Device-Id` 없이 도착한다
- Then: 서버는 400 + `{ error: { code: "DEVICE_ID_REQUIRED", message } }`를 반환한다(D-07, D-24)
- And: 화면(정상 클라이언트라면 발생하지 않음) 기준으로는 현황 한 줄이 에러 문구를 표시. localStorage 변화 없음

> 📌 결정: 헤더 누락 에러 코드는 `DEVICE_ID_REQUIRED`로 한다.

#### MAIN-105 두 탭 동시 최초 진입 (동시성)
- Given: device_id가 없는 상태에서 탭 2개가 거의 동시에 `/`를 연다
- When: 두 탭이 각각 UUID를 생성해 localStorage에 쓴다
- Then: 나중에 쓴 값으로 수렴한다. 아직 인증/예약 전이므로 기능 영향 없음(이후 요청은 각 탭이 localStorage를 다시 읽어 동일 값 사용)
- And: 서버 상태 변화 없음

- **경계**: 해당 없음 — device_id는 생성/재사용 두 상태뿐이며 값 자체에 경계 조건이 없다.

---

## 기능 영역: 현황 조연 한 줄 — `GET /api/status` + 30초 폴링 (D-12)

### 그룹 2 — 로딩·폴링·실패

> 📌 결정(구현 조정): 현황은 **주연 카드가 아니라 도착 랜딩 하단의 조연 한 줄**이다 — "지금 빈 자리 N석 · 오늘 N명 방문"(`Main.svelte`). 도착 랜딩의 주연은 좌석·CTA다. 현황은 **available/unavailable 분기에서만 노출**되고, "이용 중" 배너·QR 유도 분기에서는 조회는 하되 표시하지 않는다(맥락상 불필요).

#### MAIN-201 최초 로딩 성공 (정상)
- Given: 좌석 QR로 도착 랜딩에 진입했고 네트워크가 정상이다
- When: 마운트 직후 `GET /api/status`를 1회 즉시 호출한다(`createPoll`은 즉발하지 않으므로 onMount가 별도로 1회 호출)
- Then: 응답 `{ available_seats, today_visitors, is_full }`가 조연 한 줄에 반영된다. 로딩 동안은 "현황 불러오는 중…"
- And: 30초 간격 폴링이 시작된다. 서버·localStorage 변화 없음

#### MAIN-202 30초 폴링으로 값 갱신 (정상)
- Given: 메인 화면이 떠 있고 최초 로딩에 성공했다
- When: 30초 경과 후 폴링 응답의 `available_seats`가 4→3으로 바뀌어 온다
- Then: 화면 새로고침 없이 조연 한 줄이 "빈 자리 3석"으로 갱신된다(찍은 자리 상태도 함께 재조회 — 그룹 6)
- And: 서버·localStorage 변화 없음

#### MAIN-203 빈자리 0석 — 만석 표시 (경계, D-13)
- Given: 응답이 `{ available_seats: 0, is_full: true }`다
- When: 조연 한 줄이 렌더된다
- Then: "빈 자리 0석"을 정상 표기한다
- And: 도착 랜딩의 **[이 자리 잡기] CTA는 비활성화하지 않는다**(찍은 자리가 available이면 인증을 미리 해두는 흐름 허용). 찍은 자리 자체가 taken이면 CTA는 애초에 숨김(그룹 6 unavailable 분기)
- And: 서버·localStorage 변화 없음

#### MAIN-204 최초 로딩 실패 — 캐시 없음 (오류)
- Given: 최초 진입인데 `GET /api/status`가 실패한다(5xx/네트워크 오류)
- When: 응답 실패를 감지한다
- Then: 조연 한 줄이 "현황을 불러오지 못했어요"로 표시된다. 히어로/좌석/CTA는 항상 노출(화면 블로킹 없음)
- And: 폴링은 중단하지 않고 계속 돌며, 다음 성공 시 자동으로 값이 채워진다
- And: 서버·localStorage 변화 없음

> 📌 결정: status 실패 시에도 30초 폴링을 유지한다. 별도 "재시도" 버튼은 두지 않는다(폴링이 곧 재시도).

#### MAIN-205 폴링 중 실패 — 마지막 성공 값 유지 (오류)
- Given: 조연 한 줄에 정상 값이 표시된 상태다
- When: 이후 폴링 요청이 실패한다
- Then: 마지막 성공 값(`status`)을 그대로 유지하고 `statusError`만 세운다. 값이 "—"로 되돌아가지 않는다(`Main.svelte`: 최초 실패로 status가 null일 때만 "—"/"불러오지 못했어요")
- And: 다음 폴링 성공 시 `statusError` 해제. 서버·localStorage 변화 없음

#### MAIN-206 화면 이탈 시 폴링 정리 (복구·정리)
- Given: 메인에서 폴링이 돌고 있다
- When: CTA/햄버거로 다른 라우트로 이동해 메인이 unmount된다
- Then: `createPoll`이 반환한 stop()이 인터벌·리스너를 clear하고 `online` 리스너도 제거되어 이후 요청이 발생하지 않는다
- And: 서버·localStorage 변화 없음

#### MAIN-207 in-flight 응답 중 unmount (동시성)
- Given: `GET /api/status`(또는 `GET /api/seats`) 요청이 응답 대기 중이다
- When: 응답 도착 전에 메인이 unmount된다(`destroyed = true`)
- Then: 뒤늦게 도착한 응답은 `if (destroyed) return`으로 무시된다(파괴된 컴포넌트 상태 갱신·콘솔 에러 없음)
- And: 서버·localStorage 변화 없음

#### MAIN-208 백그라운드 탭 복귀 (복구)
- Given: 메인을 띄운 탭이 백그라운드로 갔다가 5분 뒤 돌아온다
- When: 탭이 다시 visible 상태가 된다
- Then: `createPoll`이 `visibilitychange`(visible 전환)에서 즉시 1회 재요청하고 30초 폴링을 재개한다(hidden 동안 tick은 스킵되어 낭비 없음)
- And: 서버·localStorage 변화 없음

> 📌 결정: 폴링은 `document.hidden`이면 tick을 건너뛰고, visible 복귀·`online` 복귀 시 즉시 1회 재요청한다(`lib/poll.js`).

---

## 기능 영역: 내 예약 배너 & 재진입 정책 (D-10, D-28)

### 그룹 3 — active(이용 중) 우선 노출 · 종료 후 재진입

> 📌 결정: 예약 상태 조회(`reconcileReservation` → `GET /api/reservations/:id`)는 메인 **진입 시 1회** + `online` 복귀 시 재조회. 폴링하지 않는다. active면 "이용 중" 우선 노출, active 아니면(만료·취소·404·403) localStorage `stop-island:reservation-id`를 조용히 삭제하고 직전 흔적이 있었으면 `ended=true`로 "이전 이용이 끝났어요" 안내를 얹는다(D-28).

#### MAIN-301 active 예약 보유 — "이용 중" 우선 노출 (정상, D-28)
- Given: localStorage `stop-island:reservation-id`가 존재하고, 서버 조회 결과 `status: active`다
- When: `/`에 진입해 `reconcileReservation()`이 active를 반환한다
- Then: 다른 어떤 분기보다 우선해 **"이용 중" 히어로**를 렌더한다 — "이용 중" 배지 + "이용 중인 자리 · {좌석 라벨}(대형)" + `{capacity}인석 · {위치}` + Primary CTA **[내 자리 보기] → `/reservation/:id`** + "방명록 구경하기" 링크
- And: 이 상태에서는 도착 랜딩·CTA(잡기)를 그리지 않는다(한 번에 한 자리 — D-28). 서버·localStorage 변화 없음

#### MAIN-302 이용 중 상태에서 다른 자리 QR을 찍음 (경계, D-28)
- Given: active 예약(자리 A3)이 있는데, 다른 자리 QR `/#/?seat=b1`로 재진입한다
- When: 메인이 active 예약을 확인하고, `entrySeat`(b1)가 예약 좌석 라벨(A3)과 다름을 감지한다
- Then: "이용 중" 히어로는 그대로 유지하되, 안내 박스로 "**B1** 자리를 새로 찍으셨네요. 한 번에 **한 자리**만 이용할 수 있어요 — 옮기려면 지금 자리를 비운 뒤 그 자리 QR을 다시 찍어주세요"를 표시한다(새 예약 차단)
- And: 서버 상태 변화 없음. localStorage `stop-island:seat`는 부트에서 'b1'로 갱신되지만 예약 흐름은 진행되지 않는다

#### MAIN-303 예약이 만료·취소됨 — 조용히 정리 + 종료 안내 (경계, D-28)
- Given: localStorage에 reservation_id가 있으나 서버 조회 결과 `status`가 active가 아니다(expired: 2시간 경과 D-11 lazy / cancelled: 자리 비우기·관리자 해제)
- When: 메인 진입 시 `reconcileReservation()`이 null을 반환한다
- Then: "이용 중" 배너 미노출. localStorage `stop-island:reservation-id` 삭제. 직전 흔적이 있었으므로 `ended=true` — 좌석 QR이 있으면 도착 히어로 위 검은 띠 "이전 이용이 끝났어요 · 이 자리를 다시 잡을 수 있어요", 없으면 QR 유도 화면에 "이전 이용이 끝났어요" 배지를 얹는다
- And: 서버 상태 변화 없음(expired lazy 판정은 조회 시점에 이미 반영). 토스트 등 별도 알림은 없음

> 📌 결정(D-27·D-28): 예약 종료는 토스트/푸시 없이 **재진입 시 화면 안내로만** 알린다. 좌석 QR이 유효하고 당일 토큰이 살아 있으면 재인증 없이 재예약 흐름으로 이어진다(RSV-701/702).

#### MAIN-304 예약 조회 404 또는 소유자 불일치 (오류)
- Given: localStorage의 reservation_id가 서버에 없거나(초기화 등), device_id 소유 검증에 실패한다(403)
- When: `GET /api/reservations/:id`가 404/403을 반환한다
- Then: `reconcileReservation`이 stale로 보고 localStorage `stop-island:reservation-id`를 삭제하고 null 반환 → 배너 미노출. 서버 상태 변화 없음

#### MAIN-305 예약 조회 네트워크 실패 (오류·복구)
- Given: localStorage에 reservation_id가 있으나 조회 요청이 네트워크 오류로 실패한다(404/403/TOKEN_EXPIRED 외)
- When: 메인 진입 시 조회가 예외를 던진다
- Then: `reconcile()`이 예외를 잡아 배너 null(조용히 숨김). localStorage 키는 **삭제하지 않는다**(상태 불명 — 다음 진입·online 복귀 시 재시도). `ended`도 세우지 않는다
- And: 서버 상태 변화 없음

#### MAIN-306 다른 탭에서 자리 비우기 후 재진입 (동시성)
- Given: 탭 A가 예약 완료 화면에서 "자리 비우기"를 실행했다(서버 `status: cancelled`). 탭 B는 아직 "이용 중"을 보고 있다
- When: 탭 B가 메인에 재진입(또는 online 복귀로 reconcile)한다
- Then: reconcile이 cancelled(active 아님)를 감지해 배너를 내리고 localStorage `stop-island:reservation-id`를 삭제, `ended=true`로 종료 안내를 얹는다
- And: 서버 상태 변화 없음(이미 cancelled)

- **복구**: MAIN-303~305가 새로고침·재진입·online 복귀 시의 복구 경로를 겸한다(진입 시 1회 조회 + online 재조회가 최신 상태로 수렴).

---

## 기능 영역: 좌석 QR 맥락 & 도착 랜딩 (D-26)

### 그룹 6 — 찍은 자리 중심 도착 경험

> 📌 결정(D-26): 좌석 A3의 QR은 `/#/?seat=a3`로 열린다. 셸 부트가 `?seat=`를 파싱해 localStorage `stop-island:seat`에 저장하고(최신 스캔이 덮어씀), **메인은 이번 진입의 좌석을 URL 쿼리로만 판정**한다(`entrySeat`). 좌석 상태는 `GET /api/seats` 응답을 seat id로 **대소문자 무시 필터**(`findSeat`)해 판정한다 — 그리드는 그리지 않는다(그리드 폐기). 도착 랜딩은 좌석을 주연으로 세운다: "QR 스캔 완료" 배지 → "당신의 자리 · {라벨}"(대형) → "{capacity}인석 · {위치}"(seatInfo 로드 후). 좌석 라벨은 URL 값으로 즉시 표시(대기 없음), 상세는 API 확인. CTA **[이 자리 잡기] → 곧바로 `/verify`**(메뉴 건너뜀).

> 📌 결정(D-26, 구현 조정): **메인 CTA는 `/menu`가 아니라 `/verify`로 직행한다.** 자리는 이미 QR로 정해졌으니 02 메뉴의 "예약/방명록 갈림길"이 불필요하다 — 예약 의사는 [이 자리 잡기]가, 방명록은 별도 "방명록 구경하기" 링크가 담당한다. `/menu`는 이제 햄버거 드로어에서만 도달한다(MAIN-403).

#### MAIN-601 좌석 QR로 진입 — 도착 랜딩 (정상)
- Given: 찍은 자리 A3가 available이다
- When: `/#/?seat=a3`로 진입한다
- Then: 셸 부트가 localStorage `stop-island:seat`='a3'로 저장하고, 메인이 도착 히어로를 렌더한다 — "QR 스캔 완료" 배지 + "당신의 자리 · **A3**"(라벨은 URL 값으로 즉시). `GET /api/seats` 해소 후 "{capacity}인석 · {위치}" 채움. 값 문구("참여 상점 영수증 한 장이면…") + CTA **[이 자리 잡기]**
- And: 상단 흐름 프로그레스는 자리(0) 단계(MAIN-801). 현황 조연 한 줄·방명록 링크 노출. 서버 상태 변화 없음

#### MAIN-602 찍은 자리가 사용 중/운영 중지 (경계)
- Given: 찍은 자리 A3가 taken(또는 `is_open=false`로 closed)이다
- When: 메인이 열리고 `GET /api/seats`로 A3 상태를 확인한다(`seatContext='unavailable'`)
- Then: 도착 히어로(좌석 A3 노출)는 유지하되, 아래에 "이 자리는 지금 사용 중이에요"(closed면 "운영 중지된 자리예요") + "지금 **N석** 비어 있어요 — 앉고 싶은 빈 자리의 QR을 찍어주세요"(현황 미확보 시 "빈 자리의 QR을 찍어주세요") + "방명록 구경하기". **[이 자리 잡기] CTA는 노출하지 않는다**(빈자리는 그 자리 QR로만 진입 — D-26)
- And: localStorage `stop-island:seat`는 저장되어 있음(찍은 사실은 기록). 서버 상태 변화 없음

#### MAIN-603 seat 없이 진입 — QR 유도 (경계, 폐기·변경 — D-26)
- Given: URL에 `?seat=` 파라미터가 없다(공유 링크·주소창 직접 진입). *과거 스펙의 "일반 메인" 개념은 폐기* — 게이트/QR 유도로 대체
- When: 메인이 열린다(단, 예약 보유자만 게이트를 통과해 이 경로에 도달 — MAIN-703. 그 외 seat·예약 모두 없으면 애초에 게이트가 막음 MAIN-701)
- Then: `entrySeat`가 null이므로 도착 랜딩 대신 **미니 QR 유도** 화면을 렌더한다 — "테이블의 QR을 찍어 다시 시작해주세요" + "앉고 싶은 자리의 QR을 스캔하면…" + "방명록 구경하기". 예약이 방금 종료됐다면(`ended`) "이전 이용이 끝났어요" 배지를 얹는다(MAIN-303)
- And: **stale localStorage `stop-island:seat`는 이번 진입 맥락으로 재사용하지 않는다**(URL만 신뢰). 서버·localStorage 변화 없음

#### MAIN-604 새 좌석 QR로 재진입 — seat 덮어쓰기 (복구)
- Given: localStorage `stop-island:seat`='a3'가 남아 있다(직전 스캔)
- When: 다른 자리 QR `/#/?seat=b1`로 진입한다
- Then: 셸 부트가 `stop-island:seat`를 'b1'로 덮어쓰고(최신 스캔 우선 — D-26), 메인이 `entrySeat`='b1'로 도착 히어로를 "당신의 자리 · **B1**", CTA [이 자리 잡기]로 렌더한다
- And: 서버 상태 변화 없음

#### MAIN-605 QR의 seat 값이 유효하지 않음 (오류)
- Given: `/#/?seat=zz9`처럼 존재하지 않는 좌석 id로 진입한다
- When: 부트 후 `GET /api/seats` 응답에 그 id가 없어 `findSeat`가 null을 반환한다(`seatInfo`가 null 유지 → `seatContext='loading'`)
- Then: 도착 히어로는 라벨 "ZZ9"로 렌더되지만 "자리 확인 중…"이 걷히지 않고 **[이 자리 잡기] CTA가 활성화되지 않는다**(비활성 "자리 확인 중…" 자리표시). 즉 존재하지 않는 좌석으로는 잡기로 진행할 수 없다
- And: `stop-island:seat`에는 'zz9'가 저장됨(부트는 값 유효성을 검증하지 않음 — 서버 판정은 잡기 시점 예약 API가 최종 방어). 서버 상태 변화 없음

> 📌 결정(구현): 유효하지 않은 seat id는 별도 에러 화면 없이 "자리 확인 중…" 대기 상태로 남긴다(CTA 비활성). 좌석 6개 규모에서 잘못된 QR은 극소수이고, 진행 자체가 막히므로 어뷰징 위험이 없다. 명시적 "없는 자리" 문구는 v1 미도입.

- **동시성**: 해당 없음 — seat 파싱·저장은 단일 탭 부트 동작이다(찍은 자리가 확정 전에 선점되는 경합은 04-reserve RSV-406/502가 다룬다).

---

## 기능 영역: 내비게이션 — CTA & 햄버거 메뉴 (D-15)

### 그룹 4 — 라우팅

#### MAIN-401 [이 자리 잡기] Primary CTA 탭 (정상, 변경 — D-26)
- Given: 도착 랜딩(available)이 렌더된 상태다
- When: Primary CTA "[이 자리 잡기]"를 탭한다
- Then: **곧바로 `/verify`(03 영수증 인증)로 push 이동한다** — 02 메뉴 선택을 건너뛴다. 좌석 맥락은 `stop-island:seat`로 이미 유지되므로 라우팅에 별도 파라미터를 싣지 않는다
- And: 서버·localStorage 변화 없음

> 📌 결정(변경): 과거 "CTA → `/menu`"는 폐기(D-26). 자리가 QR로 확정된 뒤엔 메뉴 분기가 불필요해 인증으로 직행한다.

#### MAIN-402 "방명록 구경하기" 링크 탭 (정상)
- Given: 메인의 어느 분기든(도착·이용 중·QR 유도·사용 중) 방명록 링크가 노출된 상태다
- When: "방명록 구경하기" 텍스트 링크를 탭한다
- Then: `/guestbook`(05 방명록)으로 push 이동한다
- And: 서버·localStorage 변화 없음

#### MAIN-403 햄버거 메뉴 열기·이동 (정상)
- Given: 게이트를 통과한 메인이 렌더된 상태다(게이트에는 헤더·햄버거가 없음 — MAIN-701)
- When: 헤더 우측 햄버거(≡) 버튼을 탭한다
- Then: 드로어가 열리고 **메인 / 메뉴 선택 / 방명록** 3개 항목을 표시한다(`NavBar`: `/`, `/menu`, `/guestbook`). 인증·예약 화면은 드로어에 없다(D-14 가드 우회 방지)
- And: 항목 탭 시 해당 라우트로 이동하고 드로어가 닫힌다. `/menu`는 이 드로어가 유일한 진입점이다(MAIN-401 이후). 서버·localStorage 변화 없음

#### MAIN-404 드로어 닫기 (경계)
- Given: 드로어가 열려 있다
- When: 오버레이(딤 영역) 또는 닫기(✕) 버튼을 탭한다
- Then: 드로어만 닫히고 라우트는 그대로다. 브라우저 히스토리에 항목이 쌓이지 않는다(순수 UI 상태)
- And: 서버·localStorage 변화 없음

> 📌 결정: 드로어 열림/닫힘은 히스토리에 push하지 않는다. 좌석 6개 규모 서비스에서 뒤로가기-드로어 연동은 과설계.

#### MAIN-405 만석 상태에서 [이 자리 잡기] 탭 (경계, D-13)
- Given: 현황 조연 한 줄이 "빈 자리 0석"이지만, 찍은 자리 A3 자체는 available이다
- When: "[이 자리 잡기]"를 탭한다
- Then: 막지 않고 `/verify`로 정상 진입한다(인증은 미리 하고 자리 유지하는 흐름 허용). 찍은 자리가 taken이면 CTA 자체가 없음(MAIN-602)
- And: 서버·localStorage 변화 없음

#### MAIN-406 다른 화면에서 back으로 메인 복귀 (복구)
- Given: 메인 → `/verify`로 이동해 메인이 unmount되고 폴링이 정리된 상태다
- When: 헤더 back으로 메인에 복귀한다
- Then: 메인이 재마운트되며 `GET /api/status`·`GET /api/seats`를 즉시 1회 호출하고 30초 폴링을 새로 시작한다. `reconcileReservation`도 다시 1회 수행한다
- And: 서버·localStorage 변화 없음

- **오류**: 해당 없음 — CTA/드로어는 순수 클라이언트 라우팅이라 서버 오류 표면이 없다(현황·예약·좌석 API 오류는 그룹 2·3·6에서 커버).
- **동시성**: 해당 없음 — 단일 사용자 탭 내 라우팅이며 경합 자원이 없다.

---

## 기능 영역: 네트워크 복구 & 일일 경계 (D-01, D-08)

### 그룹 5 — 오프라인·느린 네트워크·자정 경계

#### MAIN-501 오프라인 상태로 진입 (오류)
- Given: 페이지 셸은 로드됐으나(캐시/재방문) 기기가 오프라인이다. 좌석 QR로 진입해 게이트는 통과
- When: 도착 랜딩이 뜬다
- Then: 히어로·좌석 라벨(URL 값)·값 문구·CTA 등 정적 영역은 정상 렌더. 현황 조연 한 줄은 "현황을 불러오지 못했어요", seatInfo는 "자리 확인 중…"(로드 실패로 CTA 대기), "이용 중" 배너 미노출(MAIN-305 규칙)
- And: device_id는 정상 생성/재사용(오프라인과 무관). 서버 상태 변화 없음

#### MAIN-502 오프라인 → 온라인 복귀 (복구)
- Given: 메인 화면이 오프라인 실패 상태다
- When: 네트워크가 복구된다(`online` 이벤트)
- Then: `createPoll`의 online 핸들러가 status·seat를 즉시 재조회하고, 메인이 등록한 `online` 리스너가 `reconcile()`(내 예약)도 재시도한다. 성공 시 조연 한 줄·좌석 상세·배너가 채워진다
- And: 서버·localStorage 변화 없음

> 📌 결정: `window` `online` 이벤트 수신 시 즉시 status·seat·내 예약을 재조회한다(다음 폴링 주기를 기다리지 않음).

#### MAIN-503 느린 네트워크 — 중복 요청 방지 (경계)
- Given: 네트워크가 매우 느려 status 응답이 오래 걸린다
- When: 이전 status 요청이 아직 in-flight인 채 다음 폴링 주기가 도래한다
- Then: `fetchStatus`가 `if (inFlight) return`으로 해당 주기의 status 재요청을 스킵한다(동일 API 중복 요청 금지)
- And: 서버·localStorage 변화 없음

#### MAIN-504 자정 넘긴 재방문 — 어제 토큰·예약 (경계, D-08)
- Given: 어제 인증(approved)·예약을 마쳤고 localStorage에 `stop-island:verify`·`stop-island:reservation-id`가 남아 있다. 현재 시각은 KST 자정 이후다
- When: 좌석 QR로 재진입한다(또는 예약 흔적으로 게이트 통과)
- Then: `reconcileReservation` 결과 expired이므로 배너 미노출 + `stop-island:reservation-id` 삭제(MAIN-303 규칙, `ended` 안내)
- And: `stop-island:verify`은 메인에서 건드리지 않는다 — 토큰 만료 판정은 서버가 KST 자정 기준(D-01)으로 수행하며 `/verify`(03) 진입 시 무효 처리된다
- And: 도착 랜딩은 신규 방문과 동일하게 정상 렌더. 서버 상태 변화 없음(예약 expired 처리는 D-11 lazy 판정)

#### MAIN-505 당일 재방문 — device_id·active 예약 보존 (정상·복구)
- Given: 오늘 이미 인증·예약을 마쳤고 localStorage에 device-id·verify·reservation-id가 모두 존재하며 예약은 아직 active다
- When: 브라우저를 완전히 닫았다가 다시 연다(QR 재스캔 또는 예약 흔적으로 게이트 통과)
- Then: device_id 재사용(MAIN-102), reconcile이 active를 확인해 **"이용 중" 우선 노출**(MAIN-301) — 새로고침/재방문으로 예약 증빙을 잃지 않는다(D-10·D-28의 목적)
- And: 서버·localStorage 변화 없음

- **동시성**: 해당 없음 — 이 그룹은 단일 클라이언트의 네트워크·시간 경계 동작이며, 다중 행위자 경합은 그룹 3(MAIN-306)과 07-system(SYS)에서 다룬다.
