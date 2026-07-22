// 영수증 코어 서버 — standalone 영수증 추출 API(Go, stdlib only).
// 여러 서비스가 X-API-Key로 소비한다. 무상태(v1).
package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	// distroless static 이미지엔 tzdata가 없으므로 KST 해석을 위해 임베드한다.
	_ "time/tzdata"
)

func main() {
	cfg := loadConfig()

	var engine Engine
	if cfg.UseMock {
		engine = MockEngine{}
	} else {
		engine = GeminiEngine{APIKey: cfg.GeminiAPIKey, Model: cfg.GeminiModel}
	}
	if len(cfg.APIKeys) == 0 {
		log.Print("경고: RECEIPT_CORE_API_KEYS 미설정 — 인증 비활성(dev). 운영에선 반드시 설정할 것.")
	}

	srv := NewServer(cfg, engine)
	httpSrv := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           srv.routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("receipt-core listening on :%s (mock=%v)", cfg.Port, cfg.UseMock)
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}
	}()

	// SIGTERM(컨테이너 정지) 시 graceful shutdown.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(shutdownCtx); err != nil {
		log.Printf("shutdown error: %v", err)
	}
	os.Exit(0)
}
