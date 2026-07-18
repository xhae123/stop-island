---
name: setup-personal-gh
description: personal 프로젝트에 GitHub 개인 인증 설정 추가
user-invocable: true
disable-model-invocation: true
---

현재 프로젝트가 `/Users/tom.kim/personal/` 하위에 있는지 확인하고, 맞다면 프로젝트 전용 CLAUDE.md에 GitHub 개인 인증 설정을 추가한다.

## 수행할 작업

1. 현재 작업 디렉토리가 `/Users/tom.kim/personal/` 하위인지 확인. 아니면 "personal 디렉토리 하위가 아닙니다"라고 알리고 중단.

2. `~/.claude/projects/` 아래에서 현재 프로젝트에 매칭되는 디렉토리를 찾는다.
   - 경로의 `/`를 `-`로 치환한 패턴으로 매칭

3. 해당 디렉토리에 `CLAUDE.md`가 있으면 읽고, GitHub 인증 섹션이 이미 있는지 확인.
   - 이미 있으면: "이미 설정되어 있습니다"라고 알리고 중단
   - 없으면: 기존 내용 뒤에 아래 섹션 추가

4. `CLAUDE.md`가 없으면 새로 생성.

## 추가할 내용

```markdown
## GitHub 인증
- 이 레포는 **github.com** 개인 계정 사용 (GHE 아님)
- 모든 `gh` 명령어에 `GH_HOST`와 `GH_TOKEN` 둘 다 지정할 것
- prefix: `GH_HOST=github.com GH_TOKEN=<토큰>`
- **절대 레포에 커밋되는 파일에 토큰을 넣지 말 것**
```

토큰은 `~/.claude/commands/setup-personal-gh.md`에서 읽어올 것. 레포 파일에 토큰 하드코딩 절대 금지.

5. 완료 후 `gh issue list --limit 1`로 연결 테스트하고 결과 알려주기.
