# Codex CLI 커스텀 커맨드 핵심 가이드

이 문서는 **현재 프로젝트에서 실제로 확인된 방법**만 간단히 정리합니다.

## 1) 먼저 알아둘 점
- 현재 환경(`codex-cli 0.101.0`)에서는 `/omg-plan`, `/prompts:plan` 같은 임의 슬래시 명령이 바로 동작하지 않을 수 있습니다.
- 에러 예시: `Unrecognized command '/omg-plan'`
- 따라서 실전에서는 **텍스트 트리거 방식**을 기본으로 쓰는 것이 안전합니다.

## 2) 권장 사용 방식 (바로 사용 가능)
슬래시 대신 아래처럼 입력합니다.

```text
omg-plan: 트위터 수집기 개선 작업 계획 세워줘
omg-review: thread_scrap.py 코드 리뷰해줘
omg-debug: 로그인 버튼 클릭 시 500 에러 원인 찾아줘
omg-coordinate: 백엔드+프론트 병렬 작업 조율해줘
omg-orchestrate: plan.json 기준으로 실행 단계 정리해줘
```

## 3) 왜 이렇게 쓰는가?
- 일부 Codex 클라이언트는 **알 수 없는 슬래시 명령을 모델에 전달하기 전에 차단**합니다.
- 그래서 `.codex/config.toml`에 `custom_commands`를 넣어도, 이 빌드에서는 체감상 동작하지 않을 수 있습니다.

## 4) 설정 파일 위치 주의
- 프로젝트 파일: `D:\vibe-coding\scrap_sns\.codex\config.toml`
- 사용자 홈 설정: `C:\Users\ahnbu\.codex\config.toml`
- CLI는 보통 **홈 설정**을 기준으로 동작합니다.

## 5) 빠른 점검 명령
```powershell
codex --version
codex --help
codex features list
```

## 6) 운영 팁
- `AGENTS.md` 규칙에 맞춰 `omg-*:` 텍스트 트리거를 표준으로 사용하세요.
- 슬래시 명령 지원 빌드로 바뀌면 그때 `/omg-*`를 다시 활성화하면 됩니다.

## 7) AGENTS.md 세팅 예시 (복붙용)
아래 블록을 기준으로 `AGENTS.md`의 라우팅/트리거 규칙을 맞추면 됩니다.

```markdown
## Agent Routing & Precedence
- Apply this precedence strictly: `rules` > `workflows` > `skills`.
- `rules/*.md` are global constraints.
- `workflows/*.md` are process contracts.
- `skills/*/SKILL.md` are focused capability packs.
- If slash commands are blocked by the client, use text triggers:
  - `omg-plan: <request>`
  - `omg-review: <scope>`
  - `omg-coordinate: <request>`
  - `omg-orchestrate: <request>`
  - `omg-debug: <error/context>`
```

```markdown
## `omg` / `oh-my-ag` Trigger Rule
- Treat `omg` as alias of `oh-my-ag`.
- Treat `omg-*:` text triggers as explicit workflow invocation.
- On every `omg` request, do:
  1. Select workflow from `.agent/workflows/`.
  2. Select matching skills from `.agent/skills/`.
  3. Enforce constraints from `.agent/rules/`.
  4. Before execution, report selected skills/workflow/rules.
  5. After execution, confirm what was actually applied.
```

실제 입력 예시:

```text
omg-plan: 신규 기능 개발 계획 수립해줘
omg-review: AGENTS.md, docs/codex_cli_custom_command_guide.md 검토해줘
omg-debug: /omg-plan 명령이 인식되지 않는 원인 분석해줘
```
