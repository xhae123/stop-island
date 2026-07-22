# 영수증 코어 서버 (receipt-core) 설계

> standalone 영수증 추출 코어. 여러 서비스가 API로 소비한다. stop-island는 첫 소비자.
> **언어: Go(stdlib only, 정적 바이너리 ~6MB).** 구현 위치: 레포 루트 `receipt-core/`.
> 소비 배선: `backend/app/ocr/http_engine.py`(Python 소비자 — 계약이 언어중립이라 무관).
>
> Go 결정(Tom): 진짜 standalone 코어라 Go 근거가 가장 셈 — 정적 바이너리·최소 메모리·
> 명시적 타입·distroless. 계약(/v1/extract)이 영속자산이라 언어는 그 뒤에서 교체 가능했고,
> 실제로 Python 레퍼런스 구현을 같은 계약 유지한 채 Go로 재작성함.

## 왜 별도 서버인가 (결정의 "왜")

처음엔 "이 팝업 하나의 장애격리" 목적으로 분리를 검토했으나 그 근거는 약했다 —
단일노드·1인운영·동시 수십 규모에선 인프로세스 하드닝(동시성 상한+타임아웃)이
분리보다 싸게 90%를 준다. **분리를 정당화한 진짜 이유는 "여러 서비스가 API로
소비하는 공유 코어 능력"** 이다(다중 소비자). 이건 별도 서버가 값을 하는 정당한 사유.

## 아키텍처

```
소비자A(stop-island) ─┐
소비자B(향후)        ─┼─ HTTP(X-API-Key) ─→ receipt-core ─→ Gemini Flash
소비자C(향후)        ─┘   POST /v1/extract      (무상태, v1)
```

- **코어 책임 = 이미지 → 추출**까지. 참여상점 매칭·당일판정·중복·device 한도 같은
  **도메인 정책은 각 소비자가 자기 DB로** 판단한다.
- **v1 무상태(DB 없음).** 전 소비자 글로벌 dedup 등 공유상태가 필요해지면 v2에서
  데이터스토어 추가. 지금 안 만드는 이유: 2번째 소비자의 공유 요구가 아직 불명 →
  예제 1개로 공유 추상화 지으면 speculative generality.
- **검증체인(evaluate)은 코어로 안 올림.** stop-island에 그대로 둔다(같은 이유).

## API 계약 v2.1

```
GET  /health → 200 {"status":"ok"}

POST /v1/extract
Headers:
  X-API-Key:    <소비자 키>          # config.RECEIPT_CORE_API_KEYS 중 하나. 비면 dev(인증off)
  X-Request-Id: <uuid>              # 로그·응답헤더 echo(크로스서비스 추적). 없으면 서버 생성
  Content-Type: multipart/form-data
Body: field `image` (jpeg|png 바이너리 — base64 아님, +33% 회피)

200 { "is_receipt": true,
      "store_name":      string|null,   # 원문 상호. 매칭은 소비자
      "business_number": string|null,   # 사업자번호. exact 매칭·감사
      "date":            "YYYY-MM-DD"|null,  # 인쇄 결제일(KST 로컬, 변환 X)
      "approval_number": string|null,   # 문자열(선행0·영숫자, int 파싱 금지)
      "total_amount":    integer|null,   # 결제 총액 KRW 정수(원)
      "confidence":      0.0~1.0 }        # self-report, 자문용(단독 판정 근거 아님)
200 { "is_receipt": false }               # 진짜 비영수증. 나머지 필드 없음
503 { "reason": "saturated|upstream_unavailable", "request_id": "..." }
400 { "reason": "empty_body|too_large|unsupported_type" }
401                                        # X-API-Key 불일치
```

**규약:**
- `is_receipt` = "영수증 이미지냐"만. 추출 성공 여부 아님. 영수증인데 상호 못 읽음 →
  `is_receipt=true` + `store_name=null`(≠ false).
- 추출 필드 전부 nullable.
- 503 `reason`은 로그·관측 전용 — 소비자 동작은 reason 무관(전부 폴백).

**소비자 매핑(stop-island `HttpReceiptEngine`):**

| 코어 응답 | 매핑 | 사용자 |
|---|---|---|
| 200 is_receipt=true | `OcrResult`(total_amount·business_number는 raw로) | 정상 판정 |
| 200 is_receipt=false | `NotReceiptError` | NOT_RECEIPT → retry |
| 503 / timeout / 401 / 기타 | `OcrUnavailable` | 503 → **수동 상점선택** |

## 확장 필드 근거 (total_amount·business_number)

코어는 이미지를 보는 유일·최종 지점. 값싸게 뽑히는 필드를 지금 안 뽑으면 나중에
Gemini를 다시 호출($)해야 복구된다 — **추출 경계에선 YAGNI가 뒤집힌다.**
- `total_amount`: 최소결제룰(향후)·운영감사·중복지문 강화·객단가 분석.
- `business_number`: 한글 상호 fuzzy보다 정확한 exact 매칭·감사.
- 제외: LineItem[](벌크·진짜 YAGNI), 세금분해, 결제시각(DateVerifier는 날짜만).

## 격리 장치

- **fail-fast 동시성 세마포어**(`RECEIPT_CORE_MAX_CONCURRENCY`, 기본 8). 초과 요청은
  대기 없이 즉시 503 saturated로 스레드 반납 → OCR이 스레드풀을 독식해 다른 요청을
  굶기는 걸 막음. (차단式이면 대기가 스레드를 점유해 격리 무의미 — 그래서 비차단.)
- **cgroup mem_limit 256m**(compose) — 이미지/OCR 폭주가 노드를 굶기지 못하게.
- **타임아웃 예산**: 코어 내부 Gemini timeout(8s) < 소비자 호출 timeout(10s) →
  코어가 먼저 깔끔한 503. 소켓 타임아웃은 최후.

## 구현 구조 (Go, stdlib only)

```
receipt-core/
├── go.mod                (module receipt-core, 외부 의존성 0 → go.sum 없음)
├── main.go               부트·graceful shutdown·time/tzdata 임베드(KST)·엔진 선택
├── config.go             env 파싱(API_KEYS, MAX_CONCURRENCY, TIMEOUT, MOCK, GEMINI_*)
├── server.go             Server·라우팅·인증·fail-fast 세마포어·핸들러·JSON 응답
├── guard.go              이미지 형식·크기·매직바이트 가드
├── engine.go             Engine 인터페이스·ExtractResult·MockEngine·GeminiEngine(★SWAP★)
├── server_test.go / auth_test.go   table-driven(16개)
├── Dockerfile            멀티스테이지 golang:1.26 → distroless/static(aarch64)
├── docker-compose.yml / .env.example / .dockerignore
```

## 실행/검증 상태 (2026-07-22~23, 밤샘 자율실행)

- 코어 Go 테스트 16/16, backend 139/139(기존 133 + HttpReceiptEngine 6) 통과. `go vet` clean.
- 정적 바이너리 5.9M(CGO off), KST는 time/tzdata 임베드로 distroless에서도 동작.
- 라이브 E2E(mock, 실 Go 바이너리): browser→backend→core(HTTP)→evaluate→approved+token+막걸리계보.
- **격리 라이브 증명**: 코어 종료 시 → backend `/api/status` 200(좌석 생존),
  photo verify 503+수동폴백 안내, manual 폴백(상점 직접선택) 코어 없이 approved.
- **mock 엔진 탑재**(실 Gemini 키 없음/시크릿 정책). 실배선 = `GeminiEngine.Recognize`의
  ★SWAP POINT★ 한 곳 배선 + `RECEIPT_CORE_MOCK=0`.
- **비배포·비커밋**(정책). stop-island는 env-gated 추가만 — `RECEIPT_CORE_URL` 없으면
  기존 인프로세스 Gemini seam 그대로(기본 동작 불변).

## 배포 (인프라, 향후 — deploy-last)

공용 엣지 구조에 붙는다:
1. `services/receipt-core/`로 rsync → `docker compose up -d --build`(edge 조인).
2. `/home/ubuntu/edge/`에서 `./scripts/add-service.sh <도메인> receipt-core:8000`
   → 서브도메인(예: `receipt.leafeep.com`) + 인증서.
3. `.env`에 `RECEIPT_CORE_API_KEYS` 설정(소비자별 키). stop-island `.env`에
   `RECEIPT_CORE_URL`+`RECEIPT_CORE_API_KEY` 설정.
4. 소비자가 같은 노드면 서브도메인 없이 내부망(container name)으로도 가능 —
   외부 서비스가 소비하면 서브도메인+API키 필요.

## 후속 (별도 이슈)

- **실 Gemini 배선** — Go `GeminiEngine.Recognize`(★SWAP POINT★)에 net/http generateContent +
  response_schema 배선. 타임아웃/5xx/429 → ErrUnavailable 매핑. `RECEIPT_CORE_MOCK=0`.
- **영속 컬럼** — `total_amount`·`business_number`를 stop-island가 실제로 잡으려면
  `Verification` 모델 컬럼 추가(스키마 변경). 안 담으면 소비자단에서 또 버려짐.
- **최소결제룰** — `total_amount` 소비(룰 확정 시).
- **v2 stateful** — 전 소비자 글로벌 dedup(approval_number)이 필요하면 데이터스토어.
- **cleanup** — stop-island가 코어로 완전 이관되면 `backend/app/ocr/engine.py`의
  Gemini seam 제거(코어가 SoT). 지금은 폴백 겸 유지.
