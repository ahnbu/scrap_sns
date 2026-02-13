# Codex에서 oh-my-ag 세팅 및 운영 가이드

이 문서는 Antigravity 프로젝트를 **Codex CLI에서 안정적으로 운영**하기 위한 실전 가이드입니다.
초보자 기준으로, "무엇을 어디에 설정하고 어떻게 호출하는지"만 빠르게 따라갈 수 있게 구성했습니다.

## 1) 목표와 전제

목표:
- Codex 채팅에서 `omg-*:` 트리거로 oh-my-ag 워크플로우를 실행
- `rules > workflows > skills` 우선순위로 일관된 작업 수행
- 계획, 조율, 리뷰, 디버깅, 커밋까지 재현 가능한 운영 흐름 확보

전제:
- Codex CLI 설치
- `bunx oh-my-ag` 실행 가능
- 현재 저장소에 `.agent/` 구조가 존재

## 2) 5분 빠른 점검

아래 명령으로 환경을 먼저 확인하세요.

```powershell
codex --version
codex --help
bunx oh-my-ag doctor
python .agent/scripts/validate_agent_config.py
```

핵심 폴더/파일:

```text
.agent/skills/
.agent/workflows/
.agent/rules/
.agent/config/user-preferences.yaml
.agent/mcp.json
AGENTS.md
```

## 3) Codex에서 명령 호출 방식

현재 일부 Codex 빌드는 사용자 정의 슬래시(`/omg-plan`, `/prompts:*`)를 차단할 수 있습니다.
이 경우 **텍스트 트리거**를 표준으로 사용합니다.

```text
omg-plan: <요청>
omg-review: <범위>
omg-coordinate: <요청>
omg-orchestrate: <요청>
omg-debug: <오류/상황>
```

예시:

```text
omg-plan: 트위터 수집기 개선 작업 계획 수립해줘
omg-review: thread_scrap.py와 server.py 리뷰해줘
omg-debug: 로그인 클릭 시 500 에러 원인 분석해줘
```

## 4) 우선순위 라우팅(필수)

반드시 다음 우선순위를 적용합니다.

```text
rules > workflows > skills
```

레이어별 역할:
- `rules/*.md`: 항상 적용되는 제약(코딩 스타일, 보안, 데이터 스키마, 테스트 등)
- `workflows/*.md`: 단계형 프로세스 계약(plan/review/debug 등)
- `skills/*/SKILL.md`: 특정 작업 수행 능력(backend-agent, commit 등)

## 5) omg 요청 처리 템플릿

`omg` 또는 `oh-my-ag` 요청이 오면, 실행 전/후를 명시적으로 고지합니다.

실행 전 고지 템플릿:

```text
적용 고지(실행 전):
- selected skill(s): <예: pm-agent, commit / none>
- selected workflow: <예: .agent/workflows/plan.md / none>
- enforced key rules: <예: rules > workflows > skills, commit language policy>
```

실행 후 고지 템플릿:

```text
적용 고지(실행 후):
- selected workflow/skills 적용 여부: <적용됨/부분 적용/미적용>
- 미적용 사유: <없음 또는 사유>
```

## 6) 워크플로우별 언제 쓰는가

`plan`:
- 요구사항 분해, 우선순위, 의존성 정리
- 예: `omg-plan: 인증 포함 TODO 앱 구현 계획 세워줘`

`coordinate`:
- 여러 도메인(백엔드/프론트/모바일) 병렬 조율
- 예: `omg-coordinate: 인증 API와 UI 작업을 병렬로 조율해줘`

`orchestrate`:
- `.agent/plan.json` 기반 실행 관리
- 예: `omg-orchestrate: plan.json 기준으로 실행 상태 관리해줘`

`review`:
- 품질/보안/성능/회귀 위험 점검
- 예: `omg-review: 최근 변경 파일 전체 리뷰`

`debug`:
- 재현 -> 근본원인 -> 최소수정 -> 회귀테스트
- 예: `omg-debug: map of undefined 오류 분석`

## 7) 설정 파일 위치 주의

Codex는 보통 사용자 홈 설정을 우선 읽습니다.

```text
프로젝트 로컬 설정: D:\vibe-coding\scrap_sns\.codex\config.toml
사용자 홈 설정: C:\Users\ahnbu\.codex\config.toml
```

실무 팁:
- "설정했는데 안 먹는다"면 먼저 홈 설정 파일 기준으로 점검
- 슬래시 명령 미지원 빌드에서는 `omg-*:` 텍스트 트리거 사용

## 8) 커밋 운영 규칙(이 저장소 기준)

- 커밋 메시지의 자연어는 한국어 사용
- `feat`, `fix`, `chore` 같은 Conventional Commit 토큰은 영어 유지 가능
- `omg` 요청 커밋 시 실행 전/후 적용 고지 포함

예시:

```text
docs(omg): Codex 운영 가이드 업데이트
```

## 9) 자주 발생하는 문제와 해결

문제 1:
- 증상: `Unrecognized command '/omg-plan'`
- 원인: 클라이언트에서 미등록 슬래시 명령 차단
- 해결: `omg-plan: ...` 텍스트 트리거로 호출

문제 2:
- 증상: `Unrecognized command '/prompts:*'`
- 원인: 해당 빌드에서 커스텀 프롬프트 라우팅 미지원
- 해결: 슬래시 대신 자연어/텍스트 트리거 사용

문제 3:
- 증상: `oh-my-ag agent:spawn` 인자 누락 오류
- 원인: 필수 `agent-id`/prompt/session 인자 누락
- 해결: `oh-my-ag agent:spawn backend "작업설명" session-01`

문제 4:
- 증상: `github-mcp-server` 시작 실패
- 원인: docker 미설치 또는 PATH 미인식
- 해결: docker 설치 또는 해당 MCP 비활성화

## 10) 운영 체크리스트

- [ ] `codex --version` 확인
- [ ] `bunx oh-my-ag doctor` 통과
- [ ] `.agent/scripts/validate_agent_config.py` 통과
- [ ] `AGENTS.md`에 `rules > workflows > skills` 명시
- [ ] `omg-*:` 텍스트 트리거로 호출 테스트
- [ ] 실행 전/후 적용 고지 템플릿 사용 확인
- [ ] 계획(`plan`) -> 조율(`coordinate/orchestrate`) -> 검토(`review`) 흐름 점검
- [ ] 커밋 메시지 한국어 정책 확인

이 체크리스트를 통과하면, Codex 환경에서도 oh-my-ag 운영이 재현 가능해집니다.
