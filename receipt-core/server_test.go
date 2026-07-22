package main

import (
	"bytes"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"net/textproto"
	"testing"
)

var (
	validJPEG = append([]byte{0xff, 0xd8, 0xff, 0xe0}, bytes.Repeat([]byte{0}, 32)...)
	validPNG  = append([]byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}, bytes.Repeat([]byte{0}, 32)...)
)

// fakeEngine — 테스트용 결정론적 엔진.
type fakeEngine struct {
	result ExtractResult
	err    error
}

func (f fakeEngine) Recognize([]byte) (ExtractResult, error) { return f.result, f.err }

func strp(s string) *string { return &s }
func intp(i int) *int       { return &i }

// testServer — API 키 없이(dev 인증 통과) 기본 서버. 개별 테스트가 cfg를 바꿀 수 있다.
func testServer(engine Engine) *Server {
	return NewServer(Config{MaxConcurrency: 8, MaxImageBytes: 10 * 1024 * 1024}, engine)
}

func multipartReq(image []byte, contentType, apiKey, reqID string) *http.Request {
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	h := make(textproto.MIMEHeader)
	h.Set("Content-Disposition", `form-data; name="image"; filename="r"`)
	h.Set("Content-Type", contentType)
	part, _ := mw.CreatePart(h)
	_, _ = part.Write(image)
	_ = mw.Close()
	req := httptest.NewRequest("POST", "/v1/extract", &buf)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	if apiKey != "" {
		req.Header.Set("X-API-Key", apiKey)
	}
	if reqID != "" {
		req.Header.Set("X-Request-Id", reqID)
	}
	return req
}

func do(s *Server, req *http.Request) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	s.routes().ServeHTTP(rec, req)
	return rec
}

func TestHealth(t *testing.T) {
	rec := do(testServer(fakeEngine{}), httptest.NewRequest("GET", "/health", nil))
	if rec.Code != 200 {
		t.Fatalf("want 200, got %d", rec.Code)
	}
}

func TestExtractReceiptReturnsFields(t *testing.T) {
	s := testServer(fakeEngine{result: ExtractResult{
		IsReceipt: true, StoreName: strp("막걸리계보"), BusinessNumber: strp("123-45-67890"),
		Date: strp("2026-07-22"), ApprovalNumber: strp("APP-1"), TotalAmount: intp(12000), Confidence: 0.92,
	}})
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "", "req-1"))
	if rec.Code != 200 {
		t.Fatalf("want 200, got %d (%s)", rec.Code, rec.Body)
	}
	var body map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body["is_receipt"] != true || body["store_name"] != "막걸리계보" ||
		body["approval_number"] != "APP-1" || body["total_amount"].(float64) != 12000 ||
		body["business_number"] != "123-45-67890" {
		t.Fatalf("unexpected body: %v", body)
	}
	if rec.Header().Get("X-Request-Id") != "req-1" {
		t.Fatalf("request id not echoed: %q", rec.Header().Get("X-Request-Id"))
	}
}

func TestNotReceiptIs200False(t *testing.T) {
	s := testServer(fakeEngine{result: ExtractResult{IsReceipt: false}})
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "", ""))
	if rec.Code != 200 {
		t.Fatalf("want 200, got %d", rec.Code)
	}
	var body map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body["is_receipt"] != false || len(body) != 1 {
		t.Fatalf("want {is_receipt:false} only, got %v", body)
	}
}

func TestNullableFieldsPassThrough(t *testing.T) {
	s := testServer(fakeEngine{result: ExtractResult{IsReceipt: true, Confidence: 0.4}})
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "", ""))
	var body map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body["is_receipt"] != true || body["store_name"] != nil || body["total_amount"] != nil {
		t.Fatalf("nullable fields not null: %v", body)
	}
}

func TestEngineUnavailableIs503(t *testing.T) {
	s := testServer(fakeEngine{err: ErrUnavailable})
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "", ""))
	if rec.Code != 503 {
		t.Fatalf("want 503, got %d", rec.Code)
	}
	var body map[string]string
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body["reason"] != "upstream_unavailable" || body["request_id"] == "" {
		t.Fatalf("unexpected 503 body: %v", body)
	}
}

func TestPNGAccepted(t *testing.T) {
	s := testServer(fakeEngine{result: ExtractResult{IsReceipt: true, Confidence: 0.9}})
	rec := do(s, multipartReq(validPNG, "image/png", "", ""))
	if rec.Code != 200 {
		t.Fatalf("want 200, got %d", rec.Code)
	}
}

func TestUnsupportedTypeIs400(t *testing.T) {
	s := testServer(fakeEngine{result: ExtractResult{IsReceipt: true, Confidence: 0.9}})
	rec := do(s, multipartReq([]byte("%PDF-1.4 fake"), "application/pdf", "", ""))
	if rec.Code != 400 {
		t.Fatalf("want 400, got %d", rec.Code)
	}
	var body map[string]string
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body["reason"] != "unsupported_type" {
		t.Fatalf("want unsupported_type, got %v", body)
	}
}

func TestWrongMagicIs400(t *testing.T) {
	s := testServer(fakeEngine{result: ExtractResult{IsReceipt: true, Confidence: 0.9}})
	rec := do(s, multipartReq([]byte("not-a-jpeg-at-all"), "image/jpeg", "", ""))
	if rec.Code != 400 {
		t.Fatalf("want 400, got %d", rec.Code)
	}
}

func TestEmptyBodyIs400(t *testing.T) {
	s := testServer(fakeEngine{result: ExtractResult{IsReceipt: true, Confidence: 0.9}})
	rec := do(s, multipartReq([]byte{}, "image/jpeg", "", ""))
	if rec.Code != 400 {
		t.Fatalf("want 400, got %d", rec.Code)
	}
	var body map[string]string
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body["reason"] != "empty_body" {
		t.Fatalf("want empty_body, got %v", body)
	}
}

func TestSaturationIs503(t *testing.T) {
	s := NewServer(Config{MaxConcurrency: 1, MaxImageBytes: 10 * 1024 * 1024},
		fakeEngine{result: ExtractResult{IsReceipt: true, Confidence: 0.9}})
	s.sem <- struct{}{} // 유일한 슬롯 선점 → 다음 요청은 즉시 saturated
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "", ""))
	if rec.Code != 503 {
		t.Fatalf("want 503, got %d", rec.Code)
	}
	var body map[string]string
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body["reason"] != "saturated" {
		t.Fatalf("want saturated, got %v", body)
	}
}

func TestMockEngineProducesReceipt(t *testing.T) {
	r, err := MockEngine{}.Recognize(validJPEG)
	if err != nil || !r.IsReceipt || r.StoreName == nil || *r.StoreName != "막걸리계보" ||
		r.TotalAmount == nil || r.ApprovalNumber == nil {
		t.Fatalf("mock result wrong: %+v err=%v", r, err)
	}
}
