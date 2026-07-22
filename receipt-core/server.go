package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
)

// Server — 설정·엔진·동시성 세마포어를 묶는다.
type Server struct {
	cfg    Config
	engine Engine
	sem    chan struct{} // fail-fast 동시성 상한
}

func NewServer(cfg Config, engine Engine) *Server {
	return &Server{cfg: cfg, engine: engine, sem: make(chan struct{}, cfg.MaxConcurrency)}
}

func (s *Server) routes() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("POST /v1/extract", s.handleExtract)
	return mux
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, 200, map[string]string{"status": "ok"})
}

// authOK — X-API-Key 검증. config.APIKeys가 비면 dev(인증 비활성).
func (s *Server) authOK(r *http.Request) bool {
	if len(s.cfg.APIKeys) == 0 {
		return true
	}
	return s.cfg.APIKeys[r.Header.Get("X-API-Key")]
}

func (s *Server) handleExtract(w http.ResponseWriter, r *http.Request) {
	reqID := r.Header.Get("X-Request-Id")
	if reqID == "" {
		reqID = newRequestID()
	}
	w.Header().Set("X-Request-Id", reqID)

	if !s.authOK(r) {
		writeError(w, 401, "unauthorized", reqID)
		return
	}

	// fail-fast 동시성: 대기하지 않고 즉시 503으로 반납한다. 차단式이면 대기가 워커를
	// 점유해 격리가 무의미해진다 — 그래서 select-default.
	select {
	case s.sem <- struct{}{}:
		defer func() { <-s.sem }()
	default:
		writeError(w, 503, "saturated", reqID)
		return
	}

	// 메모리 폭주 방지 하드캡. 실제 too_large 판정은 아래 guardImage가 image 크기로 한다.
	r.Body = http.MaxBytesReader(w, r.Body, s.cfg.MaxImageBytes*2+4096)
	if err := r.ParseMultipartForm(s.cfg.MaxImageBytes + 4096); err != nil {
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			writeError(w, 400, "too_large", reqID)
		} else {
			writeError(w, 400, "empty_body", reqID)
		}
		return
	}

	file, header, err := r.FormFile("image")
	if err != nil {
		writeError(w, 400, "empty_body", reqID)
		return
	}
	defer file.Close()

	data, err := io.ReadAll(file)
	if err != nil {
		writeError(w, 400, "empty_body", reqID)
		return
	}

	contentType := ""
	if header != nil {
		contentType = header.Header.Get("Content-Type")
	}
	if reason := guardImage(contentType, data, s.cfg.MaxImageBytes); reason != "" {
		writeError(w, 400, reason, reqID)
		return
	}

	result, err := s.engine.Recognize(data)
	if err != nil {
		// 엔진 장애는 전부 upstream_unavailable로 흡수(소비자는 폴백).
		writeError(w, 503, "upstream_unavailable", reqID)
		return
	}

	writeResult(w, result)
}

func newRequestID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "req-unknown"
	}
	return hex.EncodeToString(b)
}

func writeJSON(w http.ResponseWriter, code int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, code int, reason, reqID string) {
	body := map[string]string{"reason": reason}
	if code >= 500 {
		body["request_id"] = reqID
	}
	writeJSON(w, code, body)
}

func writeResult(w http.ResponseWriter, r ExtractResult) {
	if !r.IsReceipt {
		writeJSON(w, 200, map[string]any{"is_receipt": false})
		return
	}
	// 포인터 필드는 nil일 때 JSON null로 직렬화된다(추출 실패=null).
	writeJSON(w, 200, map[string]any{
		"is_receipt":      true,
		"store_name":      r.StoreName,
		"business_number": r.BusinessNumber,
		"date":            r.Date,
		"approval_number": r.ApprovalNumber,
		"total_amount":    r.TotalAmount,
		"confidence":      r.Confidence,
	})
}
