# DB 스키마

> 7일간 팝업, 좌석 6개, 동시 접속 소규모. 복잡한 구조 불필요.

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
  id          TEXT PRIMARY KEY,           -- 'cafe-a', 'bookstore-b' 등 슬러그
  name        TEXT NOT NULL,              -- '카페 A'
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
- `is_open = false`면 예약 불가 (관리자가 닫은 상태).

> **결정:** 좌석은 관리자가 추가/삭제 가능하게. 초기 시드 데이터로 A1~B3 6개 넣되, 현장 상황에 따라 변경 가능.

---

## verifications — 영수증 인증

```sql
CREATE TABLE verifications (
  id          TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id   TEXT NOT NULL,              -- 브라우저 fingerprint 또는 localStorage UUID
  image_url   TEXT,                       -- 업로드된 영수증 이미지 URL. 상점 직접 선택 시 null.
  shop_id     TEXT REFERENCES shops(id),  -- 직접 선택한 상점. 이미지 업로드 시에도 선택 가능.
  method      TEXT NOT NULL,              -- 'photo' | 'manual' (사진 vs 직접 선택)
  status      TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected'
  token       TEXT UNIQUE,                -- 인증 성공 시 발급. 예약에 사용.
  verified_at TIMESTAMP,                  -- 승인 시각
  created_at  TIMESTAMP NOT NULL DEFAULT now(),

  CONSTRAINT one_per_device_per_day UNIQUE (device_id, (created_at::date))
);

CREATE INDEX idx_verifications_device_date ON verifications (device_id, created_at);
CREATE INDEX idx_verifications_status ON verifications (status) WHERE status = 'pending';
```

- **1일 1회 제한**: `device_id` + 날짜 기준 UNIQUE. 같은 기기에서 당일 재인증 시도 시 거부.
- **method = 'manual'**: 상점 직접 선택 시. `image_url` null, `shop_id` 필수.
- **method = 'photo'**: 사진 업로드 시. `image_url` 필수, `shop_id` optional.
- **token**: 인증 승인 시 서버에서 발급. 이 토큰으로 예약 가능. UUID.
- **pending 상태**: 운영진이 관리자 화면에서 승인/거부.

> **결정 — 수동 인증 방식 채택.** OCR 자동 인증은 v1 스코프에서 제외. `status`는 운영진이 수동으로 변경. 단, method='manual'(상점 직접 선택)은 자동 승인 처리 가능 — 팝업 현장에서 운영진이 일일이 확인하기 어려울 수 있으므로.

---

## reservations — 예약

```sql
CREATE TABLE reservations (
  id            TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  seat_id       TEXT NOT NULL REFERENCES seats(id),
  verify_token  TEXT NOT NULL REFERENCES verifications(token),
  status        TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'expired' | 'cancelled'
  reserved_at   TIMESTAMP NOT NULL DEFAULT now(),
  expires_at    TIMESTAMP NOT NULL,              -- reserved_at + 2시간 (기본)
  created_at    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_reservations_seat_active ON reservations (seat_id) WHERE status = 'active';
CREATE INDEX idx_reservations_expires ON reservations (expires_at) WHERE status = 'active';
```

- **좌석 available 판단**: `seats.is_open = true` AND 해당 seat_id에 `status = 'active'`인 reservation이 없으면 available.
- **만료**: `expires_at`을 넘기면 만료 처리. 서버에서 주기적으로 또는 조회 시 lazy 처리.
- **중복 예약 방지**: INSERT 시 해당 좌석에 active reservation이 있는지 체크 (트랜잭션).

> **결정 — 예약 만료 2시간.** 7일 팝업, 좌석 6개 규모에서 합리적. 필요하면 관리자가 수동 해제 가능.

---

## guestbook_entries — 방명록

```sql
CREATE TABLE guestbook_entries (
  id          TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  content     TEXT NOT NULL,              -- 최대 500자
  rating      INTEGER CHECK (rating BETWEEN 1 AND 5),  -- nullable. 별점 선택 안 하면 null.
  created_at  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_guestbook_created ON guestbook_entries (created_at DESC);
```

- **완전 익명.** 작성자 식별 정보 없음. device_id도 저장하지 않음.
- **인증 없이 작성 가능.** 방명록은 누구나 쓸 수 있게. (영수증 인증은 예약에만 필요)

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

- 방명록 글에 상점을 태그. N:M 관계.
- "서점 B에서 산 책이랑 음식점 C 도시락이랑 최고 조합이에요" → 서점B, 음식점C 태그.

---

## 시드 데이터

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
| `/api/status` | GET | seats + reservations | 빈 자리 수 = open seats - active reservations |
| `/api/shops` | GET | shops | `is_active = true`, `sort_order` 정렬 |
| `/api/verify` | POST | verifications | 이미지 업로드 or 상점 선택 |
| `/api/seats` | GET | seats + reservations | 좌석별 상태 계산 |
| `/api/reserve` | POST | reservations | verify_token 필수 |
| `/api/guestbook` | GET | guestbook_entries + guestbook_shop_tags | cursor 기반, 10개씩 |
| `/api/guestbook` | POST | guestbook_entries + guestbook_shop_tags | content + shop_tags[] |

---

## 관리자 API (추후 상세화)

| API | 메서드 | 기능 |
|---|---|---|
| `/api/admin/verifications` | GET | pending 인증 목록 |
| `/api/admin/verifications/:id` | PATCH | 승인/거부 (`status` 변경) |
| `/api/admin/seats/:id` | PATCH | 좌석 열기/닫기 (`is_open` 변경) |
| `/api/admin/reservations/:id` | DELETE | 예약 수동 해제 |
| `/api/admin/guestbook/:id` | DELETE | 방명록 삭제 |
| `/api/admin/shops` | POST/PATCH | 상점 추가/수정 |
