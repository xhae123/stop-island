package main

import (
	"os"
	"strconv"
	"strings"
)

// Config는 전부 환경변수로 외부화한다(시크릿은 레포에 없음). 기본값은 "키 없이도 dev에서
// 돌지만, 운영에선 반드시 값을 채워야 안전"한 쪽으로 잡는다.
type Config struct {
	APIKeys        map[string]bool // 소비자 인증 키 집합. 비면 인증 비활성(dev)
	MaxConcurrency int             // fail-fast 동시성 상한
	TimeoutSeconds float64         // 엔진(향후 Gemini) 호출 타임아웃
	MaxImageBytes  int64           // 이미지 상한
	Port           string
	UseMock        bool // 실 Gemini 배선 전까지 mock(기본 on)
	GeminiAPIKey   string
	GeminiModel    string
}

func loadConfig() Config {
	return Config{
		APIKeys:        parseKeys(os.Getenv("RECEIPT_CORE_API_KEYS")),
		MaxConcurrency: envInt("RECEIPT_CORE_MAX_CONCURRENCY", 8),
		TimeoutSeconds: envFloat("RECEIPT_CORE_TIMEOUT_SECONDS", 8.0),
		MaxImageBytes:  10 * 1024 * 1024,
		Port:           envStr("PORT", "8000"),
		UseMock:        os.Getenv("RECEIPT_CORE_MOCK") != "0",
		GeminiAPIKey:   os.Getenv("GEMINI_API_KEY"),
		GeminiModel:    envStr("GEMINI_MODEL", "gemini-2.0-flash"),
	}
}

func parseKeys(raw string) map[string]bool {
	keys := map[string]bool{}
	for _, k := range strings.Split(raw, ",") {
		if k = strings.TrimSpace(k); k != "" {
			keys[k] = true
		}
	}
	return keys
}

func envStr(name, def string) string {
	if v := strings.TrimSpace(os.Getenv(name)); v != "" {
		return v
	}
	return def
}

func envInt(name string, def int) int {
	if v := strings.TrimSpace(os.Getenv(name)); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func envFloat(name string, def float64) float64 {
	if v := strings.TrimSpace(os.Getenv(name)); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}
