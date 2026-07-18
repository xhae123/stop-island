# 03 영수증 인증 — Given/When/Then 시나리오 (VF)

> **한 줄 요약:** 영수증 사진 업로드 → OCR이 **가게·결제 일시·금액·승인번호를 읽고**(D-29), 잘 읽힌 영수증은 **"이거 맞아요?" 확인 화면**(recognized)을 거쳐 유저가 즉석 확인한 뒤 당일 이용 토큰을 **그 자리에서** 발급받는 화면. 못 읽으면 상점 직접 선택(manual→즉시 승인), 중복·금액 미달·당일 아님은 확인 없이 즉시 거부. 확인 단계는 운영진 대기가 아니라 *유저 즉석 확인*이라 무인 운영(D-00)과 무관하다 — 사람을 기다리는 상태는 여전히 존재하지 않고, 애매한 건은 승인 + `needs_audit` 플래그(D-05), 어뷰징은 원격 사후감사(D-22)가 정리한다. 이 문서는 클라이언트 검증부터 인식·확인 단계, 최소 결제금액·사업자번호 매칭, OCR 장애 폴백, 1일 1회 제한, 자정 경계, 동시 제출, 사후감사 무효화까지 전 분기를 정의한다.
>
> 전제: `00-overview.md` 결정표(특히 D-00, D-01~D-08, D-14, D-22, D-24, D-25, **D-29**)와 `../design-receipt-ocr.md`(ReceiptEngine, Verifier 체인, severity 3단계, NotReceiptError, 이미지 해시 캐시)를 단일 진실로 삼는다.

## reason_code 전체 표

`POST /api/verify` 200 응답의 `reason_code`, 4xx/5xx 응답의 `error.code`(D-24), `GET /api/verify/status`의 `reason_code`에 공통으로 쓰는 코드 체계.

| 코드 | 결과 상태 | 사용자 문구 | 발생 조건 |
|---|---|---|---|
| `NOT_RECEIPT` | retry | "영수증 사진이 아닌 것 같아요. 영수증이 잘 보이게 다시 찍어주세요." | Extractor가 `is_receipt=false` → `NotReceiptError` (재시도 없이 즉시) |
| `MISSING_REQUIRED_FIELD` | retry | "영수증 정보를 읽지 못했어요. 상호명이 잘 보이게 다시 찍어주세요." | `RequiredFieldVerifier(store.name)` 실패 |
| `NOT_TODAY` | rejected | "오늘 결제한 영수증만 인정돼요. (영수증 날짜: {date})" | `DateVerifier(max_age_days=0)` 실패 — 서버 판정 시각의 KST 오늘과 불일치(D-01) |
| `SHOP_NOT_PARTICIPATING` | rejected | "참여 상점의 영수증이 아니에요. 참여 상점 목록을 확인해주세요." | 사업자번호 불일치 **그리고** 상호명 fuzzy 최고 유사도 < 0.5 (명백 불일치 — 사업자번호 매칭이 1순위, D-29) |
| `DUPLICATE_RECEIPT` | rejected | "이미 사용된 영수증이에요." | 승인 시점 `DuplicateStore.check_and_mark` 실패 — 승인번호 매칭 우선, 승인번호 None이면 이미지 해시 매칭. **확인 단계 없이 즉시 거부**(D-29) |
| `UNDER_MIN_AMOUNT` | rejected | "최소 결제금액(5,000원) 이상 영수증만 인정돼요." (금액값은 서버 설정에서 주입) | `MinAmountVerifier` 실패 — OCR 추출 결제 금액 < 최소 결제금액(📌 5,000원 잠정, 파트너 협의 후 확정 · 서버 설정 · 상점별 차등 가능 — D-29). **확인 단계 없이 즉시 거부** |
| `LOW_CONFIDENCE` | **approved + needs_audit** | (사용자 문구 없음 — 통상 승인과 동일하게 처리, D-05) | `ConfidenceVerifier` confidence < 0.6 — 감사 큐 표시용 내부 코드 |
| `SHOP_MATCH_UNCERTAIN` | **approved + needs_audit** | (사용자 문구 없음 — 통상 승인과 동일) | 사업자번호가 없어 상호명 fuzzy로 폴백했고 유사도 0.5 이상 0.7 미만 (경계선, D-29) — 감사 큐 표시용 내부 코드 |
| `MANUAL_SHOP_SELECTED` | **approved + needs_audit** | (사용자 문구 없음 — 통상 승인과 동일) | manual 경로 제출(D-04) — 감사 큐 표시용 내부 코드 |
| `REVOKED_BY_AUDIT` | rejected (사후 전환) | "운영진 확인 결과 인증이 취소되었어요. 다시 인증해주세요." | 원격 감사에서 어뷰징 판정 — 승인됐던 인증을 무효화(D-22). 사용자는 다음 조회 때 알게 됨 |
| `ALREADY_VERIFIED_TODAY` | HTTP 409 | "오늘은 이미 인증을 완료했어요. 좌석 선택으로 이동해주세요." | 당일(KST) approved 보유 상태에서 재제출 (D-06) |
| `OCR_UNAVAILABLE` | HTTP 503 | "사진 인증이 지금 어려워요. 아래에서 상점을 직접 선택해주세요." | Gemini 호출이 재시도 소진 후에도 실패 — 타임아웃·5xx·429 (D-25) |
| `INVALID_IMAGE` | HTTP 400 | "이미지를 읽을 수 없어요. 다른 사진으로 다시 시도해주세요." | 서버 측 이미지 디코딩 실패 / 형식·크기 위반(클라이언트 검증 우회 시) |
| `INVALID_REQUEST` | HTTP 400 | "인증 정보가 올바르지 않아요. 다시 시도해주세요." | image·shop_id 둘 다 없음, shop_id가 존재하지 않거나 비활성 상점 |
| `DEVICE_ID_REQUIRED` | HTTP 400 | "일시적인 오류예요. 새로고침 후 다시 시도해주세요." | `X-Device-Id` 헤더 누락 (D-07) |

클라이언트 단독 검증 메시지(서버 요청 없음 — VF-2xx에서 정의): 형식 위반 / 10MB 초과 / 손상 파일 / HEIC.

> **`recognized` 상태(D-29):** `POST /api/verify`(photo, confirm 플래그 없음)가 **거부/재촬영 사유 없이 판정을 통과**하면 즉시 승인·토큰 발급 대신 `status: "recognized"`로 응답한다 — `reason_code`가 아니라 새 **응답 상태**이며 확인 화면(VF-301)을 그린다. 이 응답은 **row를 남기지 않고 토큰도 발급하지 않는다**(pending 아님). 실제 승인·토큰·중복 mark는 유저가 확인 화면에서 **[네, 맞아요]**를 눌러 보내는 confirm 제출에서 일어난다. DB `status`는 여전히 `approved|rejected` 2값이다.

> 📌 결정: 실패한 인증 시도(rejected·retry)도 전부 `verifications` row로 남긴다(운영 통계·어뷰징 추적·감사 참고용). DB `status`는 **`approved|rejected` 2값**이며, 여기에 **`needs_audit BOOLEAN`**(기본 false)과 `audited_at TEXT`(감사 완료 시각, 미감사면 NULL)를 둔다. API 응답의 `retry`는 DB상 `rejected` + `reason_code`로 구분한다. 이를 위해 `verifications`에 `needs_audit INTEGER`, `audited_at TEXT`, `reason_code TEXT`, `confidence REAL`, `ocr_store_name TEXT`, `ocr_date TEXT`, `approval_number TEXT` 컬럼을 추가한다(db-schema.md 갱신 필요). 단 OCR 장애(`OCR_UNAVAILABLE`)와 4xx 입력 오류는 판정 자체가 없었으므로 row를 남기지 않는다. **`recognized`(확인 대기) 응답도 아직 승인이 확정되지 않았으므로 row를 남기지 않는다**(D-29) — row는 confirm 승인(approved) 또는 거부(rejected) 시점에만 INSERT된다. 추출 컬럼에는 D-29 확장 필드로 `biz_number TEXT`(사업자등록번호)와 `amount INTEGER`(결제 금액)를 추가한다(기존 `ocr_store_name`·`ocr_date`·`approval_number`에 더해 — db-schema.md 갱신 필요).

> 📌 결정: **감사 무효화의 표현** — 별도 `revoked` status를 추가하지 않는다. 감사에서 어뷰징 판정된 인증은 `status='rejected'` + `reason_code='REVOKED_BY_AUDIT'`로 전환한다(2값 유지). 토큰 유효성 검사는 `status='approved'`만 통과시키므로 이 전환만으로 토큰이 즉시 무효가 된다. rejected는 1일 1회 부분 유니크(VF-901 📌)에서 빠지므로, 무효화된 사용자가 정당한 영수증으로 재인증하는 것도 자연히 허용된다.

## 공통 전제

- **API 형태**
  - `POST /api/verify` — multipart(`image?`, `shop_id?`, `confirm?`) + `X-Device-Id` 헤더. 200 응답: `{ status: "recognized"|"approved"|"rejected"|"retry", recognized?, token?, reason_code?, message?, verification_id?, matched_shop_id?, shop_name? }`. `recognized`(D-29)는 확인 화면용 추출 결과 `{ shop_name, matched_shop_id, paid_at, amount, approval_tail }`(`approval_tail`은 승인번호 뒷 4자리 마스킹, `paid_at`은 시간까지 포함). `shop_name`은 approved 시 인증 상점 표시명 — 04 "{shop_name} 영수증 인증 완료" 배너용. 실패: `{ error: { code, message } }` (D-24). **`needs_audit`은 응답에 싣지 않는다** — 사용자는 감사 플래그 여부를 알 수 없다(D-05).
  - `GET /api/verify/status` — device_id 기준 당일(KST) 최신 인증 상태: `{ status: "none"|"approved"|"rejected", token?, reason_code?, verification_id?, method?, shop_name? }`. 재진입 복원용 단발 조회 — **폴링 용도가 아니다**(기다릴 상태가 없으므로). `recognized`는 미확정(row 없음)이라 이 조회에 나타나지 않는다.
- **Verifier 체인(D-03 + D-29):** `RequiredField(store.name)` → `MinAmount(최소금액, reject)` → `Confidence(0.6, review)` → `Date(당일, reject)` → `Store(사업자번호 우선 > 상호명 fuzzy, 아래 📌)` → `Duplicate(승인번호 > 이미지해시, reject)`. 집계는 reject > retry > review(`_aggregate_status`). **집계 결과가 reject/retry가 아니면(=승인 또는 review) 서버는 즉시 승인하지 않고 `status: "recognized"` + 추출 결과로 응답한다**(D-29 확인 단계). 확인 화면에서 [네, 맞아요]를 누른 confirm 제출에서 승인 트랜잭션이 실행되며, **집계가 review였으면 이때 `needs_audit=true`를 기록한다**(D-05). review는 체인 내부 개념일 뿐 API·화면에 노출되지 않는다 — 유저는 review 건도 통상 확인 화면과 동일하게 본다.

> 📌 결정: **확인 단계(recognized/confirm) 아키텍처** — 확인 화면은 서버 2단계 호출로 구현한다. **1차(인식):** `POST /api/verify`(image, confirm 없음) → 추출·체인 판정. reject/retry면 그대로 응답(확인 없이), 그 외에는 `recognized` + 추출 필드로 응답하고 **row·토큰·중복 mark 없음**. **2차(확정):** 유저가 [네, 맞아요]를 누르면 클라이언트가 **같은 image + `confirm=true`**로 재제출 → 서버는 이미지 해시 캐시로 **Gemini 재호출을 스킵**(VF-408 규약)하고 체인을 재실행 후 승인 트랜잭션(`check_and_mark` + approved row INSERT + 토큰)을 수행한다. pending row를 두지 않는 이유: "기다릴 상태 없음"(D-00) 원칙 유지 + 재제출은 해시 캐시로 사실상 무비용. 근거: 확인은 *유저 즉석 확인*이지 운영진 대기가 아니므로 무인 원칙과 무관하다.

> 📌 결정: **method 판정** — 요청에 `image`가 있으면 `photo`(이때 `shop_id`는 참고 힌트, `confirm`은 확인 단계 확정 플래그), `image` 없이 `shop_id`만 있으면 `manual`(D-04 경로 — 즉시 승인, 확인 화면 없음), 둘 다 없으면 400 `INVALID_REQUEST`. 03-verify 스펙의 "이미지 필수 여부" 미확정을 이렇게 확정한다.

> 📌 결정: **사업자등록번호 우선 매칭(D-29)** — `StoreVerifier`는 상점 매칭 시 **① OCR 추출 사업자등록번호를 참여 상점 등록번호와 정확 일치 대조**(일치하면 유사도 1.0 취급, 매칭 1순위), **② 사업자번호가 없거나 미등록이면 상호명 fuzzy로 폴백**한다. 근거: 상호명 fuzzy는 "막걸리 계보집" 같은 표기 흔들림에 약하지만 사업자번호는 불변·유일하다. 참여 상점 등록 시 `biz_number`를 함께 저장한다(db-schema.md 갱신 필요). 상호명은 확인 화면 **표시**와 보조 매칭에만 쓴다.

> 📌 결정: **최소 결제금액 정책(D-29 신설)** — `MinAmountVerifier(min_amount, severity="reject")`를 체인에 넣는다. OCR 추출 결제 금액이 **최소 결제금액(📌 5,000원 — 파트너 협의 후 확정)** 미만이면 `rejected` + `UNDER_MIN_AMOUNT`. 최소금액은 **서버 설정값**이며 **상점별 차등 가능**(상점 레코드에 override, 없으면 전역 기본값). 근거: 500원짜리 소액 결제로 좌석을 점유하는 어뷰징을 막는다. 금액을 추출하지 못한(amount=None) 경우는 다른 None 필드와 동일하게 **스킵**(모듈 None 처리 규약)하되, 금액 미추출은 대개 "못 읽음"이라 RequiredField/재촬영·manual 경로로 흡수된다.

> 📌 결정: **RequiredFieldVerifier severity** — 멈춰,섬! 체인에서는 `severity="retry"`로 조립한다(모듈 기본값 reject를 오버라이드). 상호명이 안 읽힌 것은 대개 촬영 품질 문제라 재촬영 요청이 올바른 액션이다.

> 📌 결정: **StoreVerifier 2단계 임계값** — D-03의 `Store(fuzzy 0.7, review)`를 다음과 같이 구체화한다. **먼저 사업자등록번호로 정확 매칭을 시도**(D-29 📌)해 일치하면 곧바로 통과(유사도 1.0 취급, +`metadata.matched_store`). 사업자번호가 없거나 미등록이면 상호명 fuzzy로 폴백해 최고 유사도가 **0.5 미만이면 reject(`SHOP_NOT_PARTICIPATING`)**, **0.5 이상 0.7 미만이면 review → 승인+감사 플래그(`SHOP_MATCH_UNCERTAIN`)**, 0.7 이상이면 통과. 명백한 비참여 상점까지 관용 승인하면 감사 큐가 쓰레기로 채워지고 인증제 자체가 무의미해진다 — 관용은 "경계선"에만 적용한다.

> 📌 결정: **중복 mark 시점** — `DuplicateVerifier`는 체인 단계에서 **조회만** 하고, 실제 `check_and_mark`(원자적)는 **승인(토큰 발급) 트랜잭션 안에서** 수행한다. 체인 단계에서 mark까지 해버리면 retry 판정을 받은 사용자가 같은 영수증을 재촬영해 재제출할 때 자기 자신의 이전 시도와 중복 판정되는 자기충돌이 생긴다. 감사 플래그가 붙는 승인(review 승격·manual)도 photo 경로라면 동일하게 승인 트랜잭션에서 mark한다. 중복 키는 `approval_number`가 있으면 그것, None이면 `image_hash`.

> 📌 결정: **localStorage 키** — `stop-island:verify`에 JSON `{ token?, verification_id, status, issued_date, shop_name? }` 저장(`issued_date`는 KST `YYYY-MM-DD`, `shop_name`은 04 인증 완료 배너 표시용). status는 approved|rejected만 존재한다. **단일 진실은 항상 서버(`GET /api/verify/status`)** — localStorage는 캐시일 뿐이며 불일치 시 서버 값으로 덮어쓴다. device_id는 D-07대로 `stop-island:device-id`.

---

## 1. 진입과 상태 복원

관점 커버리지: 정상 VF-101 / 경계 VF-103 / 오류 VF-105·VF-106 / 동시성 VF-107 / 복구 VF-104.

### 첫 진입

#### VF-101 최초 방문자 정상 진입
- Given: 이 브라우저로 처음 접속한 사용자 (localStorage에 `stop-island:device-id` 없음)
- When: 02 메뉴에서 "테이블 예약"을 눌러 `/verify`에 진입한다
- Then: `crypto.randomUUID()`로 device_id를 생성해 `stop-island:device-id`에 저장한다
- And: `GET /api/verify/status` 응답이 `{ status: "none" }` → 업로드 폼(empty 드롭존 + 상점 드롭다운 + 비활성 "인증하기" 버튼)을 렌더한다
- And: `GET /api/shops`로 활성 상점 목록을 받아 드롭다운 옵션을 채운다. 서버 상태 변화 없음

### 재진입 — 당일 상태별

#### VF-102 당일 approved 보유 재진입 (D-14)
- Given: 오늘(KST) approved 인증이 있고 `stop-island:verify`에 유효 토큰이 저장돼 있다
- When: `/verify`에 재진입한다
- Then: 업로드 폼 대신 **"오늘 인증 완료"** 상태를 렌더한다 — "오늘은 이미 인증을 완료했어요" 안내 + "좌석 선택으로 이동" CTA(→ `/reserve`)
- And: 서버 상태·localStorage 변화 없음. `GET /api/verify/status`로 토큰 유효성을 재확인만 한다

#### VF-103 어제 토큰이 남아 있는 재진입 (경계)
- Given: `stop-island:verify`에 `issued_date`가 어제인 approved 토큰이 남아 있다
- When: 오늘 `/verify`에 진입한다
- Then: 클라이언트가 `issued_date ≠ 오늘`로 만료를 감지하고 `stop-island:verify`를 삭제한다 (D-08: 토큰은 발급일 자정까지)
- And: `GET /api/verify/status`가 `{ status: "none" }` → 업로드 폼을 렌더한다. 오늘 다시 인증 가능(D-06 일 단위 리셋)

#### VF-104 감사 플래그 승인 보유 재진입 — 사용자 무차이 검증 (복구)
- Given: review 승격(VF-501) 또는 manual(VF-601)로 `needs_audit=true`인 approved 인증을 받은 사용자가 브라우저를 닫았다가 돌아왔다
- When: `/verify`에 재진입한다
- Then: `GET /api/verify/status`는 `{ status: "approved", token, ... }`를 반환한다 — 응답 어디에도 감사 플래그 흔적이 없고, VF-102와 **완전히 동일한** "오늘 인증 완료" 화면이 렌더된다 (D-05: 사용자는 차이를 못 느낀다)
- And: `stop-island:verify`를 서버 응답 기준으로 갱신한다. 서버 상태 변화 없음

#### VF-105 localStorage와 서버 불일치 (오류)
- Given: `stop-island:verify`에 오늘 날짜의 approved 기록이 있으나(다른 기기 데이터 이식·조작), 서버에는 이 device_id의 당일 인증이 없다
- When: `/verify`에 진입한다
- Then: `GET /api/verify/status`의 `{ status: "none" }`이 우선 — stale한 `stop-island:verify`를 삭제하고 업로드 폼을 렌더한다 (서버가 단일 진실)

#### VF-106 X-Device-Id 누락 (오류)
- Given: localStorage 접근이 차단된 환경 등으로 device_id 헤더 없이 API가 호출됐다
- When: `GET /api/verify/status` 또는 `POST /api/verify` 요청이 서버에 도착한다
- Then: 서버는 400 `{ error: { code: "DEVICE_ID_REQUIRED" } }`를 반환한다 (D-07)
- And: 화면은 일반 오류 배너("일시적인 오류예요. 새로고침 후 다시 시도해주세요")를 띄운다. 서버 row 생성 없음

#### VF-107 두 탭 동시 최초 접속 (동시성)
- Given: device_id가 없는 브라우저에서 두 탭이 거의 동시에 열렸다
- When: 두 탭이 각각 UUID를 생성해 `stop-island:device-id`에 쓴다
- Then: 나중에 쓴 값이 남고, 이후 요청은 모두 같은 device_id로 수렴한다
- And: 먼저 쓴 탭의 in-flight 조회가 다른 id로 나갔더라도 당일 기록이 없는 id의 status 조회일 뿐이라 무해하다. 서버 row 생성 없음

---

## 2. 이미지 선택과 클라이언트 검증

관점 커버리지: 정상 VF-201·VF-206·VF-207 / 경계 VF-202 / 오류 VF-203·VF-204·VF-205 / 동시성 해당 없음 — 서버·공유 자원이 개입하지 않는 로컬 단일 사용자 상호작용 / 복구 VF-208.

### 파일 선택과 미리보기

#### VF-201 JPG/PNG 선택 → 미리보기
- Given: 업로드 폼(empty) 상태
- When: 드롭존을 탭해 카메라 촬영 또는 갤러리에서 8MB JPG를 선택한다
- Then: 드롭존이 `preview` 상태로 전환 — 썸네일 + 우상단 X(삭제) 버튼 표시, "인증하기" 버튼 활성화
- And: 서버 요청 없음(파일은 메모리에만 있음). localStorage 변화 없음

#### VF-206 미리보기 삭제
- Given: preview 상태
- When: X 버튼을 탭한다
- Then: 드롭존이 empty로 복귀한다. 상점도 미선택이면 "인증하기" 버튼 비활성화. 서버·localStorage 변화 없음

#### VF-207 재업로드 교체
- Given: preview 상태
- When: 드롭존을 다시 탭해 다른 파일을 선택한다
- Then: 기존 미리보기가 새 파일로 교체된다(기존 파일 참조 폐기). 서버·localStorage 변화 없음

### 클라이언트 검증

#### VF-202 10MB 경계 (경계)
- Given: 업로드 폼 상태
- When: 정확히 10MB(10,485,760바이트) 파일과 10MB+1바이트 파일을 각각 선택한다
- Then: 10MB는 통과(preview 전환), 10MB+1은 즉시 차단 — 에러 문구 "파일이 너무 커요. 10MB 이하 사진으로 올려주세요." 서버 요청 없음, 드롭존 empty 유지

#### VF-203 허용 외 형식 (오류)
- Given: 업로드 폼 상태
- When: PDF·GIF·WebP 등 JPG/PNG 외 파일을 선택한다 (`accept` 속성을 우회한 파일 선택 포함)
- Then: MIME/시그니처 검사로 즉시 차단 — "JPG 또는 PNG 사진만 올릴 수 있어요." 서버 요청 없음

#### VF-204 HEIC — 아이폰 기본 포맷 (오류)
- Given: iOS 기본 카메라 설정(고효율/HEIC)의 사용자가 갤러리에서 사진을 고른다
- When: 파일이 HEIC로 전달된다
- Then: 클라이언트에서 차단하고 안내한다 — "지원하지 않는 사진 형식이에요(HEIC). 카메라로 다시 촬영하거나, 설정 > 카메라 > 포맷을 '높은 호환성'으로 바꿔주세요."
- And: 서버 요청 없음

> 📌 결정: **HEIC는 v1에서 변환하지 않고 거부한다.** 근거: (1) iOS Safari는 `<input type="file" accept="image/jpeg,image/png">`에 대해 HEIC를 JPEG로 자동 변환해 넘기는 것이 기본 동작이라 실제 발생률이 낮고, (2) heic2any 등 클라이언트 변환 라이브러리는 번들 크기·구형 기기 성능 비용이 커서 7일 팝업에 과설계다. 현장 테스트(Phase 5)에서 실기기 발생률이 유의미하면 그때 변환 도입을 재검토한다.

#### VF-205 0바이트·손상 파일 (오류)
- Given: 업로드 폼 상태
- When: 0바이트 파일 또는 확장자만 .jpg인 손상 파일을 선택한다
- Then: 클라이언트가 미리보기 디코딩 실패(Image load error) 또는 size 0을 감지해 차단 — "사진을 읽을 수 없어요. 다른 사진으로 다시 시도해주세요."
- And: 검증을 우회해 서버까지 도달한 경우 서버가 디코딩 실패로 400 `INVALID_IMAGE`를 반환하고 row를 남기지 않는다

### 복구

#### VF-208 파일 선택 후 새로고침
- Given: preview 상태(아직 제출 전)
- When: 페이지를 새로고침한다
- Then: 선택 파일은 메모리에만 있었으므로 소실 — empty 폼부터 다시 시작한다
- And: 서버에 아무 기록이 없으므로 잃는 것은 파일 재선택 몇 초뿐. 의도된 트레이드오프(파일을 로컬 저장하지 않음)

---

## 3. OCR 제출 — 인식·확인·승인 (해피 패스)

관점 커버리지: 정상 VF-301·VF-302 / 분기 VF-303 / 경계 VF-304 / 오류 — 해당 없음(오류 분기는 영역 4·7이 전담) / 동시성 — 영역 9 전담 / 복구 VF-305·VF-306.

#### VF-301 정상 인식 → "이거 맞아요?" 확인 화면 (recognized) (정상)
- Given: 참여 상점의 당일 영수증 JPG가 preview 상태
- When: "인증하기"를 탭한다
- Then: 버튼이 로딩 상태(중복 클릭 방지 disable)로 전환되고 `POST /api/verify`(multipart, `confirm` 없음)가 전송된다
- And: 서버 — 이미지를 디스크에 저장(D-23), ReceiptEngine 실행, **사업자번호로 상점 매칭 + 결제 일시·금액·승인번호 추출**(D-29), 전 Verifier가 reject/retry 없이 통과 → **승인·토큰 발급을 미루고** `{ status: "recognized", recognized: { shop_name, matched_shop_id, paid_at: "오늘 14:32", amount: "8,000원", approval_tail: "****1234" } }`로 응답. **row·토큰 없음**(확인 단계 📌)
- And: 화면 — 읽은 정보를 표로 표시한다: **가게(상호명) · 결제 일시(시간까지) · 결제 금액 · 승인번호 뒷자리** + **[네, 맞아요 · 인증하기]** / **[아니요, 직접 선택할게요]**. localStorage 변화 없음

#### VF-302 [네, 맞아요] 확정 → 토큰 발급 → 04 자동 이동 (정상)
- Given: VF-301의 확인 화면 (recognized `matched_shop_id`·image 보유)
- When: "네, 맞아요 · 인증하기"를 탭한다
- Then: 같은 image + `confirm=true`로 `POST /api/verify` 재제출 → 서버는 이미지 해시 캐시로 **Gemini 재호출 스킵**(VF-408), 체인 재실행 후 승인 트랜잭션에서 `check_and_mark`(승인번호) 성공 → row `{ status: 'approved', method: 'photo', needs_audit: 0, token: UUID, verified_at, reason_code: null, matched_shop_id, amount, approval_number }` INSERT
- And: 응답 `{ status: "approved", token, verification_id, shop_name }` 수신 → `stop-island:verify`에 `{ token, verification_id, status: "approved", issued_date: 오늘, shop_name }` 저장 → 04 좌석 선택(`/reserve`)으로 자동 이동. 당일 방문 수(D-20) +1

#### VF-303 [아니요, 직접 선택할게요] → manual 전환 (분기)
- Given: VF-301의 확인 화면 (OCR이 읽은 가게가 실제와 다르다고 유저가 판단)
- When: "아니요, 직접 선택할게요"를 탭한다
- Then: 확인 화면을 닫고 **상점 직접 선택 UI**(영역 6, "결제한 참여 상점을 골라주세요")로 전환한다. 서버 요청 없음(confirm 미전송이므로 recognized 결과는 그냥 폐기 — row 없음)
- And: 이후 선택→인증은 manual 경로(VF-601 — 즉시 승인 + `needs_audit`)를 탄다. photo 확정을 하지 않았으므로 이미지 기반 승인 기록은 남지 않는다

#### VF-304 shop_id 힌트와 함께 제출 — 사업자번호 매칭 우선 (경계)
- Given: 사용자가 이미지 업로드 + 드롭다운에서 상점 A도 선택해 둔 상태 (와이어프레임상 두 입력은 상호 배타 아님)
- When: 제출하고, OCR이 사업자번호로 상점 B를 매칭(또는 상호명 fuzzy ≥ 0.7)한다
- Then: **서버 판정은 OCR 매칭이 우선** — 확인 화면의 가게는 상점 B로 표시되고, [네, 맞아요] 확정 시 row의 `shop_id`에는 B를 기록. 사용자가 보낸 A는 부가 정보로만 로깅한다
- And: 사용자 선택이 판정을 바꾸지 않으므로 어뷰징(허위 상점 지정) 여지가 없다. 표시된 가게가 틀렸으면 유저는 [아니요]로 manual 전환(VF-303)

> 📌 결정: **shop_id 우선순위** — photo 경로에서 요청의 `shop_id`는 판정에 영향을 주지 않는 힌트다(기록·감사 참고용). 판정·확인 화면 표시는 항상 OCR StoreVerifier 결과(사업자번호 우선)를 따른다. `shop_id`가 판정을 결정하는 것은 image가 없는 manual 경로뿐이다. 근거: 사용자 선택을 신뢰하면 영수증 인증제가 무의미해진다(D-04와 같은 논리 — manual조차 감사 플래그를 남긴다).

#### VF-305 확인 화면 표시 중 새로고침 (복구)
- Given: VF-301의 recognized 확인 화면 상태 (아직 confirm 미전송 — 서버에 row 없음)
- When: 페이지를 새로고침한다
- Then: recognized 결과는 응답으로만 있었으므로 소실, 선택 파일도 메모리에서 소실(VF-208) → empty 폼부터 다시 시작
- And: `GET /api/verify/status`는 `{ status: "none" }`(승인 확정 전이라 row 없음) → 서버 상태 변화 없음. 잃는 것은 재촬영·재인식 몇 초뿐(의도된 트레이드오프)

#### VF-306 confirm 확정 응답 수신 직전 새로고침 (복구)
- Given: [네, 맞아요] confirm 제출 후 서버는 approved 처리를 완료했으나, 응답 수신 전에 사용자가 새로고침·이탈했다 (localStorage 미저장)
- When: `/verify`에 재진입한다
- Then: `GET /api/verify/status`가 `{ status: "approved", token, verification_id }` → 토큰을 `stop-island:verify`에 복원 저장하고 "오늘 인증 완료" 상태(VF-102)를 렌더한다
- And: 서버 상태는 이미 approved로 확정돼 있으므로 변화 없음. 토큰 유실 구멍 없음(status API가 복원의 단일 창구)

---

## 4. OCR 제출 — rejected / retry

관점 커버리지: 정상(각 사유의 정상 판정) VF-401~VF-406·VF-410 / 경계 VF-407·VF-408 / 오류 — 이 영역 전체가 오류 판정 자체 / 동시성 — 영역 9 전담 / 복구 — 실패는 서버에 부작용 있는 상태를 남기지 않으므로(row는 rejected로 종결) 새로고침 후 폼 재시작이 곧 복구(VF-208·VF-104 메커니즘 준용).

공통 Then(rejected — 당일 아님·미참여·중복·금액 미달): 응답 `{ status: "rejected", reason_code, message, verification_id }` 수신 → **확인 화면 없이 즉시** 에러 배너를 드롭존 하단에 표시(D-29 — 확인 단계는 승인 후보에만 붙는다), **이미지 preview는 유지**(재제출 편의), "인증하기" 버튼 재활성화. 서버 — row `{ status: 'rejected', reason_code }` 종결. localStorage — `stop-island:verify` 변화 없음(실패는 저장하지 않음).

공통 Then(retry — 못 읽음: 영수증 아님·필수 필드 결손): 응답 `{ status: "retry", reason_code, message, verification_id }` 수신 → 안내 문구와 함께 **상점 직접 선택 UI(영역 6)로 유도**한다(D-29 — "영수증을 잘 못 읽었어요. 결제한 참여 상점을 골라주세요"). 재촬영도 여전히 가능(뒤로/다른 사진). 서버 — row `{ status: 'rejected', reason_code }` 종결(응답 status만 retry — 서두 📌).

### rejected — 자동 거부

#### VF-401 당일 아님 (DateVerifier)
- Given: 어제 날짜(2026-09-29)의 참여 상점 영수증
- When: 제출한다
- Then: `DateVerifier(max_age_days=0)` 실패(severity reject) → `rejected` + `NOT_TODAY`, 문구 "오늘 결제한 영수증만 인정돼요. (영수증 날짜: 2026-09-29)"
- And: 판정 기준일은 서버의 KST 오늘(D-01). 클라이언트 시계와 무관

#### VF-402 미참여 상점 (StoreVerifier 명백 불일치)
- Given: 행궁동 밖 프랜차이즈 카페의 당일 영수증 (허용 목록 대비 최고 유사도 0.2)
- When: 제출한다
- Then: 유사도 < 0.5 → `rejected` + `SHOP_NOT_PARTICIPATING`, 문구 표시 + 화면에 참여 상점 목록 링크(02 화면) 노출

#### VF-403 중복 영수증 — 승인번호 매칭
- Given: 다른 사용자가 이미 오늘 승인받은 영수증을, 다른 각도로 찍은 사진(이미지 해시 다름, 승인번호 동일)
- When: 제출한다
- Then: 다른 Verifier는 통과하지만 승인 트랜잭션의 `check_and_mark(approval_number)`가 기존 키 존재로 False → `rejected` + `DUPLICATE_RECEIPT`, "이미 사용된 영수증이에요."
- And: 이미지 해시가 달라도 잡힌다 — 승인번호가 해시보다 우선하는 이유(각도·조명 불변)

#### VF-404 중복 영수증 — 이미지 해시 매칭 (승인번호 None)
- Given: OCR이 승인번호를 추출하지 못한(approval_number=None) 영수증이 이미 승인됐고, **같은 이미지 파일**이 다시 제출된다
- When: 제출한다
- Then: 승인번호가 None이므로 중복 키는 `image_hash`로 폴백 → `check_and_mark(image_hash)` False → `rejected` + `DUPLICATE_RECEIPT`
- And: 한계를 명시한다 — 승인번호 None인 영수증을 **다시 찍은 다른 사진**은 해시가 달라 통과할 수 있다. 규모(좌석 6개·7일)상 수용하고 원격 사후감사(D-22)로 보완(SYS 어뷰징 참조)

#### VF-410 금액 미달 (MinAmountVerifier, D-29 신설)
- Given: 참여 상점의 당일 영수증이지만 결제 금액이 최소 결제금액(📌 5,000원) 미만 (예: 아메리카노 500원 이벤트 결제)
- When: 제출한다
- Then: `MinAmountVerifier` 실패(severity reject) → **확인 화면 없이** `rejected` + `UNDER_MIN_AMOUNT`, 문구 "최소 결제금액(5,000원) 이상 영수증만 인정돼요."
- And: 최소금액은 서버 설정값이며 상점별 차등 가능(공통 전제 📌). 금액을 아예 못 읽은 경우(amount=None)는 이 Verifier를 스킵하고 못 읽음(retry→manual) 경로로 흡수된다

#### VF-407 복수 실패 혼합 — 집계 우선순위 (경계)
- Given: 어제 날짜(reject 사유)이면서 confidence 0.4(review 사유)이고 금액도 미달(reject 사유)인 영수증
- When: 제출한다
- Then: `_aggregate_status` 우선순위 reject > retry > review에 따라 최종 `rejected` + 대표 reject 사유(`NOT_TODAY` 또는 `UNDER_MIN_AMOUNT`) 하나만 표시 — **review 사유가 섞여 있어도 관용 승인(D-05)·확인 화면으로 빠지지 않는다**(확인 화면은 reject·retry 사유가 하나도 없을 때만)
- And: row에는 대표 reason_code를 기록하고, 전체 실패 목록은 서버 로그로만 남긴다

### retry — 못 읽음 → 상점 직접 선택 (D-29)

#### VF-405 영수증 아님 (NotReceiptError)
- Given: 셀카 등 영수증이 아닌 이미지
- When: 제출한다
- Then: Extractor가 `is_receipt=false` → `NotReceiptError`를 **재시도 없이 즉시** 발생(설계 문서 규약) → `retry` + `NOT_RECEIPT`, "영수증 사진이 아닌 것 같아요. 영수증이 잘 보이게 다시 찍어주세요."
- And: Gemini 재호출 낭비 없음. row는 `rejected` + `NOT_RECEIPT`로 저장(응답 status만 retry — 서두 📌 참조). 화면은 재촬영 안내 + **상점 직접 선택 UI 유도**(retry 공통 Then, D-29) — 영수증이 아니어도 유저가 결제 상점을 직접 골라 manual로 인증할 길을 연다(manual은 전건 감사 — D-04)

#### VF-406 필수 필드 결손 → 상점 직접 선택 (RequiredFieldVerifier)
- Given: 심하게 구겨져 상호명이 안 읽히는 영수증 (`store.name=None`)
- When: 제출한다
- Then: `RequiredFieldVerifier(store.name, severity="retry")` 실패 → `retry` + `MISSING_REQUIRED_FIELD` → 화면은 "영수증을 잘 못 읽었어요. 결제한 참여 상점을 골라주세요"와 함께 **상점 직접 선택 UI로 전환**(D-29 — 인식 실패의 주 복구 경로는 재촬영이 아니라 manual 선택)
- And: 이후 DateVerifier 등은 None 필드를 스킵(모듈의 None 처리 규약)하므로 엉뚱한 사유가 덧붙지 않는다. 유저가 상점을 고르면 VF-601(manual 즉시 승인 + `needs_audit`)로 합류

### 캐시·반복

#### VF-408 이미지 해시 캐시 히트 — 같은 이미지 재제출 (경계)
- Given: 방금 `NOT_TODAY`로 거부된 영수증 이미지를 사용자가 그대로 다시 제출한다
- When: 서버가 `hash_image()`로 캐시를 조회한다
- Then: 캐시 히트 → **Gemini 호출 스킵**(비용 0), 캐시된 ReceiptData로 **Verifier 체인은 다시 실행** → 같은 `rejected` + `NOT_TODAY`가 즉시 반환된다
- And: 새 row가 하나 더 남는다(시도 이력). "캐시 히트 = 추출 스킵이지 검증 스킵이 아님"(설계 문서 규약 — 허용 상점 목록이 요청 간 바뀔 수 있으므로)

#### VF-409 실패 후 재시도 무제한
- Given: 오늘 이미 rejected/retry를 4번 받은 사용자
- When: 5번째로 올바른 영수증을 제출한다
- Then: 횟수 제한 없이 정상 판정된다(D-06 — 실패 재시도 무제한) → 통과 시 VF-301→VF-302 흐름(확인 화면→confirm)으로 approved
- And: 서버에는 rejected row 4건 + approved row 1건이 남는다 (부분 유니크는 approved에만 걸리므로 rejected 다건 허용 — VF-901 📌 참조)

---

## 5. 관용 승인(needs_audit)과 사후감사 (D-05·D-22)

관점 커버리지: 정상 VF-501·VF-503 / 경계 VF-502(fuzzy 경계선이 곧 경계값 시나리오) / 오류 VF-504(감사 무효화) / 동시성 — 무효화와 사용자 액션의 경합은 VF-903, 두 운영진의 동시 감사는 ADM 문서 / 복구 VF-505.

#### VF-501 confidence 미달 → 확인 화면 → 승인 + 감사 플래그
- Given: 흐릿하게 찍혀 confidence 0.45로 추출된 참여 상점 당일 영수증
- When: 제출한다
- Then: `ConfidenceVerifier(0.6)` 실패(severity review), reject/retry 사유 없음 → 집계 review → **서버는 즉시 승인하지 않고 `recognized` 확인 화면**(VF-301)을 그린다 — review도 "확인 후보"라 통상 승인 후보와 동일하게 확인 단계를 탄다(오히려 확인 화면이 저신뢰 OCR 오독을 유저가 잡아주는 안전망이 된다)
- And: 유저가 [네, 맞아요]로 confirm하면 승인 트랜잭션에서 `check_and_mark` 수행 후 row `{ status: 'approved', method: 'photo', needs_audit: 1, reason_code: 'LOW_CONFIDENCE', confidence: 0.45, token }` INSERT. 이미지 원본 보존(감사 큐에서 표시 — D-22)
- And: 화면·응답·localStorage — **VF-301/302와 완전히 동일.** "확인 중" 운영진 대기 화면·폴링은 존재하지 않고(D-05), 사용자는 감사 플래그를 인지할 수 없다

#### VF-502 fuzzy 경계선 → 확인 화면 → 승인 + 감사 플래그 (경계)
- Given: 사업자번호가 안 읽혀 상호명 fuzzy로 폴백, OCR 상호명 "막걸리 계보집" — 허용 목록 "막걸리계보"와 유사도 0.62 (0.5 이상 0.7 미만)
- When: 제출한다
- Then: StoreVerifier 2단계 📌에 따라 review → `recognized` 확인 화면(후보 상점 "막걸리계보"를 가게로 표시) → [네, 맞아요] confirm 시 approved + `needs_audit=1` + `SHOP_MATCH_UNCERTAIN`. 사용자 경험은 통상 승인과 무차이
- And: 표시된 가게가 틀렸으면 유저가 [아니요]로 manual 전환(VF-303)해 스스로 교정할 수 있다. row에 후보 상점(`metadata.matched_store`)을 함께 기록해 감사 큐에서 운영진 판단을 돕는다. 토큰·예약은 후보 상점 기준으로 정상 동작

#### VF-503 감사 플래그 승인으로 예약까지 진행 (정상)
- Given: VF-501/502로 `needs_audit=1` 토큰을 받은 사용자
- When: 04 좌석 선택 → 예약 확정까지 진행한다
- Then: 감사 플래그는 어떤 API에서도 제약이 아니다 — 좌석 선택·예약 확정·완료 화면 전부 통상 승인과 동일하게 동작한다 (감사는 사후 절차일 뿐)
- And: 운영진이 감사 큐에서 "문제없음" 처리(ADM-211)하면 `needs_audit=0`으로 종결 — 사용자에게는 처음부터 끝까지 아무 일도 없다

#### VF-504 사후감사 어뷰징 판정 — 인증 무효화 + 예약 해제 (오류)
- Given: `needs_audit=1`로 승인된 인증(예: manual 허위 선택 의심)을 원격 운영진이 감사 큐에서 어뷰징으로 판정했다. 해당 사용자는 active 예약을 보유 중이다
- When: 운영진이 "어뷰징 — 무효화"를 확정한다 (ADM-212)
- Then: 서버 — 단일 트랜잭션으로 ① verification을 `{ status: 'rejected', reason_code: 'REVOKED_BY_AUDIT', audited_at }`로 전환(토큰 즉시 무효 — 서두 📌) ② 이 인증에 연결된 active 예약을 `cancelled`로 해제(좌석 즉시 회수)
- And: 사용자에게 푸시·알림은 없다(웹) — **다음 조회 때 알게 된다**: 예약 완료 화면 재조회 시 "예약이 취소되었어요"(04 RSV-608), `/verify` 재진입 시 VF-505
- And: 04 좌석 폴링을 보던 다른 사용자에게는 회수된 좌석이 빈자리로 나타난다

#### VF-505 무효화 이후 재진입 (복구)
- Given: VF-504로 인증이 무효화된 사용자 (localStorage에는 stale approved 토큰이 남아 있다)
- When: `/verify`에 재진입하거나, `/reserve` 진입·예약 시도로 서버 검증에 걸린다
- Then: `GET /api/verify/status`가 `{ status: "rejected", reason_code: "REVOKED_BY_AUDIT" }` → stale `stop-island:verify` 삭제, 업로드 폼 + 배너 "운영진 확인 결과 인증이 취소되었어요. 다시 인증해주세요"
- And: rejected는 1일 1회 유니크에서 빠지므로(서두 📌) 정당한 영수증으로 즉시 재인증 가능 — 무효화는 차단이 아니라 되돌림이다. 반복 어뷰징은 SYS-5xx의 수용선·감사 반복으로 대응

---

## 6. 상점 직접 선택 — manual 경로 (D-04)

관점 커버리지: 정상 VF-601 / 경계 VF-602(중복 방어 한계)·VF-605(프리필 우선순위) / 오류 VF-604 / 동시성 — 영역 9 전담 / 복구 VF-603.

> 📌 결정: **manual 승인의 기록 규약** — manual 제출은 항상 `{ status: 'approved', method: 'manual', needs_audit: 1, reason_code: 'MANUAL_SHOP_SELECTED', shop_id, image_url: null }`로 저장한다. 영수증 증빙이 없는 승인이므로 **전건 감사 대상**이다. 승인번호·이미지가 없어 중복 mark는 수행하지 않는다 — manual 남용의 방어선은 중복 검사가 아니라 1일 1회 유니크(D-06) + 사후감사(D-22)다.

> manual 진입 경로(D-29): ① 확인 화면에서 [아니요, 직접 선택할게요](VF-303) ② 못 읽음 retry(VF-405/406) ③ OCR 장애(VF-701) ④ 처음부터 이미지 없이 상점만 선택. 어느 경로든 아래 VF-601로 합류한다 — manual에는 확인 화면(recognized)이 없다(대조할 OCR 추출 정보가 없으므로).

#### VF-601 상점 선택 제출 → 즉시 승인 → 04 이동
- Given: 이미지 없이 드롭다운에서 "막걸리계보"를 선택한 상태 ("인증하기"/"이 상점으로 인증" 버튼은 이미지 또는 상점 중 하나만 있어도 활성)
- When: "이 상점으로 인증"을 탭한다
- Then: `POST /api/verify`(shop_id만, image·confirm 없음) → method 판정 📌에 따라 manual → **즉시 approved + `needs_audit=1`** (D-04, 위 📌 규약), 토큰 발급 (확인 화면 없음)
- And: 응답·화면·localStorage — VF-302와 동일: 토큰 저장 후 04 좌석 선택으로 자동 이동. 기다림·안내 화면 없음 (무인 운영 — D-00)
- And: 당일 방문 수(D-20)에 +1. 운영진은 원격 감사 큐에서 사후 확인한다(ADM-2xx)

#### VF-602 manual의 중복 방어 부재 — 한계 명시 (경계)
- Given: 사용자가 영수증 없이 manual로 승인받았다 (승인번호·이미지 해시 없음)
- When: 다른 기기(다른 device_id)에서 같은 상점을 manual로 또 제출한다
- Then: 중복 mark 대상이 없으므로 그 기기 기준으로도 승인된다 — **manual은 영수증 단 중복 방어가 구조적으로 불가능하다**
- And: 방어는 ① device_id당 1일 1회 유니크(VF-901 📌) ② 전건 감사 플래그(위 📌)로 대신한다. 다중 기기 어뷰징의 수용선은 SYS-501·SYS-505 참조

#### VF-603 manual 승인 직후 이탈·재진입 (복구)
- Given: manual 제출 직후 응답 수신 전에 브라우저를 닫았다 (localStorage 미저장)
- When: `/verify`에 재진입한다
- Then: `GET /api/verify/status`가 `{ status: "approved", token, method: "manual" }` → 토큰 복원 저장 후 "오늘 인증 완료" 상태(VF-102) 렌더 — VF-306과 동일 메커니즘
- And: 서버 상태 변화 없음. 유실 구멍 없음

#### VF-604 이미지도 상점도 없이 제출 시도 (오류)
- Given: empty 폼 상태
- When: "인증하기" 영역을 탭한다
- Then: 버튼이 비활성이라 요청이 나가지 않는다 + 헬퍼 텍스트 "영수증 사진을 올리거나 상점을 선택해주세요"
- And: 비활성을 우회해 요청이 서버에 도달하면 400 `INVALID_REQUEST` (row 없음). 존재하지 않거나 비활성(`is_active=false`) shop_id도 동일하게 400

#### VF-605 matched_shop_id 프리필과 사용자 선택 우선순위 (경계)
- Given: 직전 photo 제출이 실패(retry/rejected)했고 응답에 `matched_shop_id`(OCR이 특정한 상점)가 있었다
- When: 폼으로 복귀해 드롭다운을 렌더한다
- Then: 사용자가 아직 드롭다운을 건드리지 않았다면 `matched_shop_id`로 **자동 프리필**한다
- And: 사용자가 이미 직접 선택해 둔 값이 있으면 **덮어쓰지 않는다** (사용자 조작 이후에는 프리필 비활성)

> 📌 결정: **프리필 우선순위** — 클라이언트 UI에서는 "사용자가 드롭다운을 한 번이라도 직접 조작했는가" 플래그로 판단해, 조작 전에는 OCR `matched_shop_id` 프리필을 적용하고 조작 후에는 절대 덮어쓰지 않는다. 서버 판정에서는 반대로 OCR 매칭이 항상 우선(VF-304 📌)이므로, 이 프리필은 manual 폴백 제출의 편의 기능일 뿐 판정 로직과 무관하다.

---

## 7. OCR 장애 폴백 (D-25)과 네트워크 복구

관점 커버리지: 정상 VF-703(장애 해소 후 정상 복귀) / 경계 VF-702 / 오류 VF-701·VF-704 / 동시성 해당 없음 — 장애 국면은 단일 요청 관점이며 동시 제출 경합은 영역 9가 전담 / 복구 VF-704·VF-705.

#### VF-701 Gemini 타임아웃·5xx — 재시도 소진 (오류)
- Given: Gemini API가 장애 중 (요청당 timeout 15초, 지수 백오프 재시도 3회 — 설계 문서 기본값)
- When: photo 제출의 extract가 재시도를 전부 소진하고 `ExtractionError`로 실패한다
- Then: 서버는 503 `{ error: { code: "OCR_UNAVAILABLE", message: "사진 인증이 지금 어려워요. 아래에서 상점을 직접 선택해주세요." } }` 반환, **row를 남기지 않는다**(판정 자체가 없었음)
- And: 화면 — 에러 배너와 함께 **상점 직접 선택 섹션을 강조**(스크롤·포커스 이동)해 manual 경로(영역 6 — 즉시 승인)로 유도 (D-25). 장애 중에도 사용자 플로우는 사람 개입 없이 완결된다(D-00)
- And: localStorage 변화 없음. 클라이언트 fetch 타임아웃은 서버 최악 처리시간(재시도 포함 약 50초+)을 고려해 90초로 설정

> 📌 결정: `POST /api/verify`의 클라이언트 fetch 타임아웃은 **90초**. Gemini 경로 최악 소요(15초 × 3회 + 백오프)를 덮되, 그 이상은 사용자를 세워두지 않고 네트워크 오류 처리(VF-704)로 합류시킨다.

#### VF-702 Gemini 429 rate limit (경계)
- Given: 순간 트래픽으로 Gemini가 429를 반환 (`RateLimitError`, `max_concurrency=5` 세마포어로 1차 완화)
- When: 백오프 재시도까지 소진된다
- Then: VF-701과 동일하게 503 `OCR_UNAVAILABLE` + manual 안내. 재시도로 회복된 경우에는 사용자 모르게 정상 판정(응답이 몇 초 늦을 뿐)

#### VF-703 장애 해소 후 photo 경로 복귀 (정상)
- Given: VF-701에서 manual 안내를 받았지만 제출하지 않고 기다린 사용자, Gemini 장애 해소됨
- When: 같은 이미지를 다시 "인증하기"로 제출한다
- Then: 클라이언트는 장애 상태를 고정하지 않으므로 그대로 photo 경로로 재시도 → 정상 판정 흐름(영역 3~5) 진행
- And: 장애 중 이미 manual로 승인받아 둔 경우라면 photo 재제출은 409 `ALREADY_VERIFIED_TODAY`(VF-801)

#### VF-704 제출 중 네트워크 단절 (오류·복구)
- Given: 업로드 진행 중 지하·터널 등에서 연결이 끊겼다
- When: fetch가 네트워크 오류로 실패한다
- Then: 화면 — "네트워크 연결을 확인해주세요" 배너 + "다시 시도" 버튼, preview 유지. localStorage 변화 없음
- And: 서버가 요청을 이미 수신·처리했을 가능성이 있으므로, "다시 시도"는 안전하다 — 같은 이미지는 해시 캐시로 Gemini 재호출이 스킵되고(VF-408), 이미 approved가 됐다면 409 `ALREADY_VERIFIED_TODAY`를 받아 `GET /api/verify/status` 재조회로 화면을 동기화한다

#### VF-705 업로드 중 새로고침 (복구)
- Given: `POST /api/verify` 요청이 진행 중
- When: 사용자가 새로고침한다
- Then: 요청은 브라우저에서 중단되지만 서버 처리는 계속될 수 있다 → 재진입 시 `GET /api/verify/status`가 결과를 알려준다: approved면 VF-306(토큰 복원), rejected면 폼 + 사유 배너, 서버가 처리 전에 연결이 끊겨 아무 일도 없었으면 `none` → 폼부터 재시작
- And: 어느 경로든 이중 발급·유실 없음 — status API가 복원의 단일 창구

---

## 8. 1일 1회 제한(D-06)과 날짜 경계(D-01·D-08)

관점 커버리지: 정상 VF-803 / 경계 VF-804·VF-805·VF-806(자정 경계) / 오류 VF-801·VF-802 / 동시성 — 영역 9 전담 / 복구 VF-805(만료 토큰 자가 복구).

#### VF-801 당일 approved 보유 중 재제출 (오류)
- Given: 오늘 approved 토큰을 보유한 사용자 (정상 UI에서는 폼이 안 보이지만, 뒤로가기 캐시된 폼·API 직접 호출로 제출 가능)
- When: `POST /api/verify`가 도착한다
- Then: 서버는 판정 시작 전에 당일 approved 존재를 확인하고 409 `{ error: { code: "ALREADY_VERIFIED_TODAY" } }` 반환 (새 row 없음, Gemini 호출 없음). 감사 플래그 승인(needs_audit=1)도 approved이므로 동일하게 걸린다
- And: 화면 — 문구 표시 후 `GET /api/verify/status`로 동기화해 "오늘 인증 완료" 상태(VF-102)로 전환, 토큰을 localStorage에 복원

#### VF-802 감사 무효화 이후 재인증 (오류→정상 복귀)
- Given: 오늘 approved였던 인증이 감사에서 `REVOKED_BY_AUDIT`로 무효화됐다(VF-504)
- When: 사용자가 정당한 영수증으로 다시 `POST /api/verify`를 제출한다
- Then: 무효화된 row는 `rejected`라 1일 1회 부분 유니크에서 빠져 있으므로(서두 📌) 재제출이 차단되지 않고 정상 판정된다 — 통과 시 새 approved row + 새 토큰
- And: 서버에는 revoked row와 새 approved row가 공존한다(이력 보존). 새 승인이 또 review성/manual이면 다시 감사 플래그가 붙는다 — 반복 어뷰징 대응은 감사 큐에서

#### VF-803 어제 approved, 오늘 재인증 (정상·경계)
- Given: 어제 인증·이용을 마친 사용자
- When: 오늘(KST 00:00 이후) `/verify`에 진입해 오늘 영수증을 제출한다
- Then: 1일 1회 카운터는 KST 자정에 리셋(D-01) → 정상 판정, 새 approved row + 새 토큰. 어제 row는 그대로 보존

#### VF-804 자정 직전 제출 → 자정 직후 판정 (경계)
- Given: 23:59:50에 오늘(9/30) 날짜 영수증을 제출했고, OCR 처리가 길어져 판정이 00:00:40(10/1)에 이뤄진다
- When: DateVerifier가 실행된다
- Then: 기준일은 **판정 시각의 KST 오늘(10/1)** → 영수증 날짜 9/30은 `rejected` + `NOT_TODAY`
- And: 화면에는 통상 문구 + 상점 직접 선택 유도(즉시 승인되는 자가 구제 경로 — D-04). row는 10/1자 rejected

> 📌 결정: **자정 경계 완화 없음.** DateVerifier의 기준일은 항상 판정 시각의 KST 오늘이며, 자정을 넘겨 판정된 전날 영수증은 원칙대로 거부한다. 유예 창(예: 00:00~00:10 review 전환)은 코드 복잡도 대비 실익이 없다 — 팝업 운영시간 특성상 자정 부근 제출 자체가 희귀하고, 발생해도 manual 경로(즉시 승인+감사 플래그)로 사용자가 스스로 구제할 수 있다.

#### VF-805 자정 직전 발급된 토큰을 자정 이후 수신 (경계·복구)
- Given: 서버가 23:59:58에 approved 판정·토큰 발급(row의 `issued_date`=9/30), 클라이언트는 00:00:05에 응답을 수신했다
- When: 클라이언트가 토큰을 저장하고 04로 이동하거나, 이후 `/verify`·`/reserve`에 진입한다
- Then: 토큰은 발급일(9/30) 자정에 이미 만료(D-08) — `/reserve`의 D-14 가드 또는 예약 API가 `TOKEN_EXPIRED`로 거부하고 `/verify`로 돌려보낸다
- And: `/verify`는 `issued_date ≠ 오늘`로 stale 토큰을 삭제(VF-103)하고 폼을 렌더 — 10/1 카운터는 리셋 상태라 즉시 재인증 가능. 사용자 피해는 재인증 1회로 수렴

#### VF-806 감사 플래그가 자정을 넘김 (경계)
- Given: 9/30 저녁의 `needs_audit=1` 승인 건을 운영진이 감사하지 못한 채 10/1이 됐다. 해당 토큰은 자정에 자연 만료됐고 예약도 2시간 만료로 종결됐다
- When: 10/1에 운영진이 뒤늦게 감사한다
- Then: "문제없음" 처리는 평소와 동일(`needs_audit=0`). "어뷰징" 판정도 그대로 수행 가능 — row는 `REVOKED_BY_AUDIT`로 전환되지만 토큰·예약이 이미 소멸한 뒤라 **기록·통계 목적**이며 사용자 영향은 없다(해제할 active 예약이 없으면 그 단계는 no-op)
- And: 사용자가 10/1에 재진입하면 어느 쪽이든 `{ status: "none" }`(당일 기준 조회) → 새 폼, 새로 인증 가능. 감사 지연이 사용자를 막는 경로는 존재하지 않는다

---

## 9. 동시성과 중복 경합

관점 커버리지: 이 영역은 동시성 관점 전담(VF-901~VF-903). 정상·경계·오류·복구 관점은 각 기능 영역(3~8)에서 커버됨 — 해당 없음.

#### VF-901 같은 device 두 탭 동시 제출
- Given: 같은 브라우저의 두 탭이 각각 폼을 열고 거의 동시에 "인증하기"를 눌렀다 (같은 device_id)
- When: 두 `POST /api/verify`가 각각 판정을 진행하고 거의 동시에 승인 트랜잭션(approved row INSERT)에 도달한다
- Then: 부분 유니크 인덱스(아래 📌)가 원자적으로 한쪽만 통과시킨다 — 탭 A는 approved + 토큰 발급, 탭 B는 INSERT 실패를 잡아 409 `ALREADY_VERIFIED_TODAY`
- And: 탭 B 화면은 문구 표시 후 `GET /api/verify/status` 재조회 → 탭 A의 결과("오늘 인증 완료" + 토큰 복원)로 동기화. localStorage는 마지막 갱신 값으로 수렴하며 두 탭 모두 같은 토큰을 보게 된다

> 📌 결정: **제출 직렬화 방식** — pending 선삽입은 없다(recognized 확인 대기도 row가 없다 — 서두 📌). `POST /api/verify`는 판정을 끝까지 수행한 뒤 **승인 시점(photo는 confirm 제출, manual은 즉시)** 에 approved row를 INSERT하며, `verifications`에 **부분 유니크 인덱스** `UNIQUE(device_id, date(created_at, 'localtime')) WHERE status = 'approved'`를 건다. 이 INSERT가 동시 제출의 원자적 관문이다 — 동시 요청이 둘 다 판정(Gemini 호출)까지 진행하는 낭비는 있지만, 같은 이미지면 해시 캐시로 상쇄되고 다른 이미지의 진짜 동시 제출은 희귀해 수용한다. rejected는 유니크에서 빠지므로 실패 재시도 무제한(D-06)·감사 무효화 후 재인증(VF-802)이 성립한다. db-schema.md의 무조건부 `one_per_device_per_day` UNIQUE는 이 부분 유니크로 교체한다 — db-schema.md 갱신 필요.

#### VF-902 같은 영수증, 다른 device 동시 제출
- Given: 일행 두 명이 같은 영수증을 각자 폰으로 찍어 거의 동시에 제출했다 (승인번호 동일, device_id 다름)
- When: 두 요청 모두 Verifier 체인을 통과하고 동시에 승인 트랜잭션에 진입한다
- Then: `DuplicateStore.check_and_mark(approval_number)`의 원자성(SQLite UNIQUE 제약 + INSERT 실패 캐치 — 설계 문서 규약)이 정확히 한쪽만 True → A는 approved + 토큰, B는 `rejected` + `DUPLICATE_RECEIPT`
- And: exists()+save() 분리 구현이 아닌 단일 원자 연산이므로 "둘 다 통과" race가 구조적으로 불가능. B의 row는 rejected로 종결, B 화면은 "이미 사용된 영수증이에요" 표시

#### VF-903 감사 무효화와 사용자 예약 액션의 경합
- Given: `needs_audit=1` 승인 사용자가 좌석 선택 중이고, 같은 순간 원격 운영진이 이 인증을 어뷰징으로 무효화한다(VF-504)
- When: 무효화 트랜잭션 커밋과 사용자의 `POST /api/reserve`가 교차한다
- Then: 무효화가 먼저 커밋되면 예약 API의 토큰 검증(`status='approved'`)이 실패 → 401 `TOKEN_EXPIRED` → `/verify`로 이동, VF-505 흐름으로 합류
- And: 예약이 먼저 커밋되면 그 예약은 일단 생성되지만, 무효화 트랜잭션이 "이 인증에 연결된 active 예약 해제"를 포함하므로(VF-504) 직후 cancelled로 해제된다 — **어느 순서든 최종 상태는 동일**(인증 무효 + 예약 없음). 사용자는 다음 조회에서 결과를 본다(RSV-608)

---

## 새로 내린 📌 결정 요약

| # | 결정 | 위치 |
|---|---|---|
| 1 | 실패 시도도 verifications row로 저장. status는 approved\|rejected 2값 + `needs_audit BOOLEAN` + `audited_at`. retry는 응답 status로만 구분. reason_code·confidence 등 컬럼 추가 (db-schema 갱신 필요) | 서두 |
| 2 | 감사 무효화는 별도 status 없이 `rejected` + `REVOKED_BY_AUDIT`로 표현 — 토큰 무효·재인증 허용이 자동으로 따라온다 | 서두 |
| 3 | method 판정: image 있으면 photo, shop_id만 있으면 manual, 둘 다 없으면 400 | 공통 전제 |
| 4 | RequiredFieldVerifier는 멈춰,섬! 체인에서 severity="retry" | 공통 전제 |
| 5 | StoreVerifier 2단계 임계값: 유사도 <0.5 reject, 0.5~0.7 승인+감사 플래그, ≥0.7 통과 (D-03·D-05 구체화) | 공통 전제 |
| 6 | 중복 check_and_mark는 승인 트랜잭션 시점에 수행(체인 단계는 조회만) — retry 재제출 자기충돌 방지 | 공통 전제 |
| 7 | localStorage `stop-island:verify` = `{ token?, verification_id, status, issued_date, shop_name? }`, 서버가 단일 진실. 폴링 규약은 폐지(기다릴 상태 없음) | 공통 전제 |
| 8 | HEIC는 v1에서 변환 없이 거부 + 설정 안내 문구 | VF-204 |
| 9 | photo 경로의 shop_id는 판정에 영향 없는 힌트(OCR 매칭 우선) | VF-304 |
| 10 | manual 승인 기록 규약: 항상 approved + needs_audit=1 + `MANUAL_SHOP_SELECTED`, 중복 mark 없음 — 방어는 1일 1회 유니크 + 사후감사 | 영역 6 |
| 11 | 프리필 우선순위: 사용자 드롭다운 조작 전에만 matched_shop_id 프리필, 조작 후 덮어쓰지 않음 | VF-605 |
| 12 | POST /api/verify 클라이언트 fetch 타임아웃 90초 | VF-701 |
| 13 | 자정 경계 완화 없음 — DateVerifier 기준일은 판정 시각의 KST 오늘, 구제는 manual 즉시 승인 경로 | VF-804 |
| 14 | pending 선삽입 폐지. 승인 INSERT + 부분 유니크 `(device_id, date) WHERE status='approved'`로 동시 제출 직렬화. 동시 판정의 Gemini 중복 호출은 수용. db-schema의 무조건부 UNIQUE 교체 (갱신 필요) | VF-901 |
| 15 | **확인 단계(recognized/confirm) 아키텍처(D-29)**: 잘 읽힌 영수증은 즉시 승인하지 않고 `status: "recognized"` + 추출 필드(가게·일시·금액·승인번호 뒷자리)로 응답(row·토큰 없음). [네, 맞아요]=같은 image+`confirm=true` 재제출(해시 캐시로 Gemini 스킵)→승인. [아니요]=manual 전환. review도 확인 화면을 탄다 | 서두·공통 전제·영역 3·5 |
| 16 | **사업자등록번호 우선 매칭(D-29)**: StoreVerifier는 사업자번호 정확 일치를 1순위로, 없으면 상호명 fuzzy 폴백. 상점에 `biz_number` 저장(db-schema 갱신 필요). 상호명은 표시·보조 매칭용 | 공통 전제 |
| 17 | **최소 결제금액 정책(D-29 신설)**: `MinAmountVerifier(reject)` 추가. 미달 시 `UNDER_MIN_AMOUNT` 거부(확인 없이). 값 📌 5,000원(파트너 협의 확정), 서버 설정·상점별 차등 가능. amount=None은 스킵 | 공통 전제·VF-410 |
| 18 | **못 읽음 retry → 상점 직접 선택 유도(D-29)**: NOT_RECEIPT·MISSING_REQUIRED_FIELD의 주 복구 경로를 재촬영에서 manual 선택 UI로 전환(재촬영도 병행 가능). 중복·금액 미달·당일 아님은 확인 없이 즉시 거부 | 영역 4 |
