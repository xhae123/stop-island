---
name: create-issue
description: 주차별 이슈를 병렬 에이전트로 일괄 생성
user-invocable: true
argument-hint: <phase-number> <task-descriptions>
---

# 이슈 일괄 생성

주차별 태스크를 GitHub 이슈로 생성합니다.

## 사용법

```
/create-issue P2 "메인 화면" "메뉴 선택" "영수증 인증 FE" "영수증 인증 BE"
```

## 절차

1. `context/dev-milestone-v2.md`에서 해당 Phase의 태스크 목록 확인
2. `context/wireframe-spec/` 에서 관련 화면 스펙 읽기
3. 각 태스크마다 `issue-creator` 에이전트를 병렬로 생성
4. 각 에이전트가:
   - 와이어프레임 스펙 읽기
   - 체크리스트 작성
   - `gh issue create` 실행
5. 생성된 이슈 번호 + URL 취합해서 보고

## 라벨 생성

새 Phase 라벨이 없으면 먼저 생성:
```
gh label create phase-{N} --description "Phase {N}: ..." --color "1d76db"
```

## gh 인증

프로젝트 로컬 CLAUDE.md에서 prefix 읽기:
`~/.claude/projects/-Users-tom-kim-personal-stop-island/CLAUDE.md`
