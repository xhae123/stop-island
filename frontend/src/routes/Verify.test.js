import { describe, it, expect } from 'vitest'

// 순수 로직만 검증(§부록). 파일 사전검증 + reason_code→문구 매핑.
// 헬퍼는 Verify.svelte의 <script module>에서 export 된다.
import { validateImageFile, reasonMessage, MAX_FILE_SIZE } from './Verify.svelte'

// jsdom File 헬퍼: 지정한 바이트 크기와 type을 가진 File을 만든다.
function makeFile(bytes, type, name = 'r.jpg') {
  const blob = new Blob([new Uint8Array(bytes)], { type })
  return new File([blob], name, { type })
}

describe('validateImageFile — 클라이언트 사전 검증 (VF-202~205)', () => {
  it('JPG 통과', () => {
    expect(validateImageFile(makeFile(1024, 'image/jpeg')).ok).toBe(true)
  })

  it('PNG 통과', () => {
    expect(validateImageFile(makeFile(1024, 'image/png', 'r.png')).ok).toBe(true)
  })

  it('정확히 10MB 통과 (경계, VF-202)', () => {
    expect(validateImageFile(makeFile(MAX_FILE_SIZE, 'image/jpeg')).ok).toBe(true)
  })

  it('10MB+1 차단 (경계, VF-202)', () => {
    const res = validateImageFile(makeFile(MAX_FILE_SIZE + 1, 'image/jpeg'))
    expect(res.ok).toBe(false)
    expect(res.message).toContain('10MB')
  })

  it('허용 외 형식(PDF·GIF·WebP) 차단 (VF-203)', () => {
    expect(validateImageFile(makeFile(100, 'application/pdf', 'r.pdf')).ok).toBe(false)
    expect(validateImageFile(makeFile(100, 'image/gif', 'r.gif')).ok).toBe(false)
    expect(validateImageFile(makeFile(100, 'image/webp', 'r.webp')).ok).toBe(false)
  })

  it('HEIC 차단 + 안내 (VF-204)', () => {
    const res = validateImageFile(makeFile(100, 'image/heic', 'IMG_0001.heic'))
    expect(res.ok).toBe(false)
    expect(res.message).toContain('HEIC')
  })

  it('확장자만 heic여도 차단 (type 비어있는 iOS 케이스)', () => {
    const res = validateImageFile(makeFile(100, '', 'IMG_0001.HEIC'))
    expect(res.ok).toBe(false)
  })

  it('0바이트 파일 차단 (VF-205)', () => {
    const res = validateImageFile(makeFile(0, 'image/jpeg'))
    expect(res.ok).toBe(false)
  })

  it('null/undefined 안전', () => {
    expect(validateImageFile(null).ok).toBe(false)
    expect(validateImageFile(undefined).ok).toBe(false)
  })
})

describe('reasonMessage — reason_code → 사용자 문구 (03-verify 표)', () => {
  it('NOT_RECEIPT (retry)', () => {
    expect(reasonMessage('NOT_RECEIPT')).toContain('영수증 사진이 아닌 것 같아요')
  })

  it('MISSING_REQUIRED_FIELD (retry)', () => {
    expect(reasonMessage('MISSING_REQUIRED_FIELD')).toContain('상호명')
  })

  it('NOT_TODAY (rejected)', () => {
    expect(reasonMessage('NOT_TODAY')).toContain('오늘 결제한 영수증만')
  })

  it('SHOP_NOT_PARTICIPATING (rejected)', () => {
    expect(reasonMessage('SHOP_NOT_PARTICIPATING')).toContain('참여 상점')
  })

  it('DUPLICATE_RECEIPT (rejected)', () => {
    expect(reasonMessage('DUPLICATE_RECEIPT')).toBe('이미 사용된 영수증이에요.')
  })

  it('REVOKED_BY_AUDIT (사후 전환)', () => {
    expect(reasonMessage('REVOKED_BY_AUDIT')).toContain('인증이 취소되었어요')
  })

  it('알 수 없는/누락 코드는 안전한 기본 문구', () => {
    expect(reasonMessage('SOMETHING_NEW')).toBeTruthy()
    expect(reasonMessage(undefined)).toBeTruthy()
    expect(reasonMessage(null)).toBeTruthy()
  })
})
