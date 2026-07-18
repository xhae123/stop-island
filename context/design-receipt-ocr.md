# receipt-ocr 모듈 설계

영수증 이미지에서 구조화된 데이터를 뽑고, 서비스별 규칙으로 검증하는 모듈.

- OCR 엔진: **Gemini Flash** 고정
- 추상화 대상: 추출 결과 스키마 + 검증 규칙 체인

---

## 표준 출력: ReceiptData

Gemini Flash가 영수증에서 뽑아내는 모든 정보의 표준 구조.
어떤 서비스에서 쓰든 이 스키마 하나로 받는다.

### 전체 구조

```python
@dataclass
class ReceiptData:
    # 영수증 여부. structured output을 강제하면 영수증이 아닌 이미지도
    # 빈 JSON으로 통과해버리는 문제가 있어서 최상위에 명시적으로 둔다.
    is_receipt: bool

    # 상점 정보
    store: StoreInfo

    # 거래 정보
    transaction: TransactionInfo

    # 품목 목록
    items: list[LineItem]

    # 합계
    totals: Totals

    # 메타
    meta: ExtractionMeta
```

**is_receipt가 왜 최상위인가:** extractor가 `is_receipt=False`를 받으면 `NotReceiptError`를 던지고 끝낸다. 즉 이 필드는 사실상 extractor 내부에서만 소비되고, ReceiptData가 엔진/Verifier까지 도달하는 시점엔 항상 `True`다. 그래도 스키마에 남겨두는 이유는 Gemini의 판단 근거를 구조화된 응답 안에서 강제하기 위함 — 프롬프트에 "영수증이 아니면 이 필드를 false로" 라고만 지시하는 것보다, 응답 스키마 자체에 필드가 있어야 모델이 실제로 판단을 거친다.

### StoreInfo — 상점 정보

```python
@dataclass
class StoreInfo:
    name: str | None              # 상호명. "막걸리계보", "스타벅스 행궁점"
    business_number: str | None   # 사업자등록번호. "123-45-67890"
    address: str | None           # 주소. "수원시 팔달구 정조로 781-13"
    phone: str | None             # 전화번호. "031-123-4567"
    representative: str | None    # 대표자명
```

**왜 이렇게 많이 뽑나:** 상호명만으로는 매칭이 불안정함. "막걸리계보"가 "막걸리 계보"로 나올 수도, "(주)막걸리계보"로 나올 수도 있음. 사업자등록번호가 있으면 정확한 매칭이 가능하고, 주소로 위치 기반 검증도 할 수 있음. 서비스마다 어떤 필드로 매칭할지 다르니까 다 뽑아두는 것.

### TransactionInfo — 거래 정보

```python
@dataclass
class TransactionInfo:
    date: date | None             # 결제일. 2026-09-30
    time: time | None             # 결제시각. 14:32:00
    payment_method: str | None    # "카드", "현금", "간편결제" 등
    card_company: str | None      # "신한", "삼성" 등. 현금이면 None
    card_number_last4: str | None # 카드 끝 4자리. "1234"
    approval_number: str | None   # 승인번호. 중복 검증에 사용 가능
    receipt_number: str | None    # 영수증 번호 / 거래번호
```

**approval_number가 핵심:** 같은 영수증을 두 번 제출하는 걸 잡으려면 이 번호로 중복 체크하는 게 가장 정확함. 이미지 해시보다 신뢰도 높음 (각도, 조명 달라도 같은 번호). 다만 approval_number 자체가 추출 실패로 None일 수 있으니, 이미지 해시는 폴백 겸 캐시 키로 별도 용도가 있다 (아래 "이미지 해시 캐시" 참고).

### LineItem — 품목

```python
@dataclass
class LineItem:
    name: str                     # 품목명. "아메리카노(ICE)"
    quantity: int | None          # 수량. 1
    unit_price: int | None        # 단가. 4500
    amount: int | None            # 소계. 4500 (quantity * unit_price)
```

### Totals — 합계

```python
@dataclass
class Totals:
    subtotal: int | None          # 공급가액
    tax: int | None               # 부가세
    discount: int | None          # 할인 금액
    total: int | None             # 최종 결제 금액
```

### ExtractionMeta — 추출 메타정보

```python
@dataclass
class ExtractionMeta:
    confidence: float             # 0.0~1.0. Gemini가 스스로 매긴 self-report 값.
    raw_text: str | None          # Gemini가 읽어낸 원문 텍스트 전체. 기본 None (아래 참고)
    image_hash: str                # 이미지 SHA-256. engine이 extract 호출 전에 계산해서 채워넣음
    extracted_at: datetime        # 추출 시각
    model: str                    # 사용된 모델명. "gemini-2.0-flash"
```

**confidence는 self-report임을 명시:** 이 값은 검증된 정확도가 아니라 Gemini가 "내가 이만큼 확신한다"고 응답에 적어낸 숫자다. 모델이 근거 없이 지어낼 수 있으므로, 이 값 하나로 자동 거부(reject) 판단을 내리지 않는다 — `ConfidenceVerifier`가 기본적으로 `review`(수동 확인)로만 넘기는 이유.

**field_confidence는 스키마에서 제거했다:** 애초에 Gemini가 필드별 신뢰도를 신뢰성 있게 제공하지 않는다. "store.name: 0.95, transaction.date: 0.7" 같은 숫자를 응답에 넣게 할 수는 있지만, 그 숫자가 실제 필드 정확도를 반영한다는 보장이 없다 — 모델이 그럴듯하게 지어낼 뿐이다. 이런 값을 근거로 "날짜 신뢰도가 0.5 미만이면 수동 확인" 같은 자동화 규칙을 짜면, 근거 없는 숫자 위에 규칙을 쌓는 셈이라 제거했다.

**raw_text는 기본적으로 받지 않는다:** 원문 텍스트 전체를 응답에 포함시키면 출력 토큰이 늘어나 비용·지연시간이 증가하고, 구조화된 필드 추출의 정확도가 오히려 떨어지는 경향이 있다(모델이 자유 텍스트 생성과 구조화 추출을 동시에 하려다 어느 쪽도 덜 정확해짐). 디버깅/이의제기 대응 등으로 원문이 필요한 서비스만 `ReceiptExtractor(..., include_raw_text=True)`로 켠다.

### None의 의미

모든 필드가 nullable (단 `is_receipt`, `meta.confidence`, `meta.image_hash` 등 메타 자체는 항상 값이 있음). None = 해당 정보가 영수증에 없거나 추출 실패.
서비스에서 어떤 필드를 필수로 볼지는 Verifier가 결정한다. Verifier의 None 처리 규약은 아래 "Verifier — 검증 규칙" 참고.

---

## 필드 경로 상수

`RequiredFieldVerifier` 등이 "필드 경로"를 문자열로 받는데, 매직 스트링(`"store.name"`)을 그대로 흩뿌리면 오타에 취약하고 리팩토링도 깨지기 쉽다. enum으로 고정한다.

```python
class FieldPath(str, Enum):
    STORE_NAME = "store.name"
    STORE_BUSINESS_NUMBER = "store.business_number"
    TRANSACTION_DATE = "transaction.date"
    TRANSACTION_APPROVAL_NUMBER = "transaction.approval_number"
    TOTALS_TOTAL = "totals.total"
    # 필요해지는 대로 추가
```

`str, Enum`을 상속해서 기존에 문자열을 기대하던 코드(dict lookup, dataclass path resolver)와 그대로 호환된다.

---

## Gemini Flash 추출기

```python
class ReceiptExtractor:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        include_raw_text: bool = False,
        timeout: float = 15.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_concurrency: int = 5,
    ):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.include_raw_text = include_raw_text
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def extract(self, image: bytes) -> ReceiptData:
        """이미지 바이트를 받아서 ReceiptData를 반환한다."""
        ...
```

내부적으로 Gemini에 structured output(JSON 스키마)을 강제해서 파싱 실패를 줄인다. 프롬프트와 스키마는 모듈 내부에 캡슐화.

**재시도·타임아웃·동시성:**

- `timeout`: 요청 하나당 최대 대기시간.
- `max_retries` / `retry_delay`: 429(rate limit), 5xx(서버 오류)는 지수 백오프(`retry_delay * 2**attempt`)로 재시도. 그 외 오류(파싱 실패, 4xx 등)는 재시도해도 결과가 안 바뀌므로 즉시 실패.
- `max_concurrency`: `asyncio.Semaphore`로 동시 Gemini 호출 수를 제한. 여러 요청이 몰릴 때 rate limit을 애초에 덜 맞기 위함.

**에러 타입:**

```python
class ExtractionError(Exception):
    """일시적 추출 실패. 재시도 가능 (타임아웃, 파싱 실패 등)."""

class NotReceiptError(ExtractionError):
    """이미지가 영수증이 아님 (is_receipt=False). 재시도해도 결과가 바뀌지 않으므로
    max_retries와 무관하게 즉시 발생시킨다."""

class RateLimitError(ExtractionError):
    """429. 백오프 후 재시도. max_retries 소진 시 그대로 raise."""
```

호출 측(엔진)은 `NotReceiptError`를 잡아서 사용자에게 "영수증 사진이 아닌 것 같아요" 같은 즉시 피드백을 줄 수 있고, `ExtractionError`/`RateLimitError`는 이미 내부에서 재시도를 다 소진한 뒤이므로 "잠시 후 다시 시도해주세요"로 처리한다.

---

## 이미지 해시 캐시

같은 이미지를 반복 제출하는 케이스(새로고침, 중복 탭, 네트워크 재시도로 인한 재전송)에서 매번 Gemini를 호출하는 건 비용 낭비다. `ReceiptEngine.process()`가 extract 호출 전에 이미지 해시를 먼저 계산해서 캐시를 확인한다.

```python
def hash_image(image: bytes) -> str:
    return hashlib.sha256(image).hexdigest()

class ResultCache(ABC):
    """image_hash 기준 추출 결과 캐시. 서비스마다 구현이 다르다."""
    @abstractmethod
    async def get(self, image_hash: str) -> ReceiptData | None: ...
    @abstractmethod
    async def set(self, image_hash: str, data: ReceiptData) -> None: ...

class InMemoryResultCache(ResultCache):
    """프로세스 내 dict. 단일 인스턴스 소규모 서비스용."""
    ...

class RedisResultCache(ResultCache):
    """Redis 기반. 여러 인스턴스에서 공유 가능."""
    ...
```

캐시는 optional이다 (`ReceiptEngine(..., cache=None)`이면 매번 Gemini 호출). 캐시 히트는 "Gemini 호출을 스킵한다"는 뜻이지 "검증을 스킵한다"는 뜻이 아니다 — Verifier 체인은 캐시된 데이터에도 항상 다시 돈다 (예: StoreVerifier의 허용 목록은 요청마다 다를 수 있으므로).

---

## Verifier — 검증 규칙

### 인터페이스

```python
class Verifier(ABC):
    """
    하나의 검증 규칙.

    None 처리 규약: 검증 대상 필드가 None이면 해당 Verifier는 스킵(통과)한다.
    예를 들어 DateVerifier는 transaction.date가 None이면 "날짜를 확인할 수 없다"고
    실패시키는 게 아니라 그냥 통과시킨다 — None 여부 자체를 막고 싶다면
    RequiredFieldVerifier를 체인 앞쪽에 명시적으로 넣어라.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """규칙 이름. "date_check", "store_match" 등."""
        ...

    @abstractmethod
    async def verify(self, data: ReceiptData, context: dict) -> VerifyOutput:
        """
        data: 검증 대상.
        context: 요청마다 바뀌는 동적 데이터 (예: 허용 상점 목록). 없으면 빈 dict.
        """
        ...
```

**왜 async인가:** `DuplicateStore`가 DB/Redis I/O를 하는 async 저장소이므로, `DuplicateVerifier.verify()`도 async여야 한다. 다른 Verifier는 동기 로직이라도 인터페이스를 통일해서 엔진 루프가 단순해진다 (`await v.verify(...)` 하나로 전부 처리).

**왜 context가 verify()의 인자인가, 생성자가 아닌가:** `StoreVerifier`의 허용 상점 목록처럼 요청마다 달라질 수 있는 값을 생성자에 박아두면, 값이 바뀔 때마다 Verifier 인스턴스를 새로 만들어야 하고 체인 전체를 재구성해야 한다. `ReceiptEngine`은 보통 앱 시작 시 한 번 조립해서 재사용하는 객체이므로, 요청마다 바뀌는 값은 `process()` 호출 시 `context`로 흘려보낸다.

### VerifyOutput / Failure

```python
@dataclass
class VerifyOutput:
    passed: bool
    failure: Failure | None = None      # passed=False일 때만 값이 있음
    metadata: dict = field(default_factory=dict)
    # 통과 시에도 부가 정보를 남길 수 있다.
    # 예: StoreVerifier가 fuzzy 매칭으로 통과시킨 경우 {"matched_store_id": "shop_12"}

@dataclass
class Failure:
    verifier: str        # 어떤 규칙이 실패했는지. "date_check"
    reason: str           # 사람이 읽을 수 있는 실패 사유. "결제일이 오늘이 아닙니다 (2026-09-28)"
    severity: Literal["reject", "review", "retry"]
    details: dict = field(default_factory=dict)  # 디버깅용 상세
```

**severity 세 단계:**

- `"reject"` — 자동 거부. 사람이 볼 필요 없이 명백한 실패 (중복 제출 등).
- `"review"` — 운영진 수동 확인으로 넘김. 애매한 케이스 (confidence 낮음, fuzzy 매칭 경계선).
- `"retry"` — 사용자에게 재촬영/재제출을 요청. 추출 자체가 부실했던 케이스.

**왜 Verifier가 Failure 대신 VerifyOutput을 반환하는가:** 이전 설계는 통과하면 `None`, 실패하면 `Failure`를 반환했다. 문제는 "통과했지만 알아두면 유용한 정보"(예: 어떤 상점 ID로 매칭됐는지)를 버릴 곳이 없었다는 것. `VerifyOutput`으로 감싸서 통과/실패와 무관하게 `metadata`를 실어보낼 수 있게 했다.

### 내장 Verifier 목록

```python
class DateVerifier(Verifier):
    """결제일이 기준일로부터 N일 이내인지."""
    def __init__(self, max_age_days: int = 0, reference_date: date | None = None,
                 severity: Literal["reject", "review", "retry"] = "reject"):
        # max_age_days=0: 당일만 허용
        # reference_date=None: 오늘 기준
        ...

class StoreVerifier(Verifier):
    """상호명 또는 사업자번호가 허용 목록에 있는지.
    허용 목록은 요청마다 바뀔 수 있는 동적 데이터이므로 생성자가 아니라
    context["allowed_stores"]로 받는다. context에 키가 없으면 ValueError.
    """
    def __init__(self, match_by: Literal["name", "business_number"] = "name",
                 fuzzy: bool = True, threshold: float = 0.8,
                 severity: Literal["reject", "review", "retry"] = "reject"):
        # fuzzy=True: 유사도 매칭. "막걸리계보" vs "막걸리 계보" 통과
        # threshold: fuzzy 매칭 임계값
        ...
    # 통과 시 metadata={"matched_store": "<allowed 목록에서 매칭된 원문>"} 반환

class AmountVerifier(Verifier):
    """결제 금액이 범위 내인지."""
    def __init__(self, min_amount: int | None = None, max_amount: int | None = None,
                 severity: Literal["reject", "review", "retry"] = "review"):
        ...

class DuplicateVerifier(Verifier):
    """같은 영수증 중복 제출 감지. 항상 reject."""
    def __init__(self, store: DuplicateStore):
        # store: 승인번호 또는 이미지 해시 저장소 인터페이스
        # 체크 순서: approval_number > image_hash
        ...

class ConfidenceVerifier(Verifier):
    """
    전체 confidence(meta.confidence, Gemini의 self-report 값)가 임계값 미만이면
    review로 넘긴다. 필드별 신뢰도(field_confidence)는 스키마에서 제거했으므로 다루지 않는다.
    기본 severity가 "review"인 이유: self-report 값은 근거가 약해서 자동 거부의
    근거로 쓰기엔 부적절하다 — 사람이 한 번 보게만 한다.
    """
    def __init__(self, min_confidence: float = 0.6,
                 severity: Literal["reject", "review", "retry"] = "review"):
        ...

class RequiredFieldVerifier(Verifier):
    """특정 필드가 None이 아닌지. severity 기본값이 reject인 이유는
    이 Verifier를 넣는다는 것 자체가 "이 필드는 없으면 절대 안 됨"이라는 의도이기 때문."""
    def __init__(self, fields: list[FieldPath], severity: Literal["reject", "review", "retry"] = "reject"):
        ...
```

### DuplicateStore 인터페이스

```python
class DuplicateStore(ABC):
    """중복 체크용 저장소. 서비스마다 구현 다름."""
    @abstractmethod
    async def check_and_mark(self, key: str) -> bool:
        """key가 이미 존재하면 False(중복)를 반환한다.
        존재하지 않으면 저장한 뒤 True(신규)를 반환한다.
        exists()+save() 두 번 호출로 구현하면 그 사이에 동시 요청이 끼어들어
        같은 영수증이 동시에 두 번 통과하는 race condition이 생긴다.
        구현체는 반드시 이 두 동작을 원자적으로 묶어야 한다
        (SQLite: UNIQUE 제약 + INSERT 실패 캐치, Redis: SETNX)."""
        ...

class SQLiteDuplicateStore(DuplicateStore):
    """SQLite 기반. 소규모 서비스용. UNIQUE 제약으로 원자성 확보."""
    ...

class RedisDuplicateStore(DuplicateStore):
    """Redis 기반. 대규모 서비스용. SETNX로 원자성 확보."""
    ...
```

---

## 컨텍스트 키 상수

`context` dict에 넣는 키도 매직 스트링을 피한다.

```python
class ContextKey(str, Enum):
    ALLOWED_STORES = "allowed_stores"   # StoreVerifier가 사용
```

---

## ReceiptEngine — 조립

```python
class ReceiptEngine:
    def __init__(
        self,
        extractor: ReceiptExtractor,
        verifiers: list[Verifier],
        cache: ResultCache | None = None,
    ):
        self.extractor = extractor
        self.verifiers = verifiers
        self.cache = cache

    async def process(self, image: bytes, context: dict | None = None) -> ProcessResult:
        context = context or {}
        image_hash = hash_image(image)

        data = await self.cache.get(image_hash) if self.cache else None
        if data is None:
            data = await self.extractor.extract(image)
            data.meta.image_hash = image_hash
            if self.cache:
                await self.cache.set(image_hash, data)

        outputs: dict[str, VerifyOutput] = {}
        for v in self.verifiers:
            outputs[v.name] = await v.verify(data, context)

        return ProcessResult(
            receipt=data,
            status=_aggregate_status(outputs),
            outputs=outputs,
        )


def _aggregate_status(outputs: dict[str, VerifyOutput]) -> Literal["approved", "rejected", "review", "retry"]:
    failures = [o.failure for o in outputs.values() if not o.passed]
    if not failures:
        return "approved"
    severities = {f.severity for f in failures}
    if "reject" in severities:
        return "rejected"
    if "retry" in severities:
        return "retry"
    return "review"


@dataclass
class ProcessResult:
    receipt: ReceiptData
    status: Literal["approved", "rejected", "review", "retry"]
    outputs: dict[str, VerifyOutput]   # verifier.name -> VerifyOutput

    @property
    def failures(self) -> list[Failure]:
        return [o.failure for o in self.outputs.values() if o.failure is not None]
```

**status 우선순위가 reject > retry > review인 이유:** 하나라도 자동 거부 사유가 있으면 나머지가 review여도 최종 결과는 거부다. retry와 review가 섞이면, "재촬영이 필요하다"는 게 "사람이 봐야 한다"보다 사용자에게 더 즉각적인 액션을 요구하므로 우선한다.

---

## 서비스별 사용 예시

### 멈춰, 섬!

```python
engine = ReceiptEngine(
    extractor=ReceiptExtractor(api_key=GEMINI_KEY),
    verifiers=[
        RequiredFieldVerifier(fields=[FieldPath.STORE_NAME]),
        ConfidenceVerifier(min_confidence=0.6),
        DateVerifier(max_age_days=0),
        StoreVerifier(fuzzy=True, threshold=0.7),
    ],
    cache=InMemoryResultCache(),
)

result = await engine.process(
    image,
    context={ContextKey.ALLOWED_STORES: get_active_shop_names()},
)
```

### 경비 처리 시스템

```python
engine = ReceiptEngine(
    extractor=ReceiptExtractor(api_key=GEMINI_KEY),
    verifiers=[
        RequiredFieldVerifier(fields=[FieldPath.STORE_NAME, FieldPath.TOTALS_TOTAL, FieldPath.TRANSACTION_DATE]),
        DateVerifier(max_age_days=30),
        AmountVerifier(min_amount=1000, max_amount=500000),
        DuplicateVerifier(store=RedisDuplicateStore(redis_client)),
    ],
    cache=RedisResultCache(redis_client),
)

result = await engine.process(image)
```

---

## 모듈 구조

```
receipt_ocr/
├── __init__.py           # ReceiptEngine, ReceiptExtractor export
├── schema.py             # ReceiptData, StoreInfo, TransactionInfo, LineItem, Totals, ExtractionMeta
├── constants.py          # FieldPath, ContextKey enum
├── hashing.py            # hash_image()
├── extractor.py          # ReceiptExtractor (Gemini Flash)
├── cache.py              # ResultCache ABC, InMemoryResultCache, RedisResultCache
├── engine.py             # ReceiptEngine, ProcessResult, _aggregate_status
├── errors.py             # ExtractionError, NotReceiptError, RateLimitError
└── verifiers/
    ├── __init__.py        # Verifier ABC, VerifyOutput, Failure export
    ├── date.py            # DateVerifier
    ├── store.py           # StoreVerifier (fuzzy matching 포함)
    ├── amount.py          # AmountVerifier
    ├── duplicate.py       # DuplicateVerifier + DuplicateStore ABC
    ├── confidence.py      # ConfidenceVerifier
    └── required.py        # RequiredFieldVerifier
```

---

## 구현 순서

1. `schema.py`, `constants.py`, `hashing.py` — 데이터 클래스 + 필드/컨텍스트 상수 정의
2. `errors.py` — 예외 계층
3. `extractor.py` — Gemini Flash 연동 + 프롬프트 설계 + 재시도/타임아웃/동시성
4. `verifiers/__init__.py` — Verifier ABC, VerifyOutput, Failure
5. `verifiers/date.py`, `verifiers/store.py`, `verifiers/required.py` — 멈춰,섬!에 당장 필요한 것만 먼저
6. `engine.py` — 조립 (캐시 없이 우선)
7. `cache.py` — InMemoryResultCache부터. Redis는 필요해지면
8. 나머지 Verifier(`amount.py`, `duplicate.py`, `confidence.py`)는 필요할 때
