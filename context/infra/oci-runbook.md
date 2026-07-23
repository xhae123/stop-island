# OCI 백엔드 배포 런북 / 마이그레이션 가이드

> 이 문서 하나로 백엔드 인프라를 **처음부터 재현**할 수 있게 한다(노드 날아가거나 다른 리전/계정으로 이전 시).
> 결정의 "왜"와 함정은 `oci-kb.md`에, **재현 절차는 여기**에 둔다. 시크릿은 여기 없음(전부 `infra/credentials/`, git 제외).

## 현재 실물 (2026-07-19)

| 항목 | 값 |
|---|---|
| 리전 / AD | ap-osaka-1 / WOFR:AP-OSAKA-1-AD-1 (AD 1개뿐) |
| 인스턴스 | `stop-island-node`, VM.Standard.A1.Flex, 2 OCPU / 12GB, Ubuntu 24.04 aarch64 |
| 인스턴스 OCID | `ocid1.instance.oc1.ap-osaka-1.anvwsljri2gw3nicnyc6ter522jmvl6jhi5tpm4vdl45dejwn6ayittp3l4a` |
| 예약 공인 IP | **129.225.170.51** (RESERVED, 재부팅 불변) |
| 예약 IP OCID | `ocid1.publicip.oc1.ap-osaka-1.amaaaaaai2gw3niaa72kvqajs3zvjr3pgtd6p2u4mgktqih2ifnegvtqyciq` |
| VCN / 서브넷 | 10.0.0.0/16 / 10.0.0.0/24 (public) |
| 방화벽(SL) | 인그레스 22, 80, 443 |
| 도메인 | si.leafeep.com → 129.225.170.51 (A레코드, hosting.co.kr에서 관리) |
| SSH | `ssh -i infra/credentials/instance_ssh_key ubuntu@129.225.170.51` |
| OCI CLI | `oci --config-file infra/credentials/config ...` (홈 리전 오사카) |

## 인증정보 (git 제외, `infra/credentials/`)

| 파일 | 용도 |
|---|---|
| `config` | OCI CLI 프로파일(user/tenancy/fingerprint/region/key_file) |
| `oci_api_key.pem` | OCI API 서명 개인키 |
| `instance_ssh_key`(.pub) | 노드 SSH 키페어 |
| `backend.env` | 노드 `backend/.env` 원본(ADMIN_PASSWORD 등) |

## 배포 아키텍처 (멀티서비스 공용 엣지)

```
브라우저(HTTPS)
  → Vercel 프론트 (VITE_API_BASE=https://si.leafeep.com)
  → si.leafeep.com (예약 IP 129.225.170.51)
  → OCI Security List(443) → 호스트 iptables(443)
  → edge-nginx 컨테이너 (443 TLS 종단, server_name 라우팅)   ← 노드 공용, 1개
  → stop-island-backend 컨테이너 (uvicorn :8000, FastAPI)     ← 서비스별
  → SQLite (/data/app.db, 볼륨 영속)
```

- **노드 구조**: `/home/ubuntu/edge/`(공용 nginx+certbot) + `/home/ubuntu/services/<서비스>/`(서비스별 backend).
- 공용 외부 네트워크 `edge`에 nginx·모든 서비스 조인. nginx가 서브도메인으로 `<서비스>-backend:8000`에 프록시.
- 컨테이너: `edge-nginx`, `edge-certbot`(공용) + `stop-island-backend`(서비스). 전부 `restart: unless-stopped`.
- 데이터: `services/stop-island/data/`, 인증서: `edge/certbot/`. 호스트 볼륨이라 컨테이너 재생성에도 보존.
- **새 서비스 추가·멀티서비스 운영은 스킬 참조**: `.claude/skills/infra-agent/SKILL.md`.

## 처음부터 재현하는 절차

### 0. 사전
- OCI 계정(PAYG), 홈 리전 오사카, Budget Alert $1 설정.
- 로컬에 `oci` CLI, `jq`, `rsync`, `ssh`.
- `infra/credentials/config` + `oci_api_key.pem` 준비(콘솔 API Key 발급 → fingerprint는 `openssl rsa -pubout -outform DER -in key.pem | openssl md5 -c`).

### 1. 네트워크 (스크립트화 가능 — `infra/scripts/`에 조각 있음)
```
oci network vcn create --cidr-block 10.0.0.0/16 ...
oci network internet-gateway create --is-enabled true ...
oci network route-table create --route-rules '[{destination:0.0.0.0/0, networkEntityId:<IGW>}]' ...
oci network security-list create --ingress '[22,80,443 TCP]' --egress '[all]' ...
oci network subnet create --cidr-block 10.0.0.0/24 --route-table-id <RT> --security-list-ids [<SL>] ...
```

### 2. 노드 확보 (핵심 함정: Out of host capacity)
- 오사카 A1.Flex는 재고 부족이 상시. **`infra/scripts/launch-retry.sh`로 재시도**.
- 보수적으로 **1 OCPU/6GB로 먼저 확보 → `compute instance update --shape-config {ocpus:2,memoryInGBs:12} --force`로 리사이즈**.
- SSH 공개키를 metadata `ssh_authorized_keys`로 주입. 이미지: Ubuntu 24.04 aarch64.
- **함정**: `--wait-for-state`가 CLI에서 타임아웃 나도 서버 작업은 계속됨 → `instance get`으로 재확인.

### 3. 예약 공인 IP
```
# 사설IP OCID 구하기
VNIC=$(oci compute instance list-vnics --instance-id <NODE> | jq -r '.data[0].id')
PRIV=$(oci network private-ip list --vnic-id $VNIC | jq -r '.data[0].id')
# 기존 ephemeral 삭제(사설IP당 공인IP 1개 제약)
EPH=$(oci network public-ip get --private-ip-id $PRIV | jq -r '.data.id')
oci network public-ip delete --public-ip-id $EPH --force
# reserved 생성+할당
oci network public-ip create --compartment-id <TENANCY> --lifetime RESERVED --private-ip-id $PRIV
```
- **함정**: jq 파싱 에러가 나도 create 자체는 성공했을 수 있음 → `public-ip get --private-ip-id`로 재확인.

### 4. 호스트 방화벽 (OCI SL만으로 부족)
- Oracle Ubuntu 이미지는 기본 iptables가 22 외 DROP. 노드에서:
```
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo apt-get install -y netfilter-persistent iptables-persistent
sudo netfilter-persistent save
```

### 5. Docker + 코드 배포
```
# 노드: curl -fsSL https://get.docker.com | sudo sh ; sudo usermod -aG docker ubuntu
# 로컬 → 노드 코드 전송
rsync -az --exclude venv --exclude tests --exclude app.db --exclude data --exclude certbot \
  -e "ssh -i infra/credentials/instance_ssh_key" backend/ ubuntu@<IP>:/home/ubuntu/backend/
scp -i ... infra/credentials/backend.env ubuntu@<IP>:/home/ubuntu/backend/.env
# 노드: cd backend && docker compose up -d --build   (HTTP 스택 기동)
```
- 검증: `curl -H "Host: si.leafeep.com" http://<IP>/api/health` → `{"status":"ok"}`

### 6. DNS (사람 필요 — hosting.co.kr 콘솔)
- A레코드: 호스트 `si` → `129.225.170.51`, TTL 기본. 전파 후 진행.

### 7. 엣지 기동 + 서비스 등록(HTTPS)
- 엣지 자산(`.claude/skills/infra-agent/templates/edge/`, `scripts/`)을 노드 `/home/ubuntu/edge/`로 rsync.
- `cd /home/ubuntu/edge && ./scripts/edge-up.sh` (네트워크 생성 + nginx/certbot 기동 + reload cron).
- 서비스 코드를 `/home/ubuntu/services/stop-island/`로 rsync(backend-only compose, edge 조인) → `docker compose up -d --build`.
- `./scripts/add-service.sh si.leafeep.com stop-island-backend:8000` (HTTP 부트스트랩 → certbot 발급 → HTTPS 전환).
- 검증: `curl https://si.leafeep.com/api/health`

### 8. 프론트 연결
- `frontend/.env.production`에 `VITE_API_BASE=https://si.leafeep.com` (추적됨) → git push(main) → Vercel 재빌드.
- 백엔드 CORS: `services/stop-island/.env`의 `CORS_ORIGINS`에 Vercel 오리진 → `docker compose up -d backend`(재빌드 불필요).

## 운영 명령 (치트시트)

```
# 엣지 (/home/ubuntu/edge)
docker compose ps
docker exec edge-nginx nginx -t && docker exec edge-nginx nginx -s reload
./scripts/add-service.sh <도메인> <컨테이너:포트>     # 새 서비스 등록

# 서비스 (/home/ubuntu/services/stop-island)
docker compose ps
docker compose logs -f backend
docker compose up -d --build      # 재배포(로컬 rsync 후)
docker compose down               # 이 서비스만 내림(엣지·타서비스 무관, 데이터 유지)
```

## 마이그레이션 시 체크리스트 (다른 노드/리전/계정)

1. 예약 IP는 리전 종속 → 새 리전이면 새 IP 발급 후 **DNS A레코드 갱신** 필수.
2. `services/<서비스>/data/`(app.db) 백업/복원: `sudo scp`로 통째 복사하면 방명록·예약·인증 데이터 이관됨.
3. 인증서(`edge/certbot/`)는 root 소유 심링크라 cp 재사용이 까다로움 → `add-service.sh` 재발급이 더 간단(레이트리밋 여유).
4. CORS_ORIGINS / VITE_API_BASE 도메인 바뀌면 양쪽 갱신.
5. 방화벽은 2중(OCI SL + 호스트 iptables) — 둘 다 열어야 함.
6. 멀티서비스 운영·새 서비스 추가는 스킬 `.claude/skills/infra-agent/SKILL.md` 참조.
