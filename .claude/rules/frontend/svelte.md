---
paths:
  - "frontend/**/*.svelte"
  - "frontend/**/*.js"
  - "frontend/**/*.ts"
  - "frontend/**/*.css"
---

# 프론트엔드 규칙

## 스택
- Svelte (SPA, SvelteKit 아님) + svelte-spa-router
- Vite 빌드 + Tailwind CSS v4
- 모바일 퍼스트 (375~390px 기준)

## 컨벤션
- 컴포넌트 파일명: PascalCase (`SeatGrid.svelte`)
- 라우트 컴포넌트: `frontend/src/routes/` 하위
- 공용 컴포넌트: `frontend/src/components/` 하위
- API 호출: `frontend/src/lib/api.js`에 집중
- 스타일: Tailwind 유틸리티 클래스 우선, 커스텀 CSS 최소화

## 디자인 시스템
- Island Yellow: `#FFEE00`
- Pause White: `#FFFFFF`
- Flow Black: `#000000`
- Header 배경: `#1a1700`

## 주의
- 디자인 결정은 디자인 팀원의 영역. 개발에서 art-direct 하지 않는다
- 와이어프레임 기반으로 먼저 구현, 시안 오면 교체
- 모든 화면은 모바일 브라우저(iOS Safari, Android Chrome) 호환 필수
