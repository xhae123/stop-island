package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"time"
)

// ErrUnavailable — 엔진 호출이 재시도 소진 후에도 실패(타임아웃·5xx·429).
// 핸들러가 이를 잡아 503 upstream_unavailable로 응답한다 → 소비자는 폴백.
var ErrUnavailable = errors.New("ocr unavailable")

// ExtractResult — 영수증에서 뽑아낸 구조. 추출 필드는 전부 nullable(포인터 = null 가능).
//
// 코어는 이미지를 보는 유일·최종 지점이라, 값싸게 뽑히는 total_amount·business_number를
// 지금 안 뽑으면 나중에 Gemini를 다시 호출($)해야 복구된다(추출 경계에선 YAGNI가 뒤집힌다).
type ExtractResult struct {
	IsReceipt      bool
	StoreName      *string
	BusinessNumber *string
	Date           *string
	ApprovalNumber *string
	TotalAmount    *int
	Confidence     float64
}

// Engine — 이미지 → ExtractResult 변환기. "영수증 아님"은 에러가 아니라
// IsReceipt=false 결과다(계약 v2.1). 엔진 장애만 ErrUnavailable로 던진다.
type Engine interface {
	Recognize(image []byte) (ExtractResult, error)
}

// kstLoc — time/tzdata를 임베드(main.go)했으므로 distroless static에서도 KST 해석 가능.
var kstLoc, _ = time.LoadLocation("Asia/Seoul")

// MockEngine — 실 Gemini 배선 전 dev/E2E용 결정론적 엔진.
// approval_number는 이미지 해시에서 파생시켜(서로 다른 이미지가 가짜 중복으로 충돌하지
// 않게) 고정 payload 함정을 피한다. 상호명은 stop-island seed 참여상점과 일치시킨다.
type MockEngine struct{}

func (MockEngine) Recognize(image []byte) (ExtractResult, error) {
	sum := sha256.Sum256(image)
	approval := "MOCK-" + hex.EncodeToString(sum[:])[:12]
	date := time.Now().In(kstLoc).Format("2006-01-02")
	store := "막걸리계보"
	biz := "123-45-67890"
	amount := 12000
	return ExtractResult{
		IsReceipt:      true,
		StoreName:      &store,
		BusinessNumber: &biz,
		Date:           &date,
		ApprovalNumber: &approval,
		TotalAmount:    &amount,
		Confidence:     0.9,
	}, nil
}

// GeminiEngine — 실 OCR seam. Recognize는 _callGemini 한 곳만 배선하면 된다.
// 아직 미배선이라 호출되면 ErrUnavailable을 던진다(→ 503 → 소비자 폴백). 안전한 기본값.
type GeminiEngine struct {
	APIKey string
	Model  string
}

func (e GeminiEngine) Recognize(image []byte) (ExtractResult, error) {
	// ★ THE SWAP POINT ★ — 실제 Gemini generateContent I/O를 여기에 배선한다.
	// 타임아웃/5xx/429는 ErrUnavailable로, is_receipt=false는 IsReceipt=false로 매핑.
	return ExtractResult{}, ErrUnavailable
}
