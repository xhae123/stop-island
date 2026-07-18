# 04 테이블 예약 — 시나리오 (RSV)

> **한 줄 요약:** 영수증 인증 토큰을 가진 사용자가 **QR로 지정된 자리 하나**의 상태를 확인하고 [이 자리 예약하기]로 예약을 확정한 뒤, 예약 완료 화면(D-09)에서 증빙·취소·만료·기대치 안내를 처리하고, 다시 들어왔을 때(재진입, D-28)까지 이어지는 전 과정의 Given/When/Then 명세. 좌석은 그리드에서 고르지 않는다 — **찍은 QR이 곧 좌석**이다(D-26).

**커버 범위:**
- 라우트 가드 (D-14: 토큰 없음 / 만료 / active 예약 보유) + 좌석 맥락 요구 (D-26: seat 없이 진입 시 QR 안내)
- 찍은 자리 하나의 상태 표시 (available → 확정 CTA / taken·closed → "사용 중" + 전체 현황 + 재스캔 안내)
- 30초 폴링으로 그 자리 상태 추적 (풀리면 CTA 활성 / 선점되면 재스캔 안내)
- 예약 확정 ([이 자리 예약하기] 성공 / 409 선점 → 재스캔 / 토큰 만료 / 더블탭 방지 / 응답 유실 복구)
- 예약 완료 화면 (D-09: 표시 항목, 자리 비우기, 만료 표시, 만료 후 재진입, 감사 무효화로 해제된 예약) + **기대치 안내(D-27: 자동 만료·알림 없음·재확보 가능)**
- 만료·취소 후 재예약 (D-08)
- **재진입 정책 (D-28: 이용 중이면 그 자리 최우선 · 한 번에 한 자리 · 종료 후 재진입 안내)**
- 새로고침 복구 (D-10) · 타 기기 접근 차단 (device_id 소유 검증)

> ⚠️ wireframe-spec/04의 WebSocket/SSE, `qr_token`은 결정표(D-12, D-09)에서 폐기됨.
> ⚠️ **좌석 그리드 선택 UI는 D-26에서 폐기됨.** 좌석은 QR(`/#/?seat=a3`)로 결정되어 `stop-island:seat`에 저장된다. 이 문서는 **30초 폴링 + QR 지정 좌석 + QR 없는 예약 완료 화면**을 전제로 한다.
> 📌 폐기 시나리오(D-26): **RSV-301~305**(좌석 선택 토글 그룹 전체), **RSV-402**(고르는 사이 뺏김). 각 자리에 "폐기 — D-26" 표기.

**이 문서의 localStorage 키:**

| 키 | 값 | 기록 시점 |
|---|---|---|
| `stop-island:device-id` | UUID (D-07) | 최초 접속 |
| `stop-island:verify` | verify token + 인증 상태 JSON (03-verify 규약) | 03 인증 승인 시 |
| `stop-island:seat` | seat id (D-26) | QR 부트(`?seat=`) 시 |
| `stop-island:reservation-id` | reservation_id (D-10) | 예약 확정 성공 시 |

> 📌 결정: verify token은 localStorage `stop-island:verify`에 `{ token?, verification_id, status, issued_date, shop_name? }` JSON으로 저장한다(03-verify 공통 전제와 동일 규약 — 03이 쓰고 04가 읽는다). `issued_date`(KST 날짜)가 오늘과 다르면 클라이언트가 만료로 간주하고 키를 삭제한다(서버 검증과 별개의 1차 필터).

> 📌 결정: 예약 대상 좌석은 `stop-island:seat`에서 읽는다(QR 부트 시 `?seat=`로 기록 — D-26). 이 값이 없으면 예약 경로는 좌석을 특정할 수 없으므로 "현장 좌석의 QR을 찍어주세요" 안내로 대체한다(RSV-106). `GET /api/seats` 응답에서 이 seat id로 필터해 **그 자리 하나의 상태**(available/taken/closed)만 소비한다 — 그리드를 그리지 않는다.

---

## 라우트 가드 & 진입 (D-14 + D-26 좌석 요구)

관점 커버: 정상 RSV-102 / 경계 RSV-103 / 오류 RSV-101·RSV-106 / 동시성 RSV-105 / 복구 RSV-104

### 진입 가드

#### RSV-101 토큰 없이 직접 진입 (오류)
- Given: localStorage에 `stop-island:verify`이 없다
- When: 사용자가 URL로 `/reserve`에 직접 진입한다
- Then: 렌더 전에 `/verify`로 리다이렉트된다
- And: 서버 호출 없음, localStorage 변화 없음

#### RSV-102 유효 토큰 + 좌석 맥락으로 정상 진입 (정상)
- Given: 오늘(KST) 발급된 approved 토큰이 localStorage에 있고, `stop-island:seat`에 QR로 찍은 좌석(예: a3)이 있으며, 내 active 예약이 없다
- When: 03에서 인증 성공 직후 `/reserve`로 전환된다 (QR로 찍은 자리 맥락이 유지된 채)
- Then: 헤더 "이 자리 예약" + "{shop_name} 영수증 인증 완료" 배너가 표시되고, `GET /api/seats` 호출로 **찍은 자리(A3) 하나의 상태 판정**이 시작된다 (그리드 렌더 아님 — D-26)
- And: 서버·localStorage 변화 없음

#### RSV-103 자정 경과로 토큰 만료된 상태 진입 (경계)
- Given: localStorage 토큰의 `issued_date`가 어제(KST)다
- When: `/reserve`에 진입한다
- Then: 클라이언트가 토큰을 만료로 판정하고 `/verify`로 리다이렉트, "인증이 만료되었어요. 오늘 영수증으로 다시 인증해주세요" 안내 표시
- And: localStorage `stop-island:verify` 삭제. 서버 verifications row는 변화 없음(당일 자정 이후 자연 만료 — D-08)

#### RSV-104 active 예약 보유 상태로 진입 (복구 겸)
- Given: localStorage에 `stop-island:reservation-id`가 있고 `GET /api/reservations/:id`가 `status=active`를 반환한다
- When: `/reserve`에 진입한다 (뒤로가기·URL 직접 입력 포함, 그리고 **다른 자리 QR을 새로 찍고 들어온 경우 포함** — D-28)
- Then: 좌석 상태 화면 대신 **예약 완료 화면**으로 리다이렉트된다 (동시 active 예약 1건 원칙 — D-08). 좌석 맥락(seat) 유무·값과 무관하게 이 가드가 우선한다 — **한 번에 한 자리**라 다른 자리 QR을 찍어도 새 예약을 만들지 않는다(옮기려면 먼저 비우고 재스캔 — D-28). 재진입 흐름 전체는 RSV-901~902 참조
- And: 서버·localStorage 변화 없음

#### RSV-105 진입 후 다른 탭에서 토큰 소진 (동시성)
- Given: 두 탭이 같은 토큰으로 `/reserve`를 열어 두었다 (같은 자리 QR 또는 각기 다른 자리 QR)
- When: 탭 A가 예약을 확정한 뒤 탭 B에서 확정을 시도한다
- Then: 탭 B는 서버 409 `ALREADY_RESERVED` 응답을 받고, 응답에 포함된 기존 `reservation_id`로 예약 완료 화면으로 이동한다 (RSV-506의 서버 규약)
- And: localStorage `stop-island:reservation-id`가 기존 예약 id로 갱신됨. 서버에 새 row 없음

#### RSV-106 좌석 맥락 없이 진입 — 공유 링크 등 (오류)
- Given: 유효한 approved 토큰과 미보유 active 예약 상태이나 `stop-island:seat`가 없다 (QR 없이 공유 링크·주소창으로 진입)
- When: `/reserve`에 진입한다
- Then: 좌석 상태 패널·확정 CTA 대신 "예약하려면 현장 좌석의 QR을 찍어주세요" 안내와 [메인으로] 버튼을 렌더한다. 특정할 좌석이 없어 `GET /api/seats` 호출도 하지 않는다
- And: 서버·localStorage 변화 없음

> 📌 결정: 가드 우선순위는 ① 토큰 유효성(RSV-101/103) → ② active 예약(RSV-104) → ③ 좌석 맥락(RSV-106) 순이다. 좌석 QR이 없어도 이미 예약이 있으면 완료 화면으로 보낸다.

---

## 찍은 자리 상태 표시 (D-26)

관점 커버: 정상 RSV-201 / 경계 RSV-202·RSV-203 / 오류 RSV-204 / 동시성 — 폴링 영역(RSV-406)에서 커버 / 복구 RSV-205

> 📌 결정: `GET /api/seats` 응답에서 `stop-island:seat`의 seat id로 필터해 그 좌석 하나의 status(`available | taken | closed`)만 본다. available이면 [이 자리(A3) 예약하기] CTA를 활성화하고, taken/closed이면 **CTA를 아예 노출하지 않고**(비활성이 아니라 미표시 — 그리드가 없어 다른 자리로 갈아탈 대상이 화면에 없다) "이 자리는 지금 사용 중이에요"류 안내 + 전체 빈자리 현황(`/api/status`의 `available_seats`) + "빈 자리의 QR을 찍어주세요"를 표시한다. `closed`(운영 중지)도 사용자에겐 "지금 앉을 수 없는 자리"라 taken과 같은 계열의 안내를 쓰되 사유 문구만 다르다.

### 상태별 표시

#### RSV-201 찍은 자리가 available (정상)
- Given: RSV-102 상태로 진입했고 찍은 자리 A3가 available(4인석)다
- When: `GET /api/seats` 응답이 도착한다
- Then: 스켈레톤이 사라지고 "A3 · 4인석 · 창가 자리" 카드와 [이 자리(A3) 예약하기] CTA(활성)가 표시된다
- And: 서버·localStorage 변화 없음

#### RSV-202 찍은 자리가 사용 중 (경계)
- Given: 찍은 자리 A3에 이미 다른 사람의 active 예약이 있다(taken)
- When: 좌석 상태가 도착한다
- Then: "이 자리(A3)는 지금 사용 중이에요" 안내 + "지금 빈 자리 N석" 전체 현황 + "빈 자리의 QR을 찍어주세요" 안내가 표시된다. **[이 자리 예약하기] CTA는 노출하지 않는다**(D-26 — 그리드가 없어 다른 자리로 갈아탈 수 없고, 다른 빈자리는 그 자리 QR을 찍어야 진입)
- And: 서버·localStorage 변화 없음

#### RSV-203 찍은 자리가 운영 중지 (경계)
- Given: 찍은 자리 B2가 `is_open=false`(closed)다
- When: 좌석 상태가 도착한다
- Then: "이 자리(B2)는 지금 운영하지 않아요" 안내 + 전체 빈자리 현황 + "빈 자리의 QR을 찍어주세요". CTA 미노출. taken(RSV-202)과 사유 문구만 다르고 처리는 동일
- And: 서버·localStorage 변화 없음

#### RSV-204 좌석 상태 로딩 실패 (오류)
- Given: 네트워크 단절 또는 서버 5xx
- When: `GET /api/seats`가 실패한다
- Then: "좌석 현황을 불러오지 못했어요" + [다시 시도] 버튼 표시. 확정 CTA 미노출
- And: 서버·localStorage 변화 없음

#### RSV-205 재시도로 복구 (복구)
- Given: RSV-204 상태
- When: [다시 시도]를 탭하고 `GET /api/seats`가 성공한다
- Then: 찍은 자리 상태에 따라 RSV-201/202/203 중 하나로 렌더되고 30초 폴링 타이머가 (재)시작된다
- And: 서버·localStorage 변화 없음

---

## 좌석 선택 인터랙션 — 폐기 (D-26)

> 📌 폐기: 좌석 그리드에서 자리를 고르는 UI가 사라졌으므로(D-26) 이 그룹 전체를 폐기한다. 좌석은 찍은 QR로 이미 결정되어 있어 "선택" 인터랙션 자체가 존재하지 않는다.
>
> - **RSV-301** available 좌석 선택 — 폐기 (D-26)
> - **RSV-302** 다른 좌석 탭 → 선택 이동 — 폐기 (D-26)
> - **RSV-303** 같은 좌석 재탭 → 해제 — 폐기 (D-26)
> - **RSV-304** taken 좌석 탭 무시 — 폐기 (D-26)
> - **RSV-305** closed 좌석 탭 무시 — 폐기 (D-26)
>
> 대체: 찍은 자리 하나의 상태 표시는 RSV-201~205, 그 자리가 폴링 중 선점되는 동시성은 RSV-406, 확정 시점 선점은 RSV-502.

---

## 30초 폴링 — 찍은 자리 상태 추적 (D-12)

관점 커버: 정상 RSV-401 / 경계 RSV-404 / 오류 RSV-403 / 동시성 RSV-406 / 복구 RSV-405

> 📌 결정: 폴링은 그리드 전체가 아니라 **찍은 자리 하나**의 status를 갱신한다. 폴링 실패는 무음으로 넘기고 직전 데이터를 유지한다(에러 UI 없음). 단, 예약 확정 등 사용자 액션의 실패는 반드시 표면화한다(무음 금지는 액션 실패에 적용). 또한 `POST /api/reserve` 요청이 진행 중일 때 도착한 폴링 응답은 **폐기**한다(확정 결과와의 화면 충돌 방지).

### 주기 갱신과 선점 감지

#### RSV-401 폴링으로 자리가 풀림 (정상)
- Given: 찍은 자리 A3가 taken이라 RSV-202 "사용 중" 안내가 떠 있다
- When: A3 예약이 취소/만료된 뒤 다음 30초 폴링(`GET /api/seats`)에서 A3가 available로 내려온다
- Then: "사용 중" 안내가 사라지고 "A3 · 4인석 · 창가 자리" 카드 + [이 자리(A3) 예약하기] CTA(활성)로 전환된다
- And: 서버·localStorage 변화 없음

#### RSV-402 고르는 사이 뺏김 — 폐기 (D-26)
- 폐기: 좌석을 미리 골라두는 단계가 없어졌다(그리드 폐기). "선택 상태가 폴링에서 강제 해제"되는 상황은 존재하지 않는다. 대체 — 찍은 자리가 폴링 중 taken으로 바뀌는 동시성은 RSV-406.

#### RSV-403 폴링 요청 실패 (오류)
- Given: 화면이 열려 있는데 일시적 네트워크 불량이 발생한다
- When: 30초 폴링 `GET /api/seats`가 실패한다
- Then: 화면은 직전 데이터를 그대로 유지하고 에러 UI를 띄우지 않는다(📌 위 결정). 다음 주기에 재시도
- And: 서버·localStorage 변화 없음

#### RSV-404 확정 요청 중 폴링 응답 도착 (경계)
- Given: [이 자리 예약하기]를 눌러 `POST /api/reserve` 응답 대기 중이다
- When: 그 사이 30초 폴링 응답이 도착한다
- Then: 폴링 응답은 폐기되고(📌 위 결정) 화면은 확정 결과(성공→완료 화면 / 409→재스캔 안내)만 따른다
- And: 서버·localStorage 변화는 확정 결과 시나리오(RSV-501/502)를 따름

#### RSV-405 백그라운드 탭 복귀 (복구)
- Given: 사용자가 탭을 백그라운드로 뒀다가 5분 뒤 돌아온다
- When: 탭이 다시 활성화된다(visibilitychange)
- Then: 30초 주기를 기다리지 않고 즉시 `GET /api/seats`를 1회 호출해 찍은 자리 상태를 최신화한다. 그 사이 자리가 taken이 되어 있으면 RSV-406과 동일 처리
- And: 서버·localStorage 변화 없음

#### RSV-406 폴링 중 이 자리가 선점됨 (동시성)
- Given: 찍은 자리 A3가 available이라 [이 자리 예약하기] CTA가 떠 있고, 아직 확정하지 않았다
- When: 다른 사용자가 같은 A3 QR을 찍고 먼저 확정해, 다음 폴링 응답에서 A3가 taken으로 내려온다
- Then: CTA가 사라지고 "이 자리는 방금 다른 분이 예약했어요" + 전체 빈자리 현황 + "빈 자리의 QR을 찍어주세요"(RSV-202 계열)로 즉시 전환된다 — **무음 처리 금지**. 폴링이 놓쳐 확정까지 갔더라도 확정 API 409가 최종 방어(RSV-502)
- And: 서버·localStorage 변화 없음

---

## 예약 확정 (POST /api/reserve)

관점 커버: 정상 RSV-501 / 경계 RSV-504 / 오류 RSV-503·RSV-505 / 동시성 RSV-502 / 복구 RSV-506

> 📌 결정: `POST /api/reserve`의 `seat_id`는 그리드 선택값이 아니라 `stop-island:seat`(QR에서 부트 시 저장)에서 온다(D-26). API 계약 자체는 무변경.
>
> 📌 결정: 응답 유실 대비 서버 규약 — `POST /api/reserve` 시 해당 device_id(또는 verify_token)에 이미 active 예약이 있으면 409 `ALREADY_RESERVED` + **기존 `reservation_id`를 응답 body에 포함**한다. 프론트는 이를 받으면 실패가 아니라 "이미 예약됨"으로 간주하고 그 id로 예약 완료 화면에 진입한다. 이 규약 하나로 더블탭 레이스·응답 유실·두 탭 충돌이 모두 복구된다.
>
> 📌 결정: 소유 검증을 위해 `reservations` 테이블에 `device_id TEXT NOT NULL` 컬럼을 추가한다(예약 시 `X-Device-Id` 기록). db-schema.md 갱신 필요.

### 확정 요청

#### RSV-501 예약 확정 성공 (정상)
- Given: 찍은 자리 A3가 available이고 토큰이 유효하다
- When: [이 자리(A3) 예약하기]를 탭하고 `POST /api/reserve { seat_id: "a3", verify_token }`가 성공한다
- Then: 화면 — **예약 완료 화면**(D-09)으로 전환된다. 서버 — reservations에 `{ seat_id: 'a3', verify_token, device_id, status: 'active', expires_at: reserved_at+2h }` row 생성. localStorage — `stop-island:reservation-id`에 `reservation_id` 저장 (D-10)
- And: 응답에 `qr_token` 없음 (D-09에서 폐기)

#### RSV-502 409 선점 충돌 → 재스캔 안내 (동시성)
- Given: 나와 타인이 같은 A3 QR을 찍고 거의 동시에 [이 자리 예약하기]를 눌렀다
- When: 서버 트랜잭션에서 내가 후순위가 되어 409 `SEAT_TAKEN`을 받는다
- Then: "아쉽지만 방금 다른 분이 먼저 예약했어요" 안내 + 전체 빈자리 현황 + "다른 빈 자리의 QR을 찍어주세요"를 표시한다. **다시 고르라고 하지 않는다**(그리드 없음 — D-26). 확정 CTA는 사라진다
- And: 서버 — 내 명의 row 생성 없음. localStorage 변화 없음

#### RSV-503 토큰 만료로 확정 실패 (오류)
- Given: 예약 화면을 자정(KST) 전에 열어 두고 자정을 넘겼다
- When: [이 자리 예약하기]를 탭하고 서버가 401 `TOKEN_EXPIRED`를 반환한다
- Then: "인증이 만료되었어요. 오늘 영수증으로 다시 인증해주세요" 안내 후 `/verify`로 이동
- And: localStorage `stop-island:verify` 삭제. 서버 row 생성 없음

#### RSV-504 더블탭 중복 제출 방지 (경계)
- Given: 찍은 자리 A3가 available이다
- When: [이 자리 예약하기]를 빠르게 두 번 탭한다
- Then: 첫 탭 즉시 버튼이 disabled+스피너로 바뀌어 두 번째 탭은 무시된다. 요청은 1회만 발생
- And: 혹시 클라이언트 방어가 뚫려 2회 요청이 나가도 서버가 두 번째를 409 `ALREADY_RESERVED`(기존 id 포함)로 흡수 — 결과는 RSV-501과 동일한 완료 화면

#### RSV-505 확정 중 네트워크 오류 (오류)
- Given: 찍은 자리 A3가 available이고 확정을 탭했다
- When: 요청이 타임아웃/네트워크 에러로 실패한다(서버 도달 여부 불명)
- Then: "예약을 확정하지 못했어요. 다시 시도해주세요" 표시, 버튼 재활성화. **찍은 자리 맥락은 유지**(재시도 편의 — `stop-island:seat` 그대로)
- And: localStorage 변화 없음

#### RSV-506 응답 유실 후 재시도 (복구)
- Given: RSV-505에서 실제로는 서버에 예약이 생성됐지만 응답만 유실됐다
- When: 사용자가 다시 [이 자리(A3) 예약하기]를 탭한다
- Then: 서버가 409 `ALREADY_RESERVED` + 기존 `reservation_id`를 반환하고(📌 위 결정), 프론트는 이를 성공처럼 처리해 예약 완료 화면으로 진입한다
- And: localStorage `stop-island:reservation-id`에 기존 id 저장. 서버에 중복 row 없음

---

## 예약 완료 화면 (D-09 신설)

관점 커버: 정상 RSV-601, RSV-602 / 경계 RSV-604(카운트다운 0 도달) / 오류 RSV-605, RSV-608(감사 무효화) / 동시성 RSV-606 / 복구 RSV-607

> 📌 결정: 만료 표시는 **절대 시각 + 남은 시간 병기**로 한다 — "16:42까지 이용 가능 (남은 시간 1시간 58분)". 남은 시간은 **1분 주기** 갱신(초 단위 카운트다운 없음 — 2시간 스케일에 초는 조급함만 유발). 남은 시간이 0이 되면 `GET /api/reservations/:id`로 서버 상태를 확인한 뒤 만료 UI로 전환한다(클라이언트 시계 단독 판정 금지 — D-01).
>
> 📌 결정: 만료·취소된 예약으로 이 화면에 재진입하면 "이용이 끝난 예약이에요" 상태 화면(좌석 라벨 + [메인으로] + "오늘 다시 예약할 수 있어요" 안내 — D-08)을 보여주고 localStorage `stop-island:reservation-id`를 삭제한다.
>
> 📌 결정(D-27): **종료 알림은 보내지 않는다.** 사전 푸시·문자 없이 서버가 2시간에 자동 만료·반납(D-11)만 한다(익명·무로그인 원칙 D-07상 나간 유저 도달 수단이 없음). 그래서 이 완료 화면이 유일하게 기대치를 설정하는 지점이다 — "자동 정리 · 알림 없음 · 시간 안에 재확보 가능" 3줄을 반드시 노출한다(RSV-601 ⑦). 만료 시각은 서버가 UTC-aware(오프셋 포함)로 내보내고 프론트가 KST로 표시한다(과거 버그: naive UTC를 로컬로 오해 → 수정됨. D-01).

### 표시와 자리 비우기

#### RSV-601 완료 화면 표시 항목
- Given: RSV-501로 예약이 확정됐다 (A3, 4인석, expires_at 16:42)
- When: 예약 완료 화면이 렌더된다
- Then: ① 좌석 라벨 "A3" ② "4인석 · 창가 자리" ③ "16:42까지 이용 가능 (남은 시간 1시간 58분)" ④ "내 자리와 이용 시간을 확인하는 화면이에요" 안내 ⑤ [방명록 쓰기] 버튼(→ 05) ⑥ [자리 비우기] 버튼 ⑦ **기대치 안내(D-27)** — "시간이 되면 자동으로 자리가 정리돼요 · 따로 알림은 가지 않으니 남은 시간을 확인해주세요 · 더 머물고 싶으면 시간 안에 다시 잡을 수 있어요"가 표시된다. QR 코드는 없다 (D-09)
- And: 이 화면은 **본인 확인용**이다 — 무인 운영(D-00)이라 제시할 상대가 없고, 타인에게 보여주는 티켓 개념이 아니다 (D-09)
- And: ⑦ 기대치 3줄은 유저가 자리를 뜨기 전에 "알림 없이 자동 만료" 규칙을 인지하게 하는 유일한 지점이다(D-27) — 사전 알림이 없으므로 이 문구가 곧 회전 정책의 고지다
- And: 서버·localStorage 변화 없음

#### RSV-602 자리 비우기 성공
- Given: 완료 화면에서 active 예약을 보고 있다
- When: [자리 비우기] 탭 → "자리를 비울까요? 예약이 취소돼요" 확인 다이얼로그에서 [비우기]를 탭한다
- Then: `DELETE /api/reservations/:id` 성공 → "이용해주셔서 감사해요" 안내와 함께 메인(01)으로 이동. 서버 — 해당 row `status='cancelled'`. localStorage — `stop-island:reservation-id` 삭제
- And: 같은 토큰으로 당일 재예약 가능해짐 (D-08)

#### RSV-603 자리 비우기 다이얼로그 취소
- Given: 확인 다이얼로그가 떠 있다
- When: [취소]를 탭한다
- Then: 다이얼로그만 닫히고 완료 화면 유지
- And: 서버·localStorage 변화 없음

#### RSV-604 화면을 보는 중 만료 시각 도달 (경계)
- Given: 완료 화면이 열려 있고 남은 시간이 1분 미만이다
- When: 남은 시간이 0이 되어 `GET /api/reservations/:id`를 호출하고 `status='expired'`(lazy 만료 — D-11)를 받는다
- Then: 화면이 "이용 시간이 끝났어요" 만료 상태로 전환되고 [메인으로] 버튼 + "오늘 다시 예약할 수 있어요" 안내 표시. 서버 — row `status='expired'`. localStorage — `stop-island:reservation-id` 삭제
- And: 사용자에게 별도 푸시/알림은 없다(D-27 — 화면을 보고 있으면 화면 내 전환, 떠났으면 조용히 자동 반납). 완료 화면 ⑦ 기대치 문구가 이 결과를 미리 고지했다

#### RSV-605 자리 비우기 요청 실패
- Given: 확인 다이얼로그에서 [비우기]를 탭했다
- When: `DELETE /api/reservations/:id`가 네트워크 오류/5xx로 실패한다
- Then: "자리 비우기에 실패했어요. 다시 시도해주세요" 표시, 완료 화면과 예약 상태 유지
- And: 서버 row `active` 유지, localStorage 유지

#### RSV-606 취소와 만료 스윕의 경합 (동시성)
- Given: expires_at 직전에 [자리 비우기]를 탭했다
- When: DELETE 처리 시점에 백그라운드 스윕(D-11)이 먼저 해당 row를 `expired`로 바꿨다
- Then: 서버는 이미 종료된 예약에 대한 DELETE를 에러 없이 멱등 처리(200)하고, 프론트는 RSV-602와 동일하게 메인으로 이동한다. 사용자 관점 차이 없음
- And: 서버 row는 `expired` 유지(cancelled로 덮어쓰지 않음). localStorage — id 삭제

#### RSV-607 새로고침 복구
- Given: 완료 화면에서 브라우저를 새로고침했다 (또는 나중에 메인의 "내 예약 보기" 배너로 재진입 — D-10)
- When: localStorage의 `stop-island:reservation-id`로 `GET /api/reservations/:id`를 호출한다
- Then: `active`면 RSV-601과 동일한 완료 화면 복원(남은 시간은 서버 `expires_at` 기준 재계산). `expired`/`cancelled`면 📌 결정대로 "이용이 끝난 예약이에요" 상태 화면 + localStorage id 삭제
- And: 서버 변화 없음

#### RSV-608 감사 무효화로 예약이 해제된 뒤 재조회 (오류)
- Given: `needs_audit` 인증이 사후감사에서 어뷰징으로 판정되어(03 VF-504, 06 ADM-212) 인증은 `REVOKED_BY_AUDIT`로 무효화되고 내 active 예약은 `cancelled`로 해제됐다. 나는 완료 화면을 띄워 둔 채였다
- When: 완료 화면을 새로고침하거나 1분 주기 갱신 시점에 `GET /api/reservations/:id`를 호출한다
- Then: `status='cancelled'` 수신 → "예약이 취소되었어요" 상태 화면([메인으로] 버튼)으로 전환하고 localStorage `stop-island:reservation-id`를 삭제한다 — 화면 경로는 관리자 수동 해제(ADM-402)와 동일하다
- And: 관리자 해제와의 차이는 **재예약 시점**에 드러난다 — 인증까지 무효화됐으므로 `/reserve` 재진입은 가드(D-14)·토큰 검증에서 막히고 `/verify`로 보내져 재인증부터 다시 시작한다(03 VF-505). 관리자 해제(토큰 생존)면 곧바로 재예약 가능(RSV-701)

> 📌 결정: **취소 사유는 사용자 화면에서 구분하지 않는다.** `GET /api/reservations/:id`의 cancelled에 사유 필드를 노출하지 않고, 관리자 해제든 감사 무효화든 같은 "예약이 취소되었어요" 화면을 쓴다. 차이는 다음 행동(재예약 가능 여부)이 가드에서 자연스럽게 알려준다 — 어뷰징 판정 사실을 화면에 명시해 현장 시비를 만들 이유가 없다.

---

## 만료·취소 후 재예약 (D-08)

관점 커버: 정상 RSV-701, RSV-702 / 경계 RSV-704 / 오류 RSV-703 / 동시성 — 해당 없음(재예약 시점의 좌석 경합은 RSV-502가 동일하게 커버) / 복구 — 해당 없음(RSV-607이 커버)

### 같은 토큰으로 다시

#### RSV-701 취소 후 재예약
- Given: RSV-602로 예약을 취소했고 토큰은 아직 당일 유효하다
- When: 빈 자리의 QR을 다시 찍어(또는 `stop-island:seat`에 남은 직전 자리로) 예약 흐름에 재진입한다
- Then: `/verify`는 D-14에 따라 "오늘 인증 완료" 상태로 렌더되고 곧바로 `/reserve`가 찍은 자리 상태를 보여준다(available이면 [이 자리 예약하기]로 진행). 새 영수증 인증은 요구되지 않는다
- And: 확정 시 서버에 새 reservation row 생성(이전 row는 `cancelled`로 남음)

#### RSV-702 만료 후 재예약
- Given: 예약이 2시간 경과로 `expired` 처리됐고 토큰은 당일 유효하다
- When: 빈 자리의 QR을 다시 찍어 [이 자리 예약하기]로 확정한다
- Then: RSV-501과 동일하게 성공한다 — active 예약이 없으므로 `ALREADY_RESERVED`에 걸리지 않음
- And: localStorage `stop-island:reservation-id`가 새 id로 저장됨

#### RSV-703 active 예약 보유 중 API 직접 호출
- Given: active 예약이 있는 상태에서 (라우트 가드를 우회해) `POST /api/reserve`를 직접 호출한다
- When: 서버가 요청을 처리한다
- Then: 409 `ALREADY_RESERVED` + 기존 reservation_id 반환. 새 row 생성 없음 (동시 active 1건 — D-08)
- And: 정상 UI 경로에서는 RSV-104 가드로 이 화면에 도달하지 않음

#### RSV-704 자정 경과 후 재예약 시도 (경계)
- Given: 어제 발급된 토큰으로 어제 예약을 취소했다
- When: 오늘 재예약을 시도한다
- Then: 클라이언트 1차 필터(RSV-103) 또는 서버 401 `TOKEN_EXPIRED`(RSV-503)로 차단되고 `/verify` 재인증으로 안내된다 — "영수증 하나 = 하루 이용권"
- And: localStorage `stop-island:verify` 삭제

---

## 보안 — 예약 소유 검증

관점 커버: 오류 RSV-801, RSV-802 / 정상·경계·동시성·복구 — 해당 없음(이 영역은 비정상 접근 차단이 목적이며 정상 경로는 RSV-607이, 경합은 RSV-506이 커버)

### 타 기기 접근 차단

#### RSV-801 타 기기에서 reservation_id 추측 조회
- Given: 기기 B가 기기 A의 reservation_id를 알아냈다(URL 공유·추측)
- When: 기기 B가 자신의 `X-Device-Id`로 `GET /api/reservations/:id`를 호출한다
- Then: 서버가 row의 `device_id`와 헤더를 대조해 403 `FORBIDDEN` 반환(존재 여부를 숨기려면 404로 통일해도 됨 — 구현 시 403으로 확정). 화면에는 "예약을 찾을 수 없어요" + 메인 이동
- And: 서버·localStorage 변화 없음

#### RSV-802 타 기기에서 DELETE 시도
- Given: RSV-801과 동일한 상황
- When: 기기 B가 `DELETE /api/reservations/:id`를 호출한다
- Then: 403 `FORBIDDEN`. 기기 A의 예약은 `active` 유지
- And: 서버·localStorage 변화 없음

#### RSV-803 localStorage id가 서버에 없음
- Given: localStorage에 `stop-island:reservation-id`가 있으나 서버에서 해당 row가 없다(DB 초기화 등)
- When: `GET /api/reservations/:id`가 404를 반환한다
- Then: 오류 화면 없이 조용히 localStorage id를 삭제하고 메인(01)을 일반 상태로 렌더한다 ("내 예약 보기" 배너 미노출)
- And: 서버 변화 없음

---

## 재진입 정책 — 다시 들어왔을 때 (D-28)

관점 커버: 정상 RSV-901 / 경계 RSV-902 / 오류 RSV-903 / 동시성 — 해당 없음(재진입 순간의 좌석 경합은 RSV-406·RSV-502가 동일하게 커버) / 복구 RSV-904

> 📌 결정: 재진입(QR 재스캔·앱 재오픈)의 **진입점 UI는 메인(01)이 그린다**(MAIN-*). 04는 그 재진입이 예약 흐름에 닿는 지점만 명세한다. 세 갈래로 정리한다 — ① **active 예약 보유** → 그 자리가 최우선(메인이 "이용 중 · {좌석} · [내 자리 보기]", 가드 RSV-104가 `/reserve` 직접 진입도 완료 화면으로) ② **한 번에 한 자리** → 다른 자리 QR을 찍어도 새 예약 불가(옮기려면 비우고 재스캔) ③ **예약 종료(만료·취소) 후 재진입** → 메인이 "이전 이용이 끝났어요" 안내를 얹고, 당일 토큰이 유효하면 재인증 없이 재예약(RSV-701/702), 토큰 만료면 재인증(RSV-704/RSV-103). 완료 화면 재진입(D-10) 정합은 RSV-607.

### 재진입 갈래

#### RSV-901 active 예약 보유로 재진입 (정상)
- Given: 내 active 예약(A3)이 있고, 좌석 QR 재스캔 또는 앱 재오픈으로 메인(01)에 다시 들어왔다
- When: 메인이 `GET /api/reservations/:id`로 예약을 확정하고 "이용 중 · A3 · [내 자리 보기]"를 최우선 노출한다(MAIN-301)
- Then: [내 자리 보기]를 탭하면 `/reservation/:id` 예약 완료 화면(RSV-601)으로 진입한다. active 예약이 좌석 QR 맥락보다 우선하며(D-28①), `/reserve`로 직접 진입해도 RSV-104 가드가 완료 화면으로 보낸다
- And: 서버·localStorage 변화 없음

#### RSV-902 이용 중 다른 자리 QR로 재진입 — 한 자리 규칙 (경계)
- Given: 내 active 예약(A3)이 있는데 다른 빈 자리 B1의 QR을 찍어 재진입했다(`/#/?seat=b1`)
- When: 메인이 active 예약을 감지한다
- Then: B1 도착 화면이 아니라 "이용 중 · A3" 화면이 뜨고, "한 번에 한 자리만 이용할 수 있어요 — 옮기려면 지금 자리를 비운 뒤 그 자리 QR을 다시 찍어주세요" 안내가 얹힌다(MAIN). `/reserve`로 우회해 B1로 `POST /api/reserve`를 시도해도 서버가 409 `ALREADY_RESERVED` + 기존 A3 예약 id로 흡수한다(RSV-703·RSV-104)
- And: 서버에 B1 예약 row 없음. localStorage `stop-island:seat`는 최신 스캔(b1)으로 덮이지만 active 예약(A3)은 그대로

#### RSV-903 예약 종료 후 재진입 (오류)
- Given: 직전 예약(A3)이 만료·취소로 종료됐고(localStorage에 직전 흔적), 당일(KST) 토큰은 아직 유효하다
- When: 좌석 QR로 재진입한다
- Then: 메인이 직전 예약이 사라진 것을 감지해 "이전 이용이 끝났어요 · 이 자리를 다시 잡을 수 있어요" 안내를 도착 화면에 얹는다(MAIN). [이 자리 잡기] → `/verify`는 "오늘 인증 완료"로 통과(D-14) → `/reserve`가 찍은 자리 상태를 보여주고 **재인증 없이 재예약**(RSV-701/702)
- And: 서버 변화 없음. 종료된 예약 흔적(localStorage id)은 완료 화면 재조회 시점에 이미 정리된다(RSV-604·607·803)

#### RSV-904 종료 + 토큰까지 만료된 채 재진입 (복구)
- Given: 직전 예약이 종료됐고 토큰도 자정(KST) 경과로 만료됐다
- When: 좌석 QR로 재진입해 예약을 시도한다
- Then: "이전 이용이 끝났어요" 안내는 뜨지만, `/reserve` 진입 가드가 토큰 만료를 잡거나(RSV-103) 확정 시 서버 401(RSV-503)이 걸려 `/verify` 재인증부터 다시 시작한다 — "영수증 하나 = 하루 이용권"(D-08). 감사 무효화로 인증까지 무효화된 경우도 같은 재인증 경로다(RSV-608)
- And: localStorage `stop-island:verify` 삭제
