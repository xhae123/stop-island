# 멀티스테이지: Go 정적 바이너리 → distroless static. aarch64 노드에서 직접 빌드.
FROM golang:1.26 AS build
WORKDIR /src
# 외부 의존성 0(stdlib only) → go.sum 없음. go.mod만 먼저 복사해 레이어 캐시.
COPY go.mod ./
COPY *.go ./
# CGO 끄면 완전 정적 바이너리. time/tzdata는 소스에서 임베드(KST).
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /receipt-core .

FROM gcr.io/distroless/static-debian12
COPY --from=build /receipt-core /receipt-core
EXPOSE 8000
ENV PORT=8000
ENTRYPOINT ["/receipt-core"]
