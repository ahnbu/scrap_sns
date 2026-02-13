# Codex 샌드박스에서 Playwright 설치 가이드 (초보자용)

이 문서는 `D:\vibe-coding\scrap_sns` 프로젝트에서 **Codex 샌드박스 모드**로 Playwright를 쓰기 위한 최소 설정을 설명합니다.

## 1) 먼저 알아둘 점

- 샌드박스 모드에서는 Chromium 기본 샌드박스와 충돌해 브라우저 실행이 실패할 수 있습니다.
- 그래서 Playwright MCP에 `--no-sandbox` 설정이 필요합니다.

## 2) 파일 1개 설정: `.codex/config.toml`

파일: `D:\vibe-coding\scrap_sns\.codex\config.toml`

아래 블록이 없으면 추가하세요.

```toml
[mcp_servers.playwright]
command = "npx"
args = ["-y", "@playwright/mcp@latest", "--no-sandbox"]
env = { PLAYWRIGHT_MCP_NO_SANDBOX = "1", PLAYWRIGHT_BROWSERS_PATH = "D:\\vibe-coding\\scrap_sns\\.playwright" }
```

## 3) (선택) 파일 1개 더 설정: `.agent/mcp.json`

프로젝트 내부 에이전트 설정도 같이 쓰는 경우, 아래 서버를 추가합니다.

파일: `D:\vibe-coding\scrap_sns\.agent\mcp.json`

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--no-sandbox"],
      "env": {
        "PLAYWRIGHT_MCP_NO_SANDBOX": "1",
        "PLAYWRIGHT_BROWSERS_PATH": "D:\\vibe-coding\\scrap_sns\\.playwright"
      }
    }
  }
}
```

주의: 기존 `mcpServers`에 다른 서버가 있으면, `playwright`만 추가하고 나머지는 유지하세요.

## 4) Chromium 설치

프로젝트 루트에서 실행:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH='D:\vibe-coding\scrap_sns\.playwright'
npx playwright install chromium
```

## 5) 자주 나는 오류와 해결

### 오류: `spawn EPERM`

원인: 샌드박스 제한으로 브라우저 다운로드/실행 프로세스 생성이 막힘.

해결:

1. Codex에서 같은 설치 명령을 **권한 상승(승인)**으로 다시 실행
2. 설치 완료 후 다시 테스트

## 6) 동작 확인 (가장 간단한 체크)

Codex Playwright 도구로 아래 순서 확인:

1. `https://example.com` 접속
2. 페이지 제목이 `Example Domain`인지 확인
3. 스냅샷이 정상 반환되는지 확인

## 7) 마지막 체크리스트

- `.codex/config.toml`에 `playwright` 서버가 있다.
- `--no-sandbox`가 args에 있다.
- `PLAYWRIGHT_MCP_NO_SANDBOX=1`이 env에 있다.
- `.playwright` 폴더에 Chromium이 설치되어 있다.
- 설정 변경 후 Codex 세션을 재시작했다.

위 5개가 맞으면, 초보자 기준으로 대부분 바로 동작합니다.
