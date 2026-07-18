---
paths:
  - "context/plans/**"
  - "context/dev-milestone*.md"
---

# GitHub 이슈 기반 워크플로우

## 흐름
1. 주차별 플랜(`context/plans/week-XX.md`)에서 태스크 목록 확인
2. 각 태스크는 GitHub 이슈로 존재 (`[P{phase}-{번호}]` 형식)
3. 이슈를 받으면 → 이슈 본문의 "할 일" 체크리스트 순서대로 수행
4. 완료되면 이슈 닫기

## 이슈 컨벤션
- 제목: `[P{phase}-{번호}] 태스크 제목`
- 라벨: `phase-N`, `frontend`/`backend`/`infra`
- 본문: 목표, 할 일(체크리스트), 완료 기준, 의존성

## gh 인증
프로젝트 로컬 CLAUDE.md 참조 (`~/.claude/projects/` 하위).
토큰을 레포 파일에 절대 넣지 말 것.

## 세션 시작 시
1. `gh issue list --state open`으로 열린 이슈 확인
2. 의존성이 풀린 가장 앞 번호 이슈부터 수행
3. 이슈 본문 읽고 바로 실행
