# OCI 인프라 지식베이스

> 백엔드 배포(OCI 인스턴스) 관련 지식/학습/결정사항을 시간순으로 기록한다.
> 목적: 인프라 에이전트(추후 스킬화)가 참조할 단일 진실. 결정의 "왜"를 반드시 남긴다.

## 원칙

- **0원 제약이 최우선.** 가용성/편의성보다 "돈이 한 푼도 안 나가는 것"이 항상 우선한다.
- 오픈 이슈(실측 필요한 값 등)는 결론처럼 적지 않고 **미확인 상태로 명시**한다.

## 계정/과금 기본

- **Always Free**: 계정 수명 동안 영구 무료. 홈 리전에서만 적용되고, **홈 리전은 가입 후 변경 불가**.
- **Free Trial**: 30일 $300 크레딧, Always Free와 별개.
- **PAYG 전환 후에도 Always Free는 유지**되지만, 한도를 초과하면 **자동으로 유료 과금**됨 (하드 차단 없음).
- 안전장치: PAYG 전환 전 **Budget Alert를 $0으로 설정** 필수.

## Always Free 리소스 한도

| 리소스 | 한도 | 비고 |
|---|---|---|
| Compute A1.Flex (ARM) | 1,500 OCPU-h + 9,000 GB-h/월 | 상시 가동 기준 공식 문서상 2 OCPU/12GB. **커뮤니티 보고는 4 OCPU/24GB로 엇갈림 — 콘솔에서 실측 필요 (오픈 이슈)** |
| Compute E2.1.Micro (AMD) | 최대 2대, 각 1/8 OCPU + 1GB | |
| Container Instances (A1.Flex 셰이프) | 위 Compute A1.Flex 한도 공유 | AWS Fargate 대응 서비스. 서버리스, 노드 관리 불필요 |
| OKE 컨트롤 플레인 (Basic) | 무료 | **Enhanced는 시간당 $0.10, 월 최대 $74.40 — 선택 금지** |
| Block Volume | 200GB (부트+블록 합산) | 홈 리전에서 생성해야 Always Free 인정 |
| Load Balancer | Flexible LB 1개 (10Mbps) | HA 구성 시 사용 |
| Egress 대역폭 | 10TB/월 | 초과 시 과금 |

## 리전 결정

- **홈 리전: 오사카(ap-osaka-1)**
- 오사카는 상용 리전이며 Always Free 지원 확인됨.
- ARM(A1.Flex)은 한국 춘천 리전만 제외하고 전 리전 생성 가능 → 오사카 문제없음.
- 가입 직후 소규모 테스트 인스턴스로 실제 Always Free 생성 가능 여부 검증 권장.

## 아키텍처 결정 로그

### 2026-07-19 — 쿠버네티스(OKE) 대신 단일 노드 채택

**결정**: OKE(쿠버네티스) 대신 **단일 A1.Flex 노드 + 컨테이너 자체 재시작 정책**(Docker restart policy 또는 Container Instances)으로 간다.

**왜**:
- K8s는 노드 장애 시 "새 노드를 프로비저닝"해서 파드를 재배치하는 게 핵심 가치인데, 그러려면 장애 발생 순간 죽은 노드+뜨는 새 노드가 동시에 존재해야 함 → 프리티어 한도를 이미 꽉 채워 쓰고 있으면 이 순간 한도 초과 (PAYG는 초과분을 자동 과금).
- 이 규모(개인 프리티어, 워커노드 1~2대)에서는 K8s의 "여러 노드 걸친 재배치" 이점을 실현할 여유 자체가 없고, kubelet/kube-proxy 등 자체 오버헤드가 빠듯한 자원을 더 갉아먹음.
- 컨테이너 레벨 장애(앱 크래시, 프로세스 OOM)는 K8s 없이도 restart policy만으로 충분히 커버 가능 — 이게 실제 장애의 대부분.
- 노드 레벨 장애(호스트 장애, 커널 패닉)는 발생 빈도가 낮고, "같은 인스턴스를 재부팅"(새 인스턴스 생성 아님)으로 대응하면 다운타임은 있어도 비용은 안 듦.

**트레이드오프**: 무중단(HA)은 포기. 다운타임 감수 + 비용 0원을 선택.

**HA가 정말 필요해지면**: 노드를 늘리는 게 아니라 **처음부터 상시 2개 노드(1 OCPU/6GB씩)로 쪼개서 운영 + OCI Flexible LB(Always Free 1개)로 헬스체크 라우팅**하는 구조를 쓸 것. "장애 후 새로 띄우기"가 아니라 "상시 이중화"라야 한도 초과가 안 생김. (아직 미채택 — 필요 시 재검토)

### 2026-07-19 — Fargate 대응 서비스 확인

**결정**: AWS Fargate에 해당하는 OCI 서비스는 **Container Instances**. A1.Flex 셰이프 사용 시 Always Free 적용, 초 단위 과금(최소 1분).

### 2026-07-19 — 메모리 격리 vs HA 구분

- 컨테이너별 memory limit(cgroup)은 **장애 격리** 수단이지 HA 수단이 아님. 한 컨테이너의 메모리 폭주가 노드 전체를 끌고 죽는 걸 막을 뿐, 노드 자체가 죽는 상황은 못 막음.
- 진짜 HA는 장애 도메인 분리(다중 노드)가 필요하고, 이는 위 "상시 2노드" 구조로만 0원 제약과 공존 가능.

### 2026-07-19 — 노드 확보: Out of host capacity, 재시도 전략

**관찰**: 오사카 리전 A1.Flex(ARM) launch 요청 시 `500 InternalError: Out of host capacity` 반복 발생. 프리트라이얼/PAYG 무관하게 동일 — **과금·권한 문제가 아니라 물리 서버 재고 부족**. 실패한 요청은 리소스가 생성되지 않으므로 비용 0원.

**제약**: 오사카는 가용성 도메인(AD)이 1개뿐(`WOFR:AP-OSAKA-1-AD-1`)이라 AD를 바꿔 재시도하는 우회가 불가능.

**전략**: 성공할 때까지 자동 재시도(`infra/scripts/launch-retry.sh`). 보수적으로 **1 OCPU/6GB로 먼저 확보 → 이후 2 OCPU/12GB로 리사이즈**. 재시도 스크립트는 "Out of host capacity"만 재시도하고, 그 외 에러(과금/권한 등)는 즉시 멈춰 사람이 보게 함.

### 2026-07-19 — 고정(예약) 공인 IP: 무료로 결론

**결정**: 노드가 재부팅/정지돼도 주소가 안 바뀌게 **Reserved Public IP**를 쓴다. **비용은 0원으로 판단**.

**근거**:
- OCI 공식 문서·공식 블로그: 공인 IP(ephemeral/reserved 모두) 자체에 과금 SKU 없음. OCI는 AWS와 달리 공인 IPv4에 시간당 요금을 매기지 않음.
- Always Free 구성에 공인 IP 포함(무료 A1 인스턴스에 공인 IP 붙는 것 자체가 무료).
- **이견 소스 주의**: 일부 검색 요약이 "reserved IP는 미연결 상태에도 $0.01/시간 과금"이라고 했으나, 이는 **AWS Elastic IP(미사용 시 과금) 정책과 혼동한 것**으로 판단. OCI 공식 가격표에 public IP 과금 항목이 존재하지 않음.
- **안전장치**: Budget Alert가 $1로 걸려 있어, 만에 하나 과금이 발생하면 즉시 이메일 알림 → 바로 대응 가능.

**주의(운영 규칙)**:
- ephemeral → reserved 로 **같은 주소를 전환 불가**. 처음부터 reserved로 할당해야 함.
- reserved IP는 인스턴스가 terminate돼도 테넌시 풀에 남음. 더 이상 안 쓰면 명시적으로 삭제(그래야 혹시 모를 과금·낭비 방지). Always Free reserved public IP는 1개 한도.

### 2026-07-19 — PAYG 전환 완료

트라이얼 → PAYG 전환 완료(사용자 직접, 카드 등록). 전환 전 Budget Alert $1(사실상 최소치) + 최소 임계 알림 설정 완료. Always Free 한도 내 0원 운영 유지, 초과 시 이메일 알림.

### 2026-07-19 — 백엔드 컨테이너화 완료 (배포는 노드 대기)

**구조** (`backend/` self-contained, git 추적):
- `backend/Dockerfile` — python:3.13-slim, 시작 시 `init_db`(멱등) → uvicorn. `DATABASE_URL=sqlite:////data/app.db`로 DB를 볼륨에.
- `backend/docker-compose.yml` — `restart: unless-stopped`(컨테이너 크래시·노드 재부팅 자동 복구), `./data:/data` 볼륨 영속화, `.env` env_file, healthcheck(`/api/health`).
- `backend/.env.example` — ADMIN_PASSWORD/CORS_ORIGINS/GEMINI_API_KEY. 실제 `.env`는 노드에만(git 제외).
- `backend/.dockerignore` — venv/tests/app.db 등 제외.

**코드 변경(설정 외부화, 기본값 유지로 기존 동작 무손상, 테스트 133개 통과)**:
- `app/db.py` — `DATABASE_URL` 환경변수화(기본 `sqlite:///app.db`).
- `app/main.py` — `CORS_ORIGINS` 환경변수화(콤마 구분, 기본 localhost:5173).

**배포 런북** (노드 확보 후):
1. 노드에 git clone/pull → `backend/`
2. `cp .env.example .env` 후 실제 값 채우기 (ADMIN_PASSWORD, CORS_ORIGINS=Vercel도메인, GEMINI_API_KEY)
3. `docker compose up -d --build` (arm64 노드에서 직접 빌드)
4. 뗐다 붙이기: `docker compose down`(데이터는 ./data 유지) / `up -d`

**자동 복구(태스크 4)**: compose `restart: unless-stopped`로 충족. 컨테이너 죽으면 Docker가 재시작, 노드 재부팅되면 Docker 데몬이 다시 기동. (앞서 논의한 "노드 자체 죽으면 재부팅으로 복구, 컨테이너 죽으면 자동 재시작" 그대로.)

### 2026-07-19 — 미해결 설계: 프론트(HTTPS)↔백엔드(HTTP) mixed content

**문제**: Vercel 프론트는 HTTPS로 서빙됨. HTTPS 페이지에서 `http://<고정IP>:8000`으로 `fetch` 하면 브라우저가 **mixed active content로 차단**함. 즉 **고정 공인 IP만으로는 프론트-백 연결이 안 됨** — 백엔드도 HTTPS가 필요.

**추가 문제**: Let's Encrypt는 raw IP에 인증서를 발급하지 않음 → **도메인(호스트네임)이 필요**.

**선택지 (미결정, Tom 확인 필요)**:
- (A) 백엔드용 도메인 확보 + 노드에 nginx(리버스 프록시) + Let's Encrypt 인증서. 도메인은 무료 옵션(예: DuckDNS 등) 또는 보유 도메인 서브도메인.
- (B) Cloudflare를 백엔드 앞에 무료로 두고 TLS 종단 + 호스트네임 제공. 오리진은 Cloudflare Origin Cert 또는 Full 모드.
- (C) Cloudflare Tunnel(cloudflared 컨테이너)로 노드에 인바운드 포트 오픈 없이 HTTPS 호스트네임 노출. 고정 공인 IP 자체가 불필요해질 수도 있음(재검토 포인트).

→ **이게 정해져야 태스크 5(프론트-백 연결)와 고정 IP의 실제 필요성이 확정됨.** 특히 (C)를 택하면 Reserved Public IP가 필요 없어질 수 있으므로, IP 예약 실행 전에 이 결정을 먼저 내리는 게 맞음.

**결정 (2026-07-19, Tom)**: (A) 도메인 + nginx + Let's Encrypt 채택.

**함의/후속**:
- **고정(Reserved) 공인 IP 확정 필요** — 도메인 A레코드가 노드 IP를 가리키는데, 노드 재부팅 시 ephemeral IP는 바뀔 수 있어 DNS가 깨짐. reserved IP로 주소를 고정해야 함. (앞선 조사대로 무료.)
- **도메인 필요** — Tom이 보유 도메인의 서브도메인(예: api.도메인) 또는 무료 DDNS(DuckDNS 등) 제공 필요. **미확정 — Tom 입력 대기.**
- **구성**: 노드 compose에 nginx(리버스 프록시) + certbot(Let's Encrypt) 추가. nginx가 443 TLS 종단 → 내부 backend:8000으로 프록시. 인증서 자동 갱신(certbot renew).
- **방화벽**: OCI Security List에 443(및 certbot HTTP-01 챌린지용 80) 인그레스 개방 필요. 현재 테스트 SL은 22만 열려 있음 → 80/443 추가 필요.

### 2026-07-19 — 노드 확보·리사이즈·예약IP 완료 (실물 정보)

- **인스턴스**: `stop-island-node`, VM.Standard.A1.Flex, **2 OCPU / 12GB**, Ubuntu 24.04 aarch64, RUNNING.
  - OCID: `ocid1.instance.oc1.ap-osaka-1.anvwsljri2gw3nicnyc6ter522jmvl6jhi5tpm4vdl45dejwn6ayittp3l4a` (`infra/scripts/node.ocid`)
- **리사이즈**: 1/6 → 2/12 성공. 우려했던 재부팅-용량부족 없이 완료(CLI는 2분 타임아웃 났지만 실제로는 성공, get으로 확인). **교훈: `--wait-for-state`가 CLI 타임아웃 나도 작업은 서버에서 계속되니 get으로 재확인할 것.**
- **예약 공인 IP**: `129.225.170.51` (RESERVED, ASSIGNED). 재부팅에도 불변. (`infra/scripts/node.public-ip`)
  - Reserved IP OCID: `ocid1.publicip.oc1.ap-osaka-1.amaaaaaai2gw3niaa72kvqajs3zvjr3pgtd6p2u4mgktqih2ifnegvtqyciq`
  - **교훈: `network public-ip create --lifetime RESERVED --private-ip-id <priv>`가 어렵게 사설IP에 붙는다. 기존 ephemeral을 먼저 delete해야 함(사설IP당 공인IP 1개). jq 파싱 에러가 나도 create 자체는 성공했을 수 있으니 get으로 재확인.**
- **네트워크**: VCN 10.0.0.0/16, 서브넷 10.0.0.0/24, IGW+라우트, Security List 인그레스 **22/80/443** 개방.
- **호스트 방화벽**: Oracle Ubuntu 이미지는 기본 iptables가 22 외 포트를 DROP. **노드 내부에서 80/443 ACCEPT 규칙을 iptables에 추가하고 netfilter-persistent로 영속화해야 외부 접근됨** (SL만 열면 안 됨 — 이중 방화벽).
- **Docker**: 29.6.2 설치됨, ubuntu 사용자 docker 그룹 추가.
- **SSH**: `ssh -i infra/credentials/instance_ssh_key ubuntu@129.225.170.51`

### 2026-07-19 — 도메인 결정

- **도메인**: `leafeep.com` (Tom 보유, 등록기관 hosting.co.kr, 네임서버 ns1~4.hosting.co.kr). 백엔드는 **`si.leafeep.com`** 서브도메인 사용 예정.
- **DNS는 OCI로 위임돼 있지 않음** → A레코드(api → 129.225.170.51)는 **hosting.co.kr DNS 관리 콘솔에서 Tom이 직접 추가**해야 함. certbot(Let's Encrypt HTTP-01)이 이 이름 해석에 의존하므로 인증서 발급 전 선행 필요.

### 2026-07-19 — FE↔BE 연동 완료 (실브라우저 검증)

- DNS: `si.leafeep.com` A레코드 → 129.225.170.51 (hosting.co.kr, Tom 추가) 전파 확인.
- HTTPS: `enable-ssl.sh` 실행 → Let's Encrypt 인증서 발급(만료 2026-10-17) → nginx api-ssl.conf 전환 → 갱신 루프 기동. `https://si.leafeep.com/api/*` 정상.
- CORS: `CORS_ORIGINS=https://stop-island.vercel.app` 반영. 프리플라이트/실요청 모두 ACAO 정상.
- 프론트: `frontend/.env.production`(VITE_API_BASE=https://si.leafeep.com) main에 push → Vercel 재빌드 → 새 번들이 si.leafeep.com 참조 확인.
- **실브라우저 검증**: stop-island.vercel.app 로드 → 메인 진입 시 `/api/status`·`/api/seats` 200 실데이터, 콘솔 에러 0, "빈 자리 6석" 렌더링.
- git: main에 2커밋(프론트/백엔드 분리) push. docs(context/infra/*)는 정책상 커밋 제외(Tom 관리).

**전체 체인 라이브**: 브라우저 → Vercel(HTTPS) → si.leafeep.com → OCI SL+iptables → nginx(TLS) → backend → SQLite. **0원 운영.**

### 2026-07-19 — 멀티서비스 공용 엣지 구조로 리팩토링

**결정**: 한 노드에 여러 서비스를 담기 위해 nginx+certbot을 stop-island 전용에서 **노드 공용 엣지**로 승격.

**왜**: 포트 80/443은 노드에서 하나만 소유 가능 → 서비스마다 nginx를 두면 충돌. 공용 엣지가 서브도메인(server_name)으로 각 서비스 컨테이너에 라우팅해야 여러 HTTPS 서비스가 한 IP/노드에 공존 가능.

**노드 구조**:
```
/home/ubuntu/
├── edge/                  # 공용 엣지(edge-nginx + edge-certbot). 80/443 소유
│   ├── docker-compose.yml
│   ├── conf.d/<도메인>.conf # add-service.sh가 생성 (si.leafeep.com.conf)
│   ├── templates/          # service-http/ssl.conf.tmpl
│   ├── scripts/            # edge-up.sh, add-service.sh
│   └── certbot/{conf,www}  # 모든 도메인 인증서 공유
└── services/
    └── stop-island/        # backend만(expose 8000), 외부 네트워크 'edge' 조인
```

- 공용 외부 docker 네트워크 `edge`. nginx·모든 서비스가 조인 → 컨테이너 이름으로 프록시(`stop-island-backend:8000`).
- 서비스는 호스트 포트 안 염(expose만). 외부 노출은 엣지 HTTPS 경유만.
- **새 서비스 추가 = 3스텝**: services/에 배치(edge 조인) → `add-service.sh <도메인> <컨테이너:포트>` → 검증. 상세는 스킬 `.claude/skills/infra-agent/SKILL.md`.

**이전 실행 메모**:
- 인증서 root 소유 심링크라 cp 재사용 실패 → 복사 대신 add-service.sh가 **재발급**(Let's Encrypt 재발급, 레이트리밋 여유). 데이터(app.db)는 sudo cp로 이관·검증.
- 다운타임 최소화: 새 이미지 선(先)빌드 → 구 스택 down → 새 backend up → edge up → add-service(재발급). 실측 ~1~2분.
- 구 `/home/ubuntu/backend/` 제거(검증 후). 현재 컨테이너: edge-nginx, edge-certbot, stop-island-backend.
- 인증서 갱신 후 nginx reload는 **호스트 cron**(매일 03:15 `docker exec edge-nginx nginx -s reload`)이 담당(edge-up.sh가 설치).

**스킬화**: `.claude/skills/infra-agent/` 생성 — OCI 조작 규칙 + 멀티서비스 플레이북 + edge/service 템플릿 + add-service/edge-up 스크립트. 인프라 작업의 진입점.

### 2026-07-20 — 이중화(HA) 정책 설계 (초안, 미확정)

**배경**: 오사카 단일 노드는 현재 정상 가동 중(실제 장애 이력 없음). 다만 팝업 라이브 기간(9/30~10/6) 고가용성이 필요하다는 Tom 판단으로 3단계 이중화(오사카→도쿄→노트북)를 명시적으로 요청받음. 이는 앞서 "무중단(HA)은 포기, 0원 우선" 결정(위 2026-07-19 "쿠버네티스(OKE) 대신 단일 노드 채택" 항목)을 재검토하는 것.

**전제**: 도쿄 인스턴스는 **별도 OCI 계정(테넌시)**에서 이미 가동 중. 그 계정 홈 리전이 도쿄면 Always Free 적용되어 추가 비용 없음 — 단 스펙/기존 용도는 미확인.

**설계(제안, Tom 검토 대기 — 아직 구현 안 됨)**:
- 아키텍처: 오사카(Primary, Active) → 도쿄(Secondary, Warm Standby, litestream 복제본 대기) → 노트북(Tertiary, Cold, 수동 승격)
- 트래픽 라우팅: DNS를 Cloudflare(무료 플랜)로 이관 + UptimeRobot(무료) 헬스체크 + webhook 기반 A레코드 자동 전환, TTL 60s. hosting.co.kr엔 API 기반 페일오버가 없어 이 조합이 0원으로 흉내내는 표준적 방법.
- 데이터 복제: **Litestream**(오픈소스, 무료)으로 오사카 SQLite WAL을 도쿄로 지속 스트리밍. DNS만 바꾸고 데이터 복제를 안 하면, 페일오버해도 도쿄엔 예약/방명록 데이터가 없어 반쪽짜리 HA가 됨 — 이게 이 설계의 핵심 리스크 지점.
- 노트북 계층: Cloudflare Tunnel(아웃바운드 전용)로 한국 통신사 CGNAT(인바운드 차단) 우회. 자동화 대상 아님 — 사람이 노트북 켜고 온라인이어야 의미 있어 런북(수동 절차)으로 문서화.
- 페일백: 오사카 복구돼도 자동으로 되돌리지 않음(전환 중 도쿄/노트북에 쌓인 쓰기 데이터 병합 문제 때문) — 사람이 판단해서 수동 전환.

**오픈 이슈(미확인 — 구현 전 Tom 확인 필요)**:
- [ ] 도쿄 인스턴스 스펙/현재 용도(다른 워크로드 여부, 여유 자원 있는지)
- [ ] DNS Cloudflare 이관 범위 — `leafeep.com` 전체 vs `si.leafeep.com` 서브도메인만 NS 위임(hosting.co.kr 지원 여부 확인 필요)
- [ ] Litestream 도입 여부 vs 더 단순한 주기적 rsync 백업(RPO 트레이드오프, litestream은 신규 컴포넌트라 학습/검증 비용 있음)
- [ ] 완전자동 전환 vs 반자동(알림만 자동화, 전환은 사람이 트리거) — 완전자동은 오탐/플래핑으로 인한 불필요한 스위칭 리스크

→ 이슈 트래킹: GitHub 이슈 `[HA]`로 등록 예정.

### 2026-07-21 — HA 정책 보완: DB를 오사카 내 별도 인스턴스로 분리 (문서만, 미구현)

**결정**: 백엔드 앱과 SQLite DB를 같은 인스턴스에 두지 않고, **DB 전용 인스턴스를 오사카 안에 별도로 둔다**. 도쿄/노트북으로 분산하지 않고 **RW 소스는 오사카 DB 인스턴스 하나로 유지**한다.

**왜**:
- 앱과 DB가 같은 인스턴스에 있으면 앱 배포/재시작/장애가 DB 가용성에 직접 영향을 줌. 분리하면 blast radius가 줄고, litestream 복제 소스(DB 인스턴스)와 앱 프로세스가 서로 얽히지 않음.
- 기존 HA 정책(도쿄 Warm Standby, 노트북 Cold)의 방향 전환이 아니라 확장임 — 오사카 쪽 아키텍처만 App/DB 2계층으로 나뉘고, litestream이 오사카-DB → 도쿄-DB로 복제하는 흐름은 그대로 유지.

**비용**: 오사카 Always Free 한도(2 OCPU/12GB, 위 "노드 확보·리사이즈·예약IP" 항목 참고)를 App 인스턴스 + DB 인스턴스로 쪼개서 쓰면 추가 비용 없음(예: 1 OCPU/6GB씩). 이건 2026-07-19 "HA가 정말 필요해지면 상시 2노드로 쪼개서" 메모와 같은 맥락. 단, 인스턴스 신규 확보 시 "Out of host capacity" 재시도가 필요할 수 있음(위 기존 함정 참고).

**남은 리스크(명시적으로 해소 안 됨)**: DB 인스턴스 자체가 오사카에만 있으므로, 오사카 리전 전체 장애 시 DB 인스턴스도 함께 죽는다. 도쿄/노트북은 litestream 복제본을 RW로 승격하는 시나리오이지, "오사카 DB에 원격 접속"하는 구조가 아니다 — 이 부분은 기존 오픈 이슈(litestream 도입 여부)와 함께 확정 필요.

**이슈 반영**: GitHub 이슈 #14 본문(아키텍처 다이어그램/컴포넌트 표/할일) 갱신 완료.

### 2026-07-22 — HA 정책: 스코프 확정 (도쿄 확보 완료, DB 원격접속 방식은 보류)

**결정**:
- 도쿄 인스턴스 확보 완료 — "스펙/여유자원 미확인" 오픈 이슈 해소.
- 오사카 리전 전체 장애·DB 인스턴스 자체 장애는 대비 범위 밖으로 확정(Tom: "그거까지 고민하는 건 너무 많은 고민, 자연재해 걱정하는 수준"). 이 HA 설계가 막는 건 **오사카 App 장애**(배포 실패, 프로세스 크래시 등)까지이고, 오사카 DB/리전 자체 장애는 대비하지 않는다.
- SQLite 유지 안 함 — 추후 다른 DB로 마이그레이션 예정. 그에 따라 "도쿄/노트북 WAS가 오사카 DB에 원격 접속하는 구체적 방법"(Litestream vs NFS vs 기타)은 지금 결정 대상이 아님 — DB 마이그레이션 시점에 자연히 풀리는 문제로 보류.

**추가 결정 (2026-07-22)**:
- DNS 이관 범위: **`si.leafeep.com` 서브도메인만** Cloudflare로 이관. `leafeep.com` 전체는 건드리지 않음.
- 전환 방식(오사카→도쿄): **완전자동**으로 간다(오탐/반자동 절충안은 검토 대상 아님). 구체적 구현 방법(webhook 스크립트 등)은 착수 시점에 결정 — 지금 단계에서 다룰 내용 아님.
- 전환 방식(도쿄→노트북): 노트북을 켜는 것 자체는 사람이 해야 하지만(자동 감지·자동 기동 불가), **Cloudflare Tunnel 기동 + DNS 전환은 스크립트로 준비**해서 사람이 스크립트 1회 실행으로 끝나게 한다. 애드훅 수동 절차로 남겨두지 않는다.

이로써 HA 정책의 방향 결정(what)은 모두 확정. 남은 건 구현(how) 단계.

### 2026-07-23 — HA 정책 문서화·공개 + 정책 보강

**산출물**:
- `context/infra/ha-policy-gist.md` — HA 정책 명세(9장 구성: 개요→채택 근거→핵심 원칙→복구 목표→아키텍처→시나리오→SPOF→대비 범위 제외→검증). 공개 기스트의 원본.
- 공개 기스트: https://gist.github.com/xhae123/a0b4b353e29475754ebf857ae0b7495b (xhae123 계정, public, 파일명 `stop-island-ha-policy.md`) — 외부 평가·멘토링용. 갱신 시 이 원본 파일을 수정 후 기스트에 반영.
- `README.md` 재구성 — 서비스 소개(화면·운영 조건·구성) + HA 정책 전문 수록.
- main 반영: `03b8c78` (feat/receipt-core를 ff 머지 후 브랜치 삭제 — receipt-core 커밋 `eb02d61` 포함).

**정책 보강 결정(Tom 승인)**:
- **채택 근거 프레임 수정**: "주 장애 원인이 배포"가 아님 — 운영 기간 중 코드 변경은 최소화한다. HA 도입 이유는 낮은 확률의 장애조차 발생 시 비용(현장 운영 중단, 7일 수명)을 수용할 수 없어서.
- **복구 목표(RTO/RPO)**: App 장애·동시 장애 모두 RPO=0(단일 DB의 구조적 효과). RTO는 리허설 실측으로 확정.
- **헬스체크 범위**: App 프로세스 응답만 검사, DB 연결은 제외 — 전 계층이 동일 DB를 쓰므로 DB 장애는 전환으로 해결 불가, 포함 시 불필요한 전환만 유발.
- **전환 로직 위치 원칙**: webhook→DNS 전환 로직은 보호 대상(오사카·도쿄) 외부에서 실행(예: Cloudflare Worker). 보호 장치가 보호 대상과 함께 죽는 순환 의존 배제. 구체 구현은 착수 시.
- **페일백 기준**: 오사카 복구 후 헬스체크 연속 통과 30분 관찰 → 수동 원복.
- **검증 계획**: 운영 개시 전 리허설 3종(1차 전환 강제 장애 / 2차 전환 노트북 절차 실측 / 페일백) — 검증 안 된 페일오버 경로는 없는 것으로 간주.
- **App 세트 원칙**: 백엔드 API + receipt-core는 동일 인스턴스에서 한 세트로 배포·전환(부분 전환 상태 배제).

**리뷰에서 확인된 갭(미해소)**:
- 영수증 이미지 저장소 — 업로드 이미지가 App 로컬 디스크라 페일오버 중 업로드분이 전환 대상 노드에만 남음. RPO=0 보장은 DB에만 성립. DB 마이그레이션 결정 시 함께 해소(이미지 DB 수납 or 중앙 저장소). → 오픈 이슈 등재.
- 도쿄 warm standby 버전 동기화 — 배포 시 오사카·도쿄 동시 배포 필요. 배포 스크립트에 반영할 것.
- 감지 지연 — UptimeRobot 무료 플랜 체크 간격 최소 5분이라 감지 지연이 지배적. Cloudflare 프록시(orange cloud)로 TTL 대기는 제거 가능. 구현 파라미터로 취급.

## 오픈 이슈

- [x] ~~노드 확보~~ 완료(2/12 리사이즈까지). 예약 IP 129.225.170.51 할당 완료.
- [x] ~~HTTPS 방식 결정~~ (A) 도메인+nginx+Let's Encrypt 채택. 도메인 si.leafeep.com.
- [x] ~~백엔드 이미지 빌드/기동 검증~~ 노드에서 완료, 인터넷 경유 HTTP로 /api/health·/api/status 응답 확인.
- [ ] **DNS A레코드 추가 필요** (사람) — si.leafeep.com → 129.225.170.51. hosting.co.kr 콘솔. 이거 있어야 certbot 발급 가능.
- [ ] **HTTPS 발급 미완** — DNS 후 노드에서 `backend/enable-ssl.sh` 실행.
- [ ] **Vercel 오리진 미확정** — CORS_ORIGINS 최종값 + `frontend/.env.production` push로 Vercel 재빌드 필요.
- [ ] Always Free A1.Flex 실제 한도가 2/12인지 4/24인지 콘솔 실측(현재 2/12로 운영 — 충분).
- [ ] 전용 IAM 사용자 + Compartment 분리 + 제한 정책 아직 미구성(현재 루트 자격증명 사용 중).
- [ ] infra-agent 스킬 미구현 — 이 KB/런북을 참조하는 스킬 스캐폴딩 예정.
- [ ] **영수증 이미지 저장소 중앙화** — 현재 App 로컬 디스크. 페일오버 중 업로드 이미지가 노드에 분산됨(DB만 RPO=0). DB 마이그레이션 결정 시 함께 해소.
- [ ] 배포 스크립트에 오사카·도쿄 동시 배포 반영 (warm standby 버전 동기화).

> 재현/마이그레이션 절차는 `context/infra/oci-runbook.md` 참조.

## 인프라 에이전트 운영에 필요한 것 (추후 셋업 시)

- Tenancy OCID, User OCID(전용 IAM 사용자), API 서명 키페어, Fingerprint, Region
- **키는 절대 레포에 커밋하지 않음** — `.claude/skills/infra-agent/` 하위 git-ignored `.local` 파일로 보관 (Figma PAT와 동일 패턴)
