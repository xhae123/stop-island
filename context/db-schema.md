# DB 스키마

> 7일간 팝업, 좌석 6개, 동시 접속 소규모. 복잡한 구조 불필요.
> **단일 진실은 `backend/app/models.py`.** 이 문서는 그 요약이며, 기획 결정(`context/scenarios/00-overview.md` 결정표 D-00~D-25)을 반영한다.

## ERD

```
shops ──┐
        ├── verifications ── reservations
seats ──┘        │
                 │
        guestbook_entries ── guestbook_shop_tags ── shops
```

---

## shops — 참여 상점

```sql
CREATE TABLE shops (
  id          TEXT PRIMARY KEY,           -- 'makgeolli-gyebo' 등 슬러그
  name        TEXT NOT NULL,              -- '막걸리계보'
  category    TEXT NOT NULL,              -- 'cafe' | 'restaurant' | 'bookstore' | 'bar' | 'craft'
  is_active   BOOLEAN NOT NULL DEFAULT true,
  sort_order  INTEGER NOT NULL DEFAULT 0, -- 메뉴 선택 화면 badge 정렬용
  created_at  TIMESTAMP NOT NULL DEFAULT now()
);
```

- 팝업 기간 동안 고정. 관리자가 추가/수정 가능.
- `id`를 슬러그로 쓰는 이유: 좌석 6개, 상점 15개 내외 규모에서 UUID 불필요.

---

## seats — 좌석

```sql
CREATE TABLE seats (
  id              TEXT PRIMARY KEY,       -- 'a1', 'a2', 'b3' 등
  label           TEXT NOT NULL,          -- 'A1' (표시용)
  capacity        INTEGER NOT NULL,       -- 2 또는 4
  position_label  TEXT,                   -- '창가 자리' 등. nullable.
  is_open         BOOLEAN NOT NULL DEFAULT true,  -- 관리자가 열기/닫기
  created_at      TIMESTAMP NOT NULL DEFAULT now()
);
```

- 좌석 상태(available/taken)는 seats 테이블에 저장하지 않음. `reservations`에서 실시간 계산.
- `is_open = false`면 예약 불가 (관리자가 닫은 상태 — D-22 ②).

> **결정:** 좌석은 관리자가 추가/삭제 가능하게. 초기 시드 데이터로 A1~B3 6개 넣되, 현장 상황에 따라 변경 가능.

---

## verifications — 영수증 인증

```sql
CREATE TABLE verifications (
  id               TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id        TEXT NOT NULL,             -- localStorage UUID (D-07). X-Device-Id 헤더
  image_url        TEXT,                      -- 업로드 영수증 원본 위치. manual이면 null (D-23)
  image_hash       TEXT,                      -- 중복 검출용. 승인번호 None일 때의 폴백 키
  shop_id          TEXT REFERENCES shops(id), -- OCR 매칭 상점(photo) 또는 직접 선택 상점(manual)
  method           TEXT NOT NULL,             -- 'photo' | 'manual'
  status           TEXT NOT NULL,             -- 'approved' | 'rejected' (2값 — pending 없음)
  needs_audit      BOOLEAN NOT NULL DEFAULT false, -- 관용 승인 사후감사 플래그 (D-05)
  reason_code      TEXT,                      -- 판정 사유 코드 (03-verify.md reason_code 표)
  confidence       REAL,                      -- OCR confidence (감사 참고)
  ocr_store_name   TEXT,                      -- OCR이 읽은 상호명 (감사 참고)
  ocr_date         TEXT,                      -- OCR이 읽은 영수증 날짜 (감사 참고)
  approval_number  TEXT,                      -- 영수증 승인번호. 중복 검출 1순위 키
  token            TEXT UNIQUE,               -- approved일 때만 발급. 예약에 사용
  verify_date      TEXT NOT NULL,             -- 판정 시각의 KST 날짜 'YYYY-MM-DD' (D-01 하루 경계 키)
  verified_at      TIMESTAMP,                 -- approved 확정 시각
  audited_at       TIMESTAMP,                 -- 감사 완료 시각. 미감사면 null
  created_at       TIMESTAMP NOT NULL DEFAULT now()
);

-- D-06: 1일 1회 제한. approved만 부분 유니크로 직렬화한다.
CREATE UNIQUE INDEX uq_verif_device_day_approved
  ON verifications (device_id, verify_date) WHERE status = 'approved';
CREATE INDEX idx_verifications_device_date ON verifications (device_id, verify_date);
CREATE INDEX idx_verifications_status ON verifications (status);
```

- **동기 판정, pending 없음 (D-02·D-05):** `POST /api/verify` 안에서 OCR 판정을 끝까지 수행하고
  최종 status(`approved`|`rejected`)로 INSERT한다. "확인 중" 대기 상태는 존재하지 않는다.
- **needs_audit (D-05):** confidence 미달·fuzzy 경계선(review성) 판정과 manual 제출은 **승인 + `needs_audit=true`**.
  사용자 경험은 통상 승인과 무차이. 운영진이 원격 감사 큐에서 사후 확인(D-22 ①).
- **verify_date (D-01):** `created_at`(UTC)이 아니라 판정 시각의 **KST 날짜**가 하루 경계 키다.
  당일 방문 수(D-20)·1일 1회 제한·재진입 조회가 전부 이 컬럼 기준. `app/timeutil.py`가 계산.
- **부분 유니크 (D-06):** `(device_id, verify_date) WHERE status='approved'`. approved 1건/일을 DB 레벨에서
  직렬화하고, 동시 제출(VF-901)의 원자적 관문이 된다. rejected/retry는 유니크에서 빠지므로 실패 재시도 무제한,
  감사 무효화 후 재인증(VF-802)이 자연히 허용된다. SQLite 표현식 유니크 대신 `verify_date` 컬럼을 두어
  `sqlite_where`로 부분 인덱스를 건다.
- **method 판정 (03-verify.md 📌):** image 있으면 `photo`(shop_id는 힌트일 뿐, 판정은 OCR 우선),
  image 없이 shop_id만 있으면 `manual`, 둘 다 없으면 400 `INVALID_REQUEST`.
- **감사 무효화 (D-22):** 별도 `revoked` status를 두지 않는다. 어뷰징 판정 시
  `status='rejected'` + `reason_code='REVOKED_BY_AUDIT'` + `audited_at`으로 전환 → 토큰 즉시 무효.
- **실패 row도 보존:** rejected/retry 시도도 전부 row로 남긴다(통계·어뷰징 추적). API의 `retry`는 DB상 `rejected` +
  reason_code로 구분. 단 OCR 장애(503 `OCR_UNAVAILABLE`)와 4xx 입력 오류는 판정 자체가 없었으므로 row를 남기지 않는다.

> **결정 — OCR 자동 인증 채택 (D-02).** (기존 "OCR v1 제외" 결정은 폐기.)
> `context/design-receipt-ocr.md`의 ReceiptEngine으로 사진을 자동 판정한다. 결과 3상태:
> approved(즉시 토큰) / rejected(사유 표시·재시도) / retry(재촬영 요청). 애매한 건은 승인 + `needs_audit`(D-05).
> OCR 장애 시 manual 경로로 폴백(D-25).

> **결정 — manual은 즉시 자동 승인 (D-04).** 무인 운영(D-00)이라 현장 확인이 불가능하다.
> manual 제출은 항상 `approved` + `needs_audit=true` + `reason_code='MANUAL_SHOP_SELECTED'`.
> 영수증 증빙이 없으므로 전건 감사 대상이며, 중복 mark는 하지 않는다(방어는 1일 1회 유니크 + 사후감사).

---

## reservations — 예약

```sql
CREATE TABLE reservations (
  id            TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  seat_id       TEXT NOT NULL REFERENCES seats(id),
  verify_token  TEXT NOT NULL REFERENCES verifications(token),
  device_id     TEXT NOT NULL,                  -- 예약 소유 검증용 (D-10 내 예약, RSV-801 자리 비우기)
  status        TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'expired' | 'cancelled'
  reserved_at   TIMESTAMP NOT NULL DEFAULT now(),
  expires_at    TIMESTAMP NOT NULL,              -- reserved_at + 2시간 (D-11)
  created_at    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_reservations_seat_active ON reservations (seat_id);
CREATE INDEX idx_reservations_expires ON reservations (expires_at);
```

- **좌석 available 판단:** `seats.is_open = true` AND 해당 seat_id에 `status = 'active'`인 reservation이 없으면 available.
- **만료 (D-11):** 2시간. 판정은 **조회 시 lazy**(expires_at 지난 active는 조회 시점에 expired 처리) + 1분 주기 백그라운드 스윕 병행.
- **중복 예약 방지 (D-12):** INSERT 시 해당 좌석에 active reservation이 있는지 트랜잭션으로 체크. 선점당하면 409 `SEAT_TAKEN`.
- **device_id (D-10):** 예약 소유자 식별. `GET /api/reservations/:id` 조회·`DELETE`(자리 비우기)에서 소유 검증에 사용.
- **verify_token 수명 (D-08):** 발급일 당일 자정(KST)까지 유효. 동시에 active 예약 1건만. 만료·취소되면 같은 토큰으로 당일 재예약 가능.
- **qr_token 폐기 (D-09):** 예약 완료 화면은 본인 확인용이며 타인에게 제시하는 티켓이 아니므로 QR 토큰을 발급하지 않는다.

> **결정 — 예약 만료 2시간 (D-11).** 7일 팝업, 좌석 6개 규모에서 합리적. 관리자가 수동 해제 가능(D-22 ③).

---

## guestbook_entries — 방명록

```sql
CREATE TABLE guestbook_entries (
  id          TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  content     TEXT NOT NULL,              -- 최대 500자, trim 후 1자 이상 (D-18)
  rating      INTEGER CHECK (rating BETWEEN 1 AND 5),  -- nullable. 별점 선택 안 하면 null (D-17)
  created_at  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_guestbook_created ON guestbook_entries (created_at DESC);
```

- **완전 익명.** 작성자 식별 정보 없음. device_id도 저장하지 않음.
- **인증 없이 작성 가능.** 방명록은 누구나 쓸 수 있게. (영수증 인증은 예약에만 필요)
- **별점 저장 (D-17):** `POST /api/guestbook` body에 `rating: 1~5 | null` 포함.
- **어뷰징 방어 (D-19):** device_id 기준 1분 1회 rate limit(서버). 초과 시 429. 삭제는 관리자.

> **결정 — 방명록은 인증 불필요.** 진입 장벽을 낮춰서 후기를 많이 모으는 게 이득. 어뷰징은 관리자 삭제로 대응.

---

## guestbook_shop_tags — 방명록 맛집 태그

```sql
CREATE TABLE guestbook_shop_tags (
  entry_id  TEXT NOT NULL REFERENCES guestbook_entries(id) ON DELETE CASCADE,
  shop_id   TEXT NOT NULL REFERENCES shops(id),
  PRIMARY KEY (entry_id, shop_id)
);
```

- 방명록 글에 상점을 태그. N:M 관계. 0~5개 (D-18).
- "서점 B에서 산 책이랑 음식점 C 도시락이랑 최고 조합이에요" → 서점B, 음식점C 태그.

---

## 시드 데이터 (`backend/app/seed.py`, 멱등)

```sql
-- 좌석
INSERT INTO seats (id, label, capacity, position_label) VALUES
  ('a1', 'A1', 2, NULL),
  ('a2', 'A2', 2, NULL),
  ('a3', 'A3', 4, '창가 자리'),
  ('b1', 'B1', 2, NULL),
  ('b2', 'B2', 2, NULL),
  ('b3', 'B3', 4, NULL);

-- 상점 (예시 — 실제 데이터는 8월에 확정)
INSERT INTO shops (id, name, category, sort_order) VALUES
  ('makgeolli-gyebo', '막걸리계보', 'bar', 1),
  ('jojunyoung', '조준영 목공방', 'craft', 2);
```

---

## API ↔ 테이블 매핑

| API | 메서드 | 테이블 | 비고 |
|---|---|---|---|
| `/api/status` | GET | seats + reservations | 빈 자리 수 = open seats - active reservations. `{ available_seats, today_visitors, is_full }` |
| `/api/shops` | GET | shops | `is_active = true`, `sort_order` 정렬 |
| `/api/verify` | POST | verifications | multipart(image?, shop_id?) + X-Device-Id. 응답 3상태 approved/rejected/retry |
| `/api/verify/status` | GET | verifications | **신설.** device_id 기준 당일(KST) 인증 상태 조회. 재진입 복원용(폴링 아님) |
| `/api/seats` | GET | seats + reservations | 좌석별 상태 계산 |
| `/api/reserve` | POST | reservations | verify_token 필수. 응답 `{ reservation_id, seat, expires_at }` (qr_token 없음) |
| `/api/reservations/:id` | GET/DELETE | reservations | **신설.** 내 예약 조회(D-10) / 자리 비우기(D-09). device_id 소유 검증 |
| `/api/guestbook` | GET | guestbook_entries + guestbook_shop_tags | cursor 기반, 10개씩 |
| `/api/guestbook` | POST | guestbook_entries + guestbook_shop_tags | content + rating + shop_tags[] |

---

## 관리자 API (D-21·D-22 — 원격 모니터링)

관리자 인증(D-21): 단일 비밀번호 → `POST /api/admin/login` → HttpOnly 세션 쿠키(12시간).
`/admin` 라우트와 모든 `/api/admin/*`는 세션 필수.

| API | 메서드 | 기능 |
|---|---|---|
| `/api/admin/login` | POST | 비밀번호 로그인 → 세션 쿠키 발급 (D-21) |
| `/api/admin/verifications` | GET | **감사 큐** — `needs_audit=true` 인증 목록(이미지·OCR 결과·판정 사유) (D-22 ①) |
| `/api/admin/verifications/:id` | PATCH | 감사 처리 — "문제없음"(needs_audit=false) 또는 "어뷰징 무효화"(REVOKED_BY_AUDIT + active 예약 해제) |
| `/api/admin/seats/:id` | PATCH | 좌석 열기/닫기 (`is_open` 변경) (D-22 ②) |
| `/api/admin/reservations/:id` | DELETE | active 예약 수동 해제 (`status='cancelled'`) (D-22 ③) |
| `/api/admin/guestbook/:id` | DELETE | 방명록 삭제 (D-22 ④) |
| `/api/admin/shops` | POST/PATCH | 상점 추가/수정/비활성 (D-22 ⑤) |
| `/api/admin/stats` | GET | 당일 통계 — approved 인증 수·예약 수 등 (D-22 ⑥) |

> **감사 큐 ≠ 승인 큐 (D-22).** 사용자 플로우를 막지 않고, 관용 승인된 건(`needs_audit`)을 뒤에서 정리한다.
> 어뷰징 무효화는 단일 트랜잭션으로 인증 rejected 전환 + 연결된 active 예약 cancelled 해제(VF-504).

---

## 에러 응답 규약 (D-24)

모든 실패 응답은 아래 봉투로 통일한다. `app/deps.py`의 `ApiError`/`raise_api` + `main.py` 예외 핸들러가 담당.

```json
{ "error": { "code": "SEAT_TAKEN", "message": "이미 예약된 자리예요." } }
```

주요 코드: `DEVICE_ID_REQUIRED`(400), `INVALID_REQUEST`(400), `INVALID_IMAGE`(400),
`ALREADY_VERIFIED_TODAY`(409), `SEAT_TAKEN`(409), `TOKEN_EXPIRED`(401), `OCR_UNAVAILABLE`(503).
verify 판정 사유 코드 전체 표는 `context/scenarios/03-verify.md` 참조.
