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
}

main();
