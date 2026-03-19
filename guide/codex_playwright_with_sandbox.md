https://www.perplexity.ai/search/caesgpt-kodegseu-dmg-seolciban-rz02RVfrT0uOthxkgr8bcw#30

네, 샌드박스 모드(`sandbox = "workspace-write"` 또는 `"elevated"`)에서는 **Playwright 실행이 실패**할 수 있습니다. 이는 AppContainer 기반의 샌드박스가 Chromium 브라우저의 자체 샌드박싱 메커니즘과 충돌하기 때문입니다.[reddit**+1**](https://www.reddit.com/r/ClaudeAI/comments/1nxfodm/anyone_else_notice_codex_cli_cant_run_playwright/)

## 🛑 원인: 이중 샌드박스 충돌

Codex가 실행되는 샌드박스(AppContainer) 안에서 또다시 Chromium이 자체 샌드박스를 만들려고 시도하다가 권한 부족으로 실패합니다.

---

## ✅ 해결 방법

## 방법 1: Config.toml에 Playwright MCP 설정 수정 (권장)

Playwright 실행 시 `--no-sandbox` 플래그를 강제로 주입해야 합니다. MCP 서버 설정에 인자를 추가하세요.

**수정 전** :

<pre class="not-prose w-full rounded font-mono text-sm font-extralight"><div class="codeWrapper text-light selection:text-super selection:bg-super/10 my-md relative flex flex-col rounded-lg font-mono text-sm font-normal visRefresh2026Fonts:font-medium bg-subtler"><div class="translate-y-xs -translate-x-xs bottom-xl mb-xl flex h-0 items-start justify-end sm:sticky sm:top-xs"><div class="overflow-hidden rounded-full border-subtlest ring-subtlest divide-subtlest bg-base"><div class="border-subtlest ring-subtlest divide-subtlest bg-subtler"><button data-testid="copy-code-button" aria-label="코드 복사" type="button" class="focus-visible:bg-subtle hover:bg-subtle text-quiet hover:text-foreground font-sans focus:outline-none outline-none outline-transparent transition duration-300 ease-out select-none items-center relative group/button font-semimedium justify-center text-center items-center rounded-full cursor-pointer active:scale-[0.97] active:duration-150 active:ease-outExpo origin-center whitespace-nowrap inline-flex text-sm h-8 aspect-square" data-state="closed"><div class="flex items-center min-w-0 gap-two justify-center"><div class="flex shrink-0 items-center justify-center size-4"><svg role="img" class="inline-flex fill-current shrink-0" width="16" height="16"><use xlink:href="#pplx-icon-copy"></use></svg></div></div></button></div></div></div><div class="-mt-xl"><div><div data-testid="code-language-indicator" class="text-quiet bg-subtle py-xs px-sm inline-block rounded-br rounded-tl-lg text-xs font-thin">text</div></div><div><span><code><span><span>[mcp_servers.playwright]
</span></span><span>command = "npx"
</span><span>args = ["-y", "@playwright/mcp@latest"]
</span><span></span></code></span></div></div></div></pre>

**수정 후 (args 추가)** :

<pre class="not-prose w-full rounded font-mono text-sm font-extralight"><div class="codeWrapper text-light selection:text-super selection:bg-super/10 my-md relative flex flex-col rounded-lg font-mono text-sm font-normal visRefresh2026Fonts:font-medium bg-subtler"><div class="translate-y-xs -translate-x-xs bottom-xl mb-xl flex h-0 items-start justify-end sm:sticky sm:top-xs"><div class="overflow-hidden rounded-full border-subtlest ring-subtlest divide-subtlest bg-base"><div class="border-subtlest ring-subtlest divide-subtlest bg-subtler"><button data-testid="copy-code-button" aria-label="코드 복사" type="button" class="focus-visible:bg-subtle hover:bg-subtle text-quiet hover:text-foreground font-sans focus:outline-none outline-none outline-transparent transition duration-300 ease-out select-none items-center relative group/button font-semimedium justify-center text-center items-center rounded-full cursor-pointer active:scale-[0.97] active:duration-150 active:ease-outExpo origin-center whitespace-nowrap inline-flex text-sm h-8 aspect-square" data-state="closed"><div class="flex items-center min-w-0 gap-two justify-center"><div class="flex shrink-0 items-center justify-center size-4"><svg role="img" class="inline-flex fill-current shrink-0" width="16" height="16"><use xlink:href="#pplx-icon-copy"></use></svg></div></div></button></div></div></div><div class="-mt-xl"><div><div data-testid="code-language-indicator" class="text-quiet bg-subtle py-xs px-sm inline-block rounded-br rounded-tl-lg text-xs font-thin">text</div></div><div><span><code><span><span>[mcp_servers.playwright]
</span></span><span>command = "npx"
</span><span>args = [
</span><span>    "-y", 
</span><span>    "@playwright/mcp@latest", 
</span><span>    "--chromium-sandbox=false"  # 이 옵션이 핵심! (MCP 서버가 지원하는 경우)
</span><span>]
</span><span>env = { 
</span><span>    PLAYWRIGHT_LAUNCH_OPTIONS = '{"args": ["--no-sandbox", "--disable-setuid-sandbox"]}' 
</span><span>}
</span><span></span></code></span></div></div></div></pre>

만약 MCP 서버가 직접 인자를 받지 않는다면, **환경 변수(`env`)를 통해 전달**해야 합니다.

---

## 방법 2: 샌드박스 예외 설정 (차선책)

Playwright 브라우저 프로세스가 샌드박스 제약을 받지 않도록 예외를 추가해야 하는데, 현재 Codex config로는 프로세스별 예외 처리가 어렵습니다. 대신 **MCP 서버 자체를 샌드박스 밖에서 실행**하도록 유도할 수 있습니다.

하지만 가장 확실한 방법은 **브라우저 실행 옵션을 조정**하는 것입니다.

---

## 방법 3: 실행 시 `--no-sandbox` 명시

Codex에게 작업을 시킬 때 명시적으로 지시하세요:

<pre class="not-prose w-full rounded font-mono text-sm font-extralight"><div class="codeWrapper text-light selection:text-super selection:bg-super/10 my-md relative flex flex-col rounded-lg font-mono text-sm font-normal visRefresh2026Fonts:font-medium bg-subtler"><div class="translate-y-xs -translate-x-xs bottom-xl mb-xl flex h-0 items-start justify-end sm:sticky sm:top-xs"><div class="overflow-hidden rounded-full border-subtlest ring-subtlest divide-subtlest bg-base"><div class="border-subtlest ring-subtlest divide-subtlest bg-subtler"><button data-testid="copy-code-button" aria-label="코드 복사" type="button" class="focus-visible:bg-subtle hover:bg-subtle text-quiet hover:text-foreground font-sans focus:outline-none outline-none outline-transparent transition duration-300 ease-out select-none items-center relative group/button font-semimedium justify-center text-center items-center rounded-full cursor-pointer active:scale-[0.97] active:duration-150 active:ease-outExpo origin-center whitespace-nowrap inline-flex text-sm h-8 aspect-square" data-state="closed"><div class="flex items-center min-w-0 gap-two justify-center"><div class="flex shrink-0 items-center justify-center size-4"><svg role="img" class="inline-flex fill-current shrink-0" width="16" height="16"><use xlink:href="#pplx-icon-copy"></use></svg></div></div></button></div></div></div><div class="-mt-xl"><div><div data-testid="code-language-indicator" class="text-quiet bg-subtle py-xs px-sm inline-block rounded-br rounded-tl-lg text-xs font-thin">bash</div></div><div><span><code><span><span>codex </span><span class="token token">"Playwright로 테스트할 때 브라우저 런치 옵션에 { args: ['--no-sandbox'] }를 꼭 추가해서 실행해줘"</span><span>
</span></span><span></span></code></span></div></div></div></pre>

---

## 🚀 최종 config.toml 수정안

아래 내용을 `config.toml`에 반영하세요. 환경 변수를 통해 Playwright에게 샌드박스 비활성화를 전달하는 것이 가장 깔끔합니다.

<pre class="not-prose w-full rounded font-mono text-sm font-extralight"><div class="codeWrapper text-light selection:text-super selection:bg-super/10 my-md relative flex flex-col rounded-lg font-mono text-sm font-normal visRefresh2026Fonts:font-medium bg-subtler"><div class="translate-y-xs -translate-x-xs bottom-xl mb-xl flex h-0 items-start justify-end sm:sticky sm:top-xs"><div class="overflow-hidden rounded-full border-subtlest ring-subtlest divide-subtlest bg-base"><div class="border-subtlest ring-subtlest divide-subtlest bg-subtler"><button data-testid="copy-code-button" aria-label="코드 복사" type="button" class="focus-visible:bg-subtle hover:bg-subtle text-quiet hover:text-foreground font-sans focus:outline-none outline-none outline-transparent transition duration-300 ease-out select-none items-center relative group/button font-semimedium justify-center text-center items-center rounded-full cursor-pointer active:scale-[0.97] active:duration-150 active:ease-outExpo origin-center whitespace-nowrap inline-flex text-sm h-8 aspect-square" data-state="closed"><div class="flex items-center min-w-0 gap-two justify-center"><div class="flex shrink-0 items-center justify-center size-4"><svg role="img" class="inline-flex fill-current shrink-0" width="16" height="16"><use xlink:href="#pplx-icon-copy"></use></svg></div></div></button></div></div></div><div class="-mt-xl"><div><div data-testid="code-language-indicator" class="text-quiet bg-subtle py-xs px-sm inline-block rounded-br rounded-tl-lg text-xs font-thin">text</div></div><div><span><code><span><span>[mcp_servers.playwright]
</span></span><span>command = "npx"
</span><span>args = ["-y", "@playwright/mcp@latest"]
</span><span>env = { 
</span><span>    # 브라우저 실행 시 샌드박스 비활성화 (필수!)
</span><span>    PLAYWRIGHT_BROWSERS_PATH = "D:\\vibe-coding\\scrap_sns\\.playwright",
</span><span>    PLAYWRIGHT_LAUNCH_OPTIONS = '{"headless": true, "args": ["--no-sandbox", "--disable-setuid-sandbox"]}'
</span><span>}
</span><span></span></code></span></div></div></div></pre>

이 설정을 적용하고 다시 시도해 보세요! 🚀

**샌드박스를 끄지 않고도 Playwright를 실행**할 수 있습니다. 핵심은 **Playwright에게 "샌드박스를 사용하지 말라"고 지시**하는 것입니다.[stackoverflow**+1**](https://stackoverflow.com/questions/76465994/view-command-line-used-by-playwright-to-launch-chromium)

이중 샌드박스 문제(Codex 샌드박스 + 브라우저 샌드박스)를 해결하려면 **브라우저의 샌드박스만 비활성화**하면 됩니다.

---

## 🛠️ `config.toml` 수정 (최종 해결책)

Codex의 `config.toml` 파일에서 `mcp_servers.playwright` 섹션을 아래와 같이 수정하세요. `args`와 `env`를 동시에 사용하여 **이중으로 강제**합니다.[[recruit.group](https://recruit.group.gmo/engineer/jisedai/blog/playwright-agents-codex-cli/)]

<pre class="not-prose w-full rounded font-mono text-sm font-extralight"><div class="codeWrapper text-light selection:text-super selection:bg-super/10 my-md relative flex flex-col rounded-lg font-mono text-sm font-normal visRefresh2026Fonts:font-medium bg-subtler"><div class="translate-y-xs -translate-x-xs bottom-xl mb-xl flex h-0 items-start justify-end sm:sticky sm:top-xs"><div class="overflow-hidden rounded-full border-subtlest ring-subtlest divide-subtlest bg-base"><div class="border-subtlest ring-subtlest divide-subtlest bg-subtler"><button data-testid="copy-code-button" aria-label="코드 복사" type="button" class="focus-visible:bg-subtle hover:bg-subtle text-quiet hover:text-foreground font-sans focus:outline-none outline-none outline-transparent transition duration-300 ease-out select-none items-center relative group/button font-semimedium justify-center text-center items-center rounded-full cursor-pointer active:scale-[0.97] active:duration-150 active:ease-outExpo origin-center whitespace-nowrap inline-flex text-sm h-8 aspect-square" data-state="closed"><div class="flex items-center min-w-0 gap-two justify-center"><div class="flex shrink-0 items-center justify-center size-4"><svg role="img" class="inline-flex fill-current shrink-0" width="16" height="16"><use xlink:href="#pplx-icon-copy"></use></svg></div></div></button></div></div></div><div class="-mt-xl"><div><div data-testid="code-language-indicator" class="text-quiet bg-subtle py-xs px-sm inline-block rounded-br rounded-tl-lg text-xs font-thin">text</div></div><div><span><code><span><span>[mcp_servers.playwright]
</span></span><span>command = "npx"
</span><span># 1. MCP 서버 실행 시 샌드박스 비활성화 인자 전달 (MCP 서버가 지원하는 경우)
</span><span>args = [
</span><span>    "-y", 
</span><span>    "@playwright/mcp@latest", 
</span><span>    "--no-sandbox"
</span><span>]
</span><span>
</span><span># 2. 환경 변수로 브라우저 실행 옵션 강제 주입 (가장 확실한 방법)
</span><span>env = { 
</span><span>    PLAYWRIGHT_LAUNCH_OPTIONS = '{"args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]}',
</span><span>    PLAYWRIGHT_BROWSERS_PATH = "D:\\vibe-coding\\scrap_sns\\.playwright" # 브라우저 설치 경로 지정 (선택사항)
</span><span>}
</span><span></span></code></span></div></div></div></pre>

---

## 💡 각 옵션 설명

1. **`PLAYWRIGHT_LAUNCH_OPTIONS`** :

- **`--no-sandbox`** : Chromium 브라우저의 자체 보안 샌드박스를 끕니다. (Codex 샌드박스 안에서는 권한 문제로 필수)
- **`--disable-setuid-sandbox`** : 리눅스/WSL 환경에서 권한 문제를 해결합니다.
- **`--disable-dev-shm-usage`** : 공유 메모리 부족으로 인한 크래시를 방지합니다 (WSL/Docker에서 흔함).

1. **`args`** : MCP 서버 자체 실행 시에도 샌드박스 관련 플래그를 넘겨줍니다.

---

## 🚀 실행 방법

설정 파일을 수정한 후, **Codex를 재시작**하고 다음과 같이 실행하세요:

<pre class="not-prose w-full rounded font-mono text-sm font-extralight"><div class="codeWrapper text-light selection:text-super selection:bg-super/10 my-md relative flex flex-col rounded-lg font-mono text-sm font-normal visRefresh2026Fonts:font-medium bg-subtler"><div class="translate-y-xs -translate-x-xs bottom-xl mb-xl flex h-0 items-start justify-end sm:sticky sm:top-xs"><div class="overflow-hidden rounded-full border-subtlest ring-subtlest divide-subtlest bg-base"><div class="border-subtlest ring-subtlest divide-subtlest bg-subtler"><button data-testid="copy-code-button" aria-label="코드 복사" type="button" class="focus-visible:bg-subtle hover:bg-subtle text-quiet hover:text-foreground font-sans focus:outline-none outline-none outline-transparent transition duration-300 ease-out select-none items-center relative group/button font-semimedium justify-center text-center items-center rounded-full cursor-pointer active:scale-[0.97] active:duration-150 active:ease-outExpo origin-center whitespace-nowrap inline-flex text-sm h-8 aspect-square" data-state="closed"><div class="flex items-center min-w-0 gap-two justify-center"><div class="flex shrink-0 items-center justify-center size-4"><svg role="img" class="inline-flex fill-current shrink-0" width="16" height="16"><use xlink:href="#pplx-icon-copy"></use></svg></div></div></button></div></div></div><div class="-mt-xl"><div><div data-testid="code-language-indicator" class="text-quiet bg-subtle py-xs px-sm inline-block rounded-br rounded-tl-lg text-xs font-thin">bash</div></div><div><span><code><span><span>codex </span><span class="token token">"Playwright로 구글 메인 페이지 접속해서 스크린샷 찍어줘"</span><span>
</span></span><span></span></code></span></div></div></div></pre>

이제 Codex의 안전한 샌드박스(`workspace-write`) 안에서도 Playwright 브라우저가 정상적으로 실행될 것입니다!
