---
title: SNS 조회 export md 구현계획
created: 2026-05-18
session_id: codex:019e39cf-9d30-7830-a4c7-f3639d0db3be
session_path: Codex Desktop thread
ai: Codex
---

# SNS 조회 Export Markdown Implementation Plan

> **For agentic workers:** 이 레포의 `AGENTS.md`가 워크트리는 명시 요청 시에만 사용하도록 제한하므로, 기본은 현재 브랜치에서 실행한다. 구현 전후에는 병행 작업 변경을 되돌리지 않는다. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `query-sns.mjs` 조회 결과를 강의 재료나 초기 리서치 노트로 바로 쓸 수 있도록 Markdown/JSON 파일로 저장한다.

**Architecture:** 기존 `utils/query-sns.mjs`의 조회 로직을 재사용해 `export <조회명령>` 래퍼를 추가한다. 일반 조회 결과는 기존처럼 excerpt 중심으로 유지하고, export 결과만 `full_text`, URL, 태그, 조회조건 기록을 포함한다.

**Tech Stack:** Node.js ESM, 기존 JSON 파일(`output_total/total_full_YYYYMMDD.json`), 기존 태그 파일(`web_viewer/sns_tags.json`), 기존 CLI 검증 스크립트.

---

## 범위

포함:
- `node utils/query-sns.mjs export recent 20 --format md`
- `node utils/query-sns.mjs export search "리서치" --limit 30 --format md`
- `node utils/query-sns.mjs export by-tag "클로드" --from 2026-05-01 --format md`
- `node utils/query-sns.mjs export by-platform linkedin --format json`
- export 파일 상단의 출처/조회조건 기록
- 기본 저장 위치 `output_exports/`

제외:
- SQLite/DB 전환
- 복수 쿼리 bundle 또는 `--query-file`
- 웹 뷰어 UI 변경
- 태그 추가/삭제 write path
- 기존 `json_to_md.py` 리팩터링

범위 경계:
- 복수 쿼리 bundle은 이번 MVP 제외다. 단일 조회 결과를 하나의 md/json 파일로 묶는 것까지만 구현한다.

## 영향받는 저장 대상

- 읽기 전용:
  - `output_total/total_full_YYYYMMDD.json`
  - `web_viewer/sns_tags.json`
- 새 산출물:
  - `output_exports/*.md`
  - `output_exports/*.json`
- 기존 데이터 재처리:
  - 필요 없음
- `.gitignore` 영향:
  - `output_*` 패턴이 이미 있어 `output_exports/`는 기본적으로 git 추적 대상이 아니다.

## 파일 구조

| 파일 | 작업 | 책임 |
|---|---|---|
| `utils/query-sns.mjs` | 수정 | `export` 명령, full-text export payload, Markdown 렌더링, 파일 저장 |
| `tests/verify_query_sns_cli.mjs` | 수정 | 실제 최신 데이터 기준 CLI export 동작 검증 |
| `README.md` | 수정 | SNS 조회 CLI 섹션에 export 사용 예시 추가 |

## Task 1: CLI 사용법과 옵션 파서 확장

**Files:**
- Modify: `utils/query-sns.mjs`
- Test: `tests/verify_query_sns_cli.mjs`

- [ ] **Step 1: `--out`과 `md` format 기대 테스트가 존재한다**

`tests/verify_query_sns_cli.mjs`의 `main()`에 아래 검증을 추가한다.

```js
const helpForExport = runCli(['--help']);
assert.match(helpForExport.stderr, /export <command>/, 'help에 export 명령이 없습니다.');
assert.match(helpForExport.stderr, /--out <path>/, 'help에 --out 옵션이 없습니다.');
assert.match(helpForExport.stderr, /json\|brief\|md/, 'help에 md format 안내가 없습니다.');

const nonExportMd = runCli(['recent', '1', '--format', 'md']);
assert.notEqual(nonExportMd.status, 0, 'export가 아닌 명령에서 --format md가 성공하면 안 됩니다.');
assert.match(nonExportMd.stderr, /md format is only supported for export/, 'non-export md 실패 메시지가 부정확합니다.');
```

- [ ] **Step 2: 실패 확인 명령이 실패한다**

Run:

```powershell
node tests/verify_query_sns_cli.mjs
```

Expected:

```markdown
FAIL: help에 export 명령이 없습니다.
```

- [ ] **Step 3: `printUsage()`와 `parseArgs()`가 export 옵션을 인식한다**

`utils/query-sns.mjs`에서 사용법을 아래 의미로 확장한다.

```js
function printUsage() {
  process.stderr.write(`Usage: node utils/query-sns.mjs <command> [args] [options]

Commands:
  recent [N]
  get <platform_id>
  search <keyword>
  by-platform <platform>
  by-user <keyword>
  by-tag <tag>
  tag list [url]
  stats
  export <command> [args]

Options:
  --platform <platform>   Filter by platform
  --from <YYYY-MM-DD>     Include posts from this date
  --to <YYYY-MM-DD>       Include posts until this date
  --limit <N>             Limit results (default: 10)
  --format <json|brief|md> Output format (default: json; md is for export)
  --out <path>            Export output path
  --help, -h              Show this help
`);
}
```

`parseArgs()`의 기본 option에 `out: ''`를 추가하고 `--out`을 파싱한다. `--format` 허용값은 `json`, `brief`, `md`로 확장하되, `md`는 `export` 외 명령에서 `md format is only supported for export` 메시지로 실패하게 한다.

```js
} else if (value === '--out' && args[index + 1]) {
  options.out = args[++index];
}
```

- [ ] **Step 4: help 검증이 통과한다**

Run:

```powershell
node tests/verify_query_sns_cli.mjs
```

Expected:

```markdown
help 관련 assertion은 통과한다.
아직 export 실행 검증을 추가하지 않았으면 전체 스크립트는 기존 검증까지 PASS한다.
```

## Task 2: export payload와 Markdown 렌더러 추가

**Files:**
- Modify: `utils/query-sns.mjs`
- Test: `tests/verify_query_sns_cli.mjs`

- [ ] **Step 1: export md 파일 검증 테스트가 존재한다**

`tests/verify_query_sns_cli.mjs`에 export 산출물 검증을 추가한다.

```js
const exportDir = path.join(projectRoot, 'test_runs');
fs.mkdirSync(exportDir, { recursive: true });
const exportMdPath = path.join(exportDir, `query-sns-export-test-${Date.now()}.md`);

const exportMd = runCli(['export', 'recent', '1', '--format', 'md', '--out', exportMdPath]);
assert.equal(exportMd.status, 0, `export md 실패\nSTDERR:\n${exportMd.stderr}`);
const exportSummary = JSON.parse(exportMd.stdout);
assert.equal(exportSummary.command, 'export');
assert.equal(exportSummary.export.format, 'md');
assert.equal(exportSummary.export.output_path.replaceAll('\\', '/'), path.relative(projectRoot, exportMdPath).replaceAll('\\', '/'));
assert.equal(fs.existsSync(exportMdPath), true, 'export md 파일이 생성되지 않았습니다.');

const mdText = fs.readFileSync(exportMdPath, 'utf8');
assert.match(mdText, /^# SNS 조회 Export/m, 'md 제목이 없습니다.');
assert.match(mdText, /## 출처\/조회조건/m, '출처/조회조건 섹션이 없습니다.');
assert.match(mdText, /실행한 조회:/, '실행한 조회 기록이 없습니다.');
assert.match(mdText, /사용한 데이터:/, '사용 데이터 파일 기록이 없습니다.');
assert.match(mdText, /저장된 결과:/, '저장된 결과 수 기록이 없습니다.');
assert.match(mdText, /## 1\. /, '첫 번째 게시글 섹션이 없습니다.');
```

- [ ] **Step 2: 실패 확인 명령이 실패한다**

Run:

```powershell
node tests/verify_query_sns_cli.mjs
```

Expected:

```markdown
FAIL: unknown command: export
```

- [ ] **Step 3: export 전용 full-text result를 만든다**

`utils/query-sns.mjs`에 일반 조회용 `postToResult()`와 분리된 export 전용 mapper를 추가한다.

```js
function postToExportResult(post, tags, extras = {}) {
  return {
    sequence_id: post.sequence_id ?? null,
    platform_id: post.platform_id || '',
    code: post.code || post.platform_id || '',
    sns_platform: normalizePlatformName(post.sns_platform),
    username: post.username || '',
    display_name: post.display_name || post.username || '',
    url: resolvePostUrl(post),
    created_at: post.created_at || '',
    date: post.date || extractDateValue(post),
    full_text: post.full_text || '',
    media: Array.isArray(post.media) ? post.media : [],
    local_images: Array.isArray(post.local_images) ? post.local_images : [],
    tags,
    ...extras,
  };
}
```

- [ ] **Step 4: KST 시각과 파일 경로 helper를 추가한다**

아래 helper를 `utils/query-sns.mjs`에 추가한다.

```js
function formatKstTimestamp(date = new Date()) {
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
  return `${parts} KST`;
}

function makeSafeSlug(value = 'export') {
  const slug = String(value || 'export')
    .normalize('NFKC')
    .replace(/[^0-9A-Za-z가-힣_-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60);
  return slug || 'export';
}

function resolveExportPath(options, exportCommand, keyword, format) {
  const extension = format === 'json' ? 'json' : 'md';
  const basePath = options.out
    ? path.resolve(PROJECT_ROOT, options.out)
    : path.join(PROJECT_ROOT, 'output_exports', `sns_export_${makeSafeSlug(exportCommand)}_${makeSafeSlug(keyword)}.${extension}`);

  if (!fs.existsSync(basePath)) return basePath;

  const parsed = path.parse(basePath);
  const stamp = formatKstTimestamp().slice(0, 16).replace(/[-: ]/g, '');
  return path.join(parsed.dir, `${parsed.name}_${stamp}${parsed.ext}`);
}
```

- [ ] **Step 5: Markdown 렌더러를 추가한다**

```js
function renderMarkdownExport(payload, context) {
  const lines = [
    '# SNS 조회 Export',
    '',
    '## 출처/조회조건',
    '',
    `- 생성일: ${context.generatedAt}`,
    `- 실행한 조회: \`${context.invocation}\``,
    `- 사용한 데이터: \`${context.dataFile}\``,
    `- 사용한 태그 파일: ${context.tagsFile ? `\`${context.tagsFile}\`` : '없음'}`,
    `- 전체 검색 결과: ${payload.total_matches}`,
    `- 저장된 결과: ${payload.returned}`,
    '',
    '---',
    '',
  ];

  payload.posts.forEach((post, index) => {
    const author = post.display_name || post.username || 'unknown';
    const username = post.username ? `@${post.username}` : 'unknown';
    const tags = post.tags.length > 0 ? post.tags.join(', ') : '없음';
    lines.push(`## ${index + 1}. [${post.date || 'unknown'}] ${author} (${username}) - ${post.sns_platform || 'unknown'}`);
    lines.push('');
    lines.push(`- URL: ${post.url ? `[Original](${post.url})` : '없음'}`);
    lines.push(`- ID: ${post.platform_id || post.code || '없음'}`);
    lines.push(`- Tags: ${tags}`);
    if (Array.isArray(post.match_fields) && post.match_fields.length > 0) {
      lines.push(`- Match fields: ${post.match_fields.join(', ')}`);
    }
    lines.push('');
    lines.push(post.full_text || '(본문 없음)');
    lines.push('');
    lines.push('---');
    lines.push('');
  });

  return lines.join('\n');
}
```

- [ ] **Step 6: Markdown export 테스트가 통과한다**

Run:

```powershell
node tests/verify_query_sns_cli.mjs
```

Expected:

```markdown
export md 파일이 `test_runs/query-sns-export-test.md`에 생성된다.
파일 본문이 `# SNS 조회 Export`, `## 출처/조회조건`, `## 1.`을 포함한다.
```

## Task 3: export 명령 dispatcher 구현

**Files:**
- Modify: `utils/query-sns.mjs`
- Test: `tests/verify_query_sns_cli.mjs`

- [ ] **Step 1: export json 검증 테스트가 존재한다**

`tests/verify_query_sns_cli.mjs`에 JSON export 검증을 추가한다.

```js
const exportJsonPath = path.join(exportDir, 'query-sns-export-test.json');
const exportJsonPath = path.join(exportDir, `query-sns-export-test-${Date.now()}.json`);
const exportJson = runCli(['export', 'search', '없는키워드', '--format', 'json', '--out', exportJsonPath]);
assert.equal(exportJson.status, 0, `export json 실패\nSTDERR:\n${exportJson.stderr}`);
const exportJsonSummary = JSON.parse(exportJson.stdout);
assert.equal(exportJsonSummary.command, 'export');
assert.equal(exportJsonSummary.export.format, 'json');
assert.equal(exportJsonSummary.total_matches, 0);
assert.equal(exportJsonSummary.returned, 0);
assert.equal(fs.existsSync(exportJsonPath), true, 'export json 파일이 생성되지 않았습니다.');
const exportedJson = loadJson(exportJsonPath);
assert.equal(exportedJson.command, 'search');
assert.equal(exportedJson.total_matches, 0);
assert.deepEqual(exportedJson.posts, []);

const exportBrief = runCli(['export', 'recent', '1', '--format', 'brief']);
assert.notEqual(exportBrief.status, 0, 'export --format brief가 성공하면 안 됩니다.');
assert.match(exportBrief.stderr, /export format must be json or md/, 'export brief 실패 메시지가 부정확합니다.');
```

- [ ] **Step 2: export command builder를 추가한다**

일반 조회 switch를 재사용하기 위해 payload builder를 분리한다.

```js
function buildPayload({ data, posts, file, tagsMap, options }) {
  switch (options.command) {
    case 'recent':
      return cmdRecent(posts, tagsMap, options);
    case 'get':
      return cmdGet(posts, tagsMap, options.positional[0]);
    case 'search':
      return cmdSearch(posts, tagsMap, options.positional[0], options);
    case 'by-platform':
      return cmdByPlatform(posts, tagsMap, options.positional[0], options);
    case 'by-user':
      return cmdByUser(posts, tagsMap, options.positional[0], options);
    case 'by-tag':
      return cmdByTag(posts, tagsMap, options.positional[0], options);
    case 'tag':
      if (options.positional[0] !== 'list') fail('supported tag subcommand: list');
      return cmdTagList(posts, tagsMap, options.positional[1]);
    case 'stats':
      return cmdStats(posts, tagsMap, file, options, data);
    default:
      fail(`unknown command: ${options.command}`);
  }
}
```

- [ ] **Step 3: export 대상 명령을 list command로 제한한다**

`export`의 MVP는 다건 게시글 목록에 집중한다.

```js
const EXPORTABLE_COMMANDS = new Set(['recent', 'search', 'by-platform', 'by-user', 'by-tag']);
```

`get`, `stats`, `tag list` export는 이번 범위에서 실패시킨다.

```js
if (!EXPORTABLE_COMMANDS.has(exportCommand)) {
  fail(`export supports: ${[...EXPORTABLE_COMMANDS].join(', ')}`);
}
```

- [ ] **Step 4: `cmdExport()`를 구현한다**

```js
function cmdExport(context, options) {
  const [exportCommand, ...exportPositionals] = options.positional;
  if (!exportCommand) fail('export requires a command');
  if (!EXPORTABLE_COMMANDS.has(exportCommand)) {
    fail(`export supports: ${[...EXPORTABLE_COMMANDS].join(', ')}`);
  }

  const innerOptions = {
    ...options,
    command: exportCommand,
    positional: exportPositionals,
    format: 'json',
  };
  const payload = buildPayload({ ...context, options: innerOptions });
  const exportPosts = payload.posts.map((result) => {
    const source = context.posts.find((post) => post.sequence_id != null && post.sequence_id === result.sequence_id) ||
      context.posts.find((post) =>
        normalizePlatformName(post.sns_platform) === result.sns_platform &&
        String(post.platform_id || post.code) === String(result.platform_id || result.code)
      );
    return source
      ? postToExportResult(source, result.tags || [], {
          match_fields: result.match_fields || [],
        })
      : result;
  });

  const exportPayload = {
    ...payload,
    posts: exportPosts,
  };

  const format = options.format === 'json' ? 'json' : 'md';
  const outputPath = resolveExportPath(options, exportCommand, exportPositionals.join('_'), format);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });

  const dataFile = path.relative(PROJECT_ROOT, context.file).replace(/\\/g, '/');
  const tagsFile = fs.existsSync(TAGS_PATH) ? path.relative(PROJECT_ROOT, TAGS_PATH).replace(/\\/g, '/') : null;
  const invocation = process.argv.slice(2).join(' ');
  const generatedAt = formatKstTimestamp();

  const fileContent = format === 'json'
    ? `${JSON.stringify(exportPayload, null, 2)}\n`
    : renderMarkdownExport(exportPayload, { generatedAt, invocation, dataFile, tagsFile });
  fs.writeFileSync(outputPath, fileContent, 'utf8');

  return {
    command: 'export',
    source_command: exportCommand,
    total_matches: exportPayload.total_matches,
    returned: exportPayload.returned,
    export: {
      format,
      output_path: path.relative(PROJECT_ROOT, outputPath).replace(/\\/g, '/'),
    },
  };
}
```

- [ ] **Step 5: `main()` switch가 export를 호출한다**

`main()`의 switch를 `buildPayload()` 호출로 줄이고, `export`만 별도로 처리한다.

```js
const context = { data, posts, file, tagsMap };
const payload = options.command === 'export'
  ? cmdExport(context, options)
  : buildPayload({ ...context, options });
printPayload(payload, options.command === 'export' ? { ...options, format: 'json' } : options);
```

- [ ] **Step 6: export md/json 검증이 통과한다**

Run:

```powershell
node tests/verify_query_sns_cli.mjs
```

Expected:

```markdown
모든 기존 CLI 검증이 통과한다.
export md/json 검증이 통과한다.
```

## Task 4: README 사용 예시 추가

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README에 export 예시가 존재한다**

`README.md`의 `SNS 데이터 조회 CLI` 섹션 아래에 아래 내용을 추가한다.

````markdown
조회 결과를 강의 재료나 리서치 노트로 저장하려면 `export`를 사용합니다.

```powershell
node utils/query-sns.mjs export search "리서치" --limit 30 --format md
node utils/query-sns.mjs export by-tag "클로드" --from 2026-05-01 --format md
node utils/query-sns.mjs export by-platform linkedin --format json --out output_exports/linkedin.json
```

기본 저장 위치는 `output_exports/`이며, Markdown export에는 생성일, 실행한 조회, 사용 데이터 파일, 태그 파일, 전체/저장 결과 수가 함께 기록됩니다.
````

- [ ] **Step 2: README 문구 확인이 통과한다**

Run:

```powershell
rg -n "query-sns\\.mjs export|output_exports|출처/조회조건|강의 재료" README.md
```

Expected:

```markdown
README.md에서 export 예시와 기본 저장 위치 설명이 검색된다.
```

## Task 5: 최종 검증

**Files:**
- Verify only

- [ ] **Step 1: 전체 CLI 검증이 통과한다**

Run:

```powershell
node tests/verify_query_sns_cli.mjs
```

Expected:

```markdown
프로세스 exit code 0.
기존 `stats`, `recent`, `get`, `search`, `by-platform`, `by-tag`, `tag list`, `brief` 검증과 export md/json 검증이 모두 통과한다.
```

- [ ] **Step 2: 검색 helper unit test가 통과한다**

Run:

```powershell
node --test tests/query_sns_search_helpers.test.mjs
```

Expected:

```markdown
# pass 3
# fail 0
```

- [ ] **Step 3: 수동 smoke export가 통과한다**

Run:

```powershell
node utils/query-sns.mjs export search "리서치" --limit 2 --format md --out test_runs/query-sns-export-smoke.md
```

Expected:

```json
{
  "command": "export",
  "source_command": "search",
  "returned": 2,
  "export": {
    "format": "md",
    "output_path": "test_runs/query-sns-export-smoke.md"
  }
}
```

Then run:

```powershell
rg -n "SNS 조회 Export|출처/조회조건|사용한 데이터|## 1\\." test_runs/query-sns-export-smoke.md
```

Expected:

```markdown
4개 패턴이 모두 검색된다.
```

- [ ] **Step 4: 저장 데이터 불변성이 확인된다**

Run:

```powershell
git diff -- output_total web_viewer/sns_tags.json web_viewer/sns_tag_catalog.json
```

Expected:

```markdown
출력 없음.
```

## Self-Review

- Spec coverage: 단일 조회 결과를 md/json으로 저장, 출처/조회조건 기록, raw JSON 직접 접근 회피, 강의/리서치 재사용성을 모두 포함했다.
- Placeholder scan: `TBD`, `TODO`, `나중에 구현` 없음.
- Type consistency: `options.out`, `formatKstTimestamp`, `postToExportResult`, `cmdExport`, `buildPayload` 명칭이 전 task에서 일관된다.
- Scope risk: 복수 쿼리 bundle은 MVP 후속으로 제외했다. DB 전환과 태그 write path도 제외해 기존 저장 데이터 오염 위험을 낮췄다.

---

## 실행 결과

**실행일:** 2026-05-18 KST

### Plan 보완 반영

- `plan-check-lite` 지적사항을 반영했다.
- 테스트 코드에서 `fs.rmSync` 직접 삭제 계획을 제거하고, `Date.now()` 기반 고유 파일명으로 변경했다.
- `export --format brief` 실패 검증을 추가했다.
- export가 아닌 일반 조회에서 `--format md` 사용 시 실패하도록 계획과 구현을 맞췄다.
- source post 매칭은 `sequence_id` 우선, fallback은 `sns_platform + platform_id/code`로 보완했다.
- 복수 쿼리 bundle은 후속 범위이며, 이번 MVP는 단일 조회 결과를 하나의 md/json 파일로 저장하는 것으로 명확히 했다.

### 구현 완료

| 항목 | 결과 | 확인 근거 |
|---|---|---|
| CLI help 확장 | 완료 | `export <command>`, `--out <path>`, `json|brief|md` 표시 |
| Markdown export | 완료 | `# SNS 조회 Export`, `## 출처/조회조건`, 게시글 섹션 생성 |
| JSON export | 완료 | export된 JSON에 원 조회 command, total/returned, posts 포함 |
| format 경계 | 완료 | 일반 조회 `--format md` 실패, export `--format brief` 실패 |
| README 예시 | 완료 | `query-sns.mjs export` 예시와 `output_exports/` 설명 추가 |
| 저장 데이터 불변성 | 확인 제한 | `output_total`, 태그 JSON은 구현에서 쓰지 않았다. 다만 작업 시작 전부터 `web_viewer/sns_tags.json`, `web_viewer/sns_tag_catalog.json`, `output_total/total_full_20260516.json`, `output_total/total_full_20260518.json` 변경이 워킹트리에 있어 diff 출력 자체는 비어 있지 않았다. |

### 검증 결과

```powershell
node tests/verify_query_sns_cli.mjs
```

결과: exit code 0.

```powershell
node --test tests/query_sns_search_helpers.test.mjs
```

결과: 통과.

```powershell
node utils/query-sns.mjs export search "리서치" --limit 2 --format md --out test_runs/query-sns-export-smoke.md
```

결과: `test_runs/query-sns-export-smoke.md` 생성 및 출처/조회조건 섹션 확인.

```powershell
git diff -- output_total web_viewer/sns_tags.json web_viewer/sns_tag_catalog.json
```

결과: 이번 구현으로 인한 변경 없음. 단, 작업 시작 전부터 해당 경로 일부에는 기존 워킹트리 변경이 있었다.

실제 확인: 위 명령은 기존 `web_viewer/sns_tags.json`, `web_viewer/sns_tag_catalog.json` 변경 때문에 diff를 출력했다. 이번 구현 파일은 `utils/query-sns.mjs`, `tests/verify_query_sns_cli.mjs`, `README.md`, 본 계획 문서로 한정된다.
