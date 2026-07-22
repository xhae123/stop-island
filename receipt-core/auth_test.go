package main

import "testing"

func authServer(keys map[string]bool) *Server {
	return NewServer(
		Config{APIKeys: keys, MaxConcurrency: 8, MaxImageBytes: 10 * 1024 * 1024},
		fakeEngine{result: ExtractResult{IsReceipt: true, Confidence: 0.9}},
	)
}

func TestMissingKeyIs401(t *testing.T) {
	s := authServer(map[string]bool{"test-key": true})
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "", ""))
	if rec.Code != 401 {
		t.Fatalf("want 401, got %d", rec.Code)
	}
}

func TestWrongKeyIs401(t *testing.T) {
	s := authServer(map[string]bool{"test-key": true})
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "nope", ""))
	if rec.Code != 401 {
		t.Fatalf("want 401, got %d", rec.Code)
	}
}

func TestValidKeyPasses(t *testing.T) {
	s := authServer(map[string]bool{"test-key": true})
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "test-key", ""))
	if rec.Code != 200 {
		t.Fatalf("want 200, got %d", rec.Code)
	}
}

func TestAuthDisabledWhenNoKeys(t *testing.T) {
	s := authServer(map[string]bool{}) // 키 없음 → dev, 인증 비활성
	rec := do(s, multipartReq(validJPEG, "image/jpeg", "", ""))
	if rec.Code != 200 {
		t.Fatalf("want 200, got %d", rec.Code)
	}
}
