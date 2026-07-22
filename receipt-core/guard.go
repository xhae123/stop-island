package main

import "bytes"

var (
	jpegSig = []byte{0xff, 0xd8, 0xff}
	pngSig  = []byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}
)

// guardImage — 형식·크기·매직바이트 검사. 통과면 "", 위반이면 reason 코드 반환.
// content-type은 위조 가능하므로 매직바이트로 실제 포맷을 확인한다(경량 디코딩 가드).
func guardImage(contentType string, data []byte, maxBytes int64) string {
	if len(data) == 0 {
		return "empty_body"
	}
	if int64(len(data)) > maxBytes {
		return "too_large"
	}
	switch contentType {
	case "image/jpeg":
		if !bytes.HasPrefix(data, jpegSig) {
			return "unsupported_type"
		}
	case "image/png":
		if !bytes.HasPrefix(data, pngSig) {
			return "unsupported_type"
		}
	default:
		return "unsupported_type"
	}
	return ""
}
