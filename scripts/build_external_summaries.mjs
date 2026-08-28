/**
 * 외부 요약 매핑 빌더.
 *
 * `scripts/lilys_library.mjs list` 와 `scripts/livewiki_library.mjs list` 산출물을 합쳐
 * 영상 ID 하나에 두 서비스 링크를 매다는 매핑 파일을 만든다.
 * 뷰어는 이 파일에 있는 영상에만 외부 요약 아이콘을 렌더한다.
 *
 * 입력 (둘 다 재생성 가능한 파생물이라 git 무시 대상이다)
 *   output_external/lilys_library.json
 *   output_external/livewiki_library.json
 *
 * 출력 (뷰어가 읽는 정본이라 git 추적 대상이다)
 *   web_viewer/sns_external_summaries.json
 *
 * 한쪽 수집이 실패해도 다른 쪽 아이콘은 살아야 한다.
 * 그래서 입력이 하나만 있어도 진행하고, 없는 쪽은 null 로 둔다.
 * 둘 다 없으면 기존 출력을 건드리지 않고 종료한다 - 마지막 성공본을 지키는 쪽이 낫다.
 *
 * 사용법
 *   node scripts/build_external_summaries.mjs [--dry-run]
 *     [--lilys <path>] [--livewiki <path>] [--out <path>]
 */

import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);

const DEFAULT_LILYS = path.join('output_external', 'lilys_library.json');
const DEFAULT_LIVEWIKI = path.join('output_external', 'livewiki_library.json');
const DEFAULT_OUT = path.join('web_viewer', 'sns_external_summaries.json');

function nowKst() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(new Date()).reduce((acc, p) => { acc[p.type] = p.value; return acc; }, {});
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} KST`;
}

function readLibrary(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return null;
  const raw = fs.readFileSync(filePath, 'utf8').replace(/^﻿/, '');
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed.items)) {
    throw new Error(`${filePath}: items 배열이 없습니다. 수집기를 다시 실행하세요.`);
  }
  return parsed;
}

function readExistingItems(outPath) {
  if (!fs.existsSync(outPath)) return {};
  try {
    const parsed = JSON.parse(fs.readFileSync(outPath, 'utf8').replace(/^﻿/, ''));
    return (parsed && typeof parsed.items === 'object' && parsed.items) || {};
  } catch (_) {
    return {};
  }
}

/** 영상 ID -> {lilys, livewiki}. 키는 정렬해 넣어 매 실행마다 diff 가 흔들리지 않게 한다. */
export function buildItems(lilys, livewiki) {
  const merged = new Map();
  const put = (videoId, key, url) => {
    if (!videoId || !url) return;
    const entry = merged.get(videoId) || { lilys: null, livewiki: null };
    entry[key] = url;
    merged.set(videoId, entry);
  };
  for (const item of lilys?.items || []) put(item.video_id, 'lilys', item.url);
  for (const item of livewiki?.items || []) put(item.video_id, 'livewiki', item.url);

  const items = {};
  for (const videoId of [...merged.keys()].sort()) items[videoId] = merged.get(videoId);
  return items;
}

export function diffItems(before, after) {
  const beforeKeys = new Set(Object.keys(before || {}));
  const afterKeys = new Set(Object.keys(after || {}));
  const added = [...afterKeys].filter((k) => !beforeKeys.has(k));
  const removed = [...beforeKeys].filter((k) => !afterKeys.has(k));
  const changed = [...afterKeys].filter((k) => beforeKeys.has(k)
    && JSON.stringify(before[k]) !== JSON.stringify(after[k]));
  return { added, removed, changed, kept: afterKeys.size - added.length - changed.length };
}

function parseArgs(argv) {
  const options = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (!argv[i].startsWith('--')) continue;
    const key = argv[i].slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith('--')) { options[key] = next; i += 1; } else { options[key] = true; }
  }
  return options;
}

/** 테스트가 인자를 직접 넘길 수 있도록 main 과 분리한다. 반환값으로 결과를 검사한다. */
export async function run(options = {}) {
  const lilysPath = path.resolve(options.lilys || DEFAULT_LILYS);
  const livewikiPath = path.resolve(options.livewiki || DEFAULT_LIVEWIKI);
  const outPath = path.resolve(options.out || DEFAULT_OUT);
  const dryRun = Boolean(options['dry-run']);

  const lilys = readLibrary(lilysPath);
  const livewiki = readLibrary(livewikiPath);

  if (!lilys && !livewiki) {
    process.stdout.write([
      '입력이 하나도 없습니다. 기존 출력을 그대로 둡니다.',
      `  ${lilysPath}`,
      `  ${livewikiPath}`,
      '먼저 수집기를 실행하세요:',
      '  node scripts/lilys_library.mjs list',
      '  node scripts/livewiki_library.mjs list',
      '',
    ].join('\n'));
    return { skipped: true, reason: 'no-input', outPath };
  }
  if (!lilys) process.stdout.write('⚠ Lilys 입력이 없습니다. LiveWiki 만으로 진행합니다.\n');
  if (!livewiki) process.stdout.write('⚠ LiveWiki 입력이 없습니다. Lilys 만으로 진행합니다.\n');

  const items = buildItems(lilys, livewiki);
  const before = readExistingItems(outPath);
  const delta = diffItems(before, items);

  const payload = {
    generated_at_kst: nowKst(),
    sources: {
      lilys: lilys
        ? { collected_at_kst: lilys.collected_at_kst || '', count: lilys.items.length }
        : null,
      livewiki: livewiki
        ? { collected_at_kst: livewiki.collected_at_kst || '', count: livewiki.items.length }
        : null,
    },
    total_video_count: Object.keys(items).length,
    items,
  };

  process.stdout.write([
    `영상 ${payload.total_video_count}건`
      + ` (Lilys ${lilys ? lilys.items.length : 0} · LiveWiki ${livewiki ? livewiki.items.length : 0})`,
    `변경: 추가 ${delta.added.length} / 삭제 ${delta.removed.length}`
      + ` / 갱신 ${delta.changed.length} / 유지 ${delta.kept}`,
  ].join('\n') + '\n');

  if (dryRun) {
    process.stdout.write(`[dry-run] 저장하지 않았습니다: ${outPath}\n`);
    return { skipped: true, reason: 'dry-run', payload, delta, outPath };
  }

  await fsp.mkdir(path.dirname(outPath), { recursive: true });
  const tmp = `${outPath}.tmp`;
  await fsp.writeFile(tmp, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  await fsp.rename(tmp, outPath);
  process.stdout.write(`저장: ${outPath}\n`);
  return { skipped: false, payload, delta, outPath };
}

async function main() {
  return run(parseArgs(process.argv.slice(2)));
}

// 테스트에서 import 할 때는 실행하지 않는다.
if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
