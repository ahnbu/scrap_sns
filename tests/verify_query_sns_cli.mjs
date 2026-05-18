import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');
const cliPath = path.join(projectRoot, 'utils', 'query-sns.mjs');
const outputTotalDir = path.join(projectRoot, 'output_total');
const tagsPath = path.join(projectRoot, 'web_viewer', 'sns_tags.json');

function resolveLatestJson() {
  const candidates = fs
    .readdirSync(outputTotalDir)
    .filter((name) => /^total_full_\d{8}\.json$/.test(name))
    .sort();

  assert.ok(candidates.length > 0, '최신 total_full_YYYYMMDD.json 파일이 없습니다.');
  return path.join(outputTotalDir, candidates[candidates.length - 1]);
}

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, ''));
}

function runCli(args) {
  return spawnSync(process.execPath, [cliPath, ...args], {
    cwd: projectRoot,
    encoding: 'utf8',
  });
}

function expectSuccess(args, validate) {
  const result = runCli(args);
  assert.equal(
    result.status,
    0,
    `명령 실패: node utils/query-sns.mjs ${args.join(' ')}\nSTDERR:\n${result.stderr}`
  );

  let payload;
  try {
    payload = JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(
      `JSON 파싱 실패: node utils/query-sns.mjs ${args.join(' ')}\nSTDOUT:\n${result.stdout}\n원인: ${error.message}`
    );
  }

  validate(payload);
}

function main() {
  const latestData = loadJson(resolveLatestJson());
  const posts = Array.isArray(latestData) ? latestData : latestData.posts || [];
  const tags = loadJson(tagsPath);
  const firstTag = Object.values(tags).find((value) => Array.isArray(value) && value.length > 0)?.[0];

  const help = runCli(['--help']);
  assert.equal(help.status, 0, `--help 실패\nSTDERR:\n${help.stderr}`);
  assert.match(help.stderr, /Usage:/, '--help 출력에 Usage가 없습니다.');
  assert.match(help.stderr, /export <command>/, 'help에 export 명령이 없습니다.');
  assert.match(help.stderr, /--out <path>/, 'help에 --out 옵션이 없습니다.');
  assert.match(help.stderr, /json\|brief\|md/, 'help에 md format 안내가 없습니다.');

  const nonExportMd = runCli(['recent', '1', '--format', 'md']);
  assert.notEqual(nonExportMd.status, 0, 'export가 아닌 명령에서 --format md가 성공하면 안 됩니다.');
  assert.match(
    nonExportMd.stderr,
    /md format is only supported for export/,
    'non-export md 실패 메시지가 부정확합니다.'
  );

  expectSuccess(['stats'], (payload) => {
    assert.equal(payload.command, 'stats');
    assert.equal(payload.total_posts, posts.length);
    assert.ok(payload.platform_counts, 'platform_counts가 없습니다.');
  });

  expectSuccess(['recent', '3'], (payload) => {
    assert.equal(payload.command, 'recent');
    assert.equal(payload.returned, 3);
    assert.equal(payload.posts.length, 3);
  });

  expectSuccess(['get', '7253208054928744448'], (payload) => {
    assert.equal(payload.command, 'get');
    assert.equal(payload.found, true);
    assert.ok(payload.post.sns_platform, 'sns_platform 누락');
    assert.ok(payload.post.username, 'username 누락');
    assert.ok(payload.post.url, 'url 누락');
    assert.ok(payload.post.created_at, 'created_at 누락');
  });

  expectSuccess(['search', '없는키워드'], (payload) => {
    assert.equal(payload.command, 'search');
    assert.equal(payload.total_matches, 0);
    assert.equal(payload.returned, 0);
    assert.deepEqual(payload.posts, []);
  });

  expectSuccess(['by-platform', 'threads', '--limit', '3'], (payload) => {
    assert.equal(payload.command, 'by-platform');
    assert.equal(payload.platform, 'threads');
    assert.ok(payload.returned <= 3);
  });

  if (firstTag) {
    expectSuccess(['by-tag', firstTag, '--limit', '5'], (payload) => {
      assert.equal(payload.command, 'by-tag');
      assert.equal(payload.tag, firstTag);
      assert.ok(payload.posts.every((post) => post.tags.includes(firstTag)));
    });
  }

  expectSuccess(['tag', 'list'], (payload) => {
    assert.equal(payload.command, 'tag list');
    assert.ok(Array.isArray(payload.tags), 'tag list 결과가 배열이 아닙니다.');
  });

  const brief = runCli(['recent', '2', '--format', 'brief']);
  assert.equal(brief.status, 0, `brief 포맷 실패\nSTDERR:\n${brief.stderr}`);
  assert.equal(
    brief.stdout
      .trim()
      .split(/\r?\n/)
      .filter(Boolean).length,
    2,
    'brief 출력 줄 수가 recent 개수와 다릅니다.'
  );

  const exportDir = path.join(projectRoot, 'test_runs');
  fs.mkdirSync(exportDir, { recursive: true });
  const exportMdPath = path.join(exportDir, `query-sns-export-test-${Date.now()}.md`);
  const exportMd = runCli(['export', 'recent', '1', '--format', 'md', '--out', exportMdPath]);
  assert.equal(exportMd.status, 0, `export md 실패\nSTDERR:\n${exportMd.stderr}`);
  const exportSummary = JSON.parse(exportMd.stdout);
  assert.equal(exportSummary.command, 'export');
  assert.equal(exportSummary.export.format, 'md');
  assert.equal(
    exportSummary.export.output_path.replaceAll('\\', '/'),
    path.relative(projectRoot, exportMdPath).replaceAll('\\', '/')
  );
  assert.equal(fs.existsSync(exportMdPath), true, 'export md 파일이 생성되지 않았습니다.');

  const mdText = fs.readFileSync(exportMdPath, 'utf8');
  assert.match(mdText, /^# SNS 조회 Export/m, 'md 제목이 없습니다.');
  assert.match(mdText, /## 출처\/조회조건/m, '출처/조회조건 섹션이 없습니다.');
  assert.match(mdText, /실행한 조회:/, '실행한 조회 기록이 없습니다.');
  assert.match(mdText, /사용한 데이터:/, '사용 데이터 파일 기록이 없습니다.');
  assert.match(mdText, /저장된 결과:/, '저장된 결과 수 기록이 없습니다.');
  assert.match(mdText, /## 1\. /, '첫 번째 게시글 섹션이 없습니다.');

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
}

main();
