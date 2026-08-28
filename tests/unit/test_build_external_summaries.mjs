import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  buildItems,
  diffItems,
  run,
} from "../../scripts/build_external_summaries.mjs";

const LILYS = {
  source: "lilys",
  collected_at_kst: "2026-08-28 18:00:00 KST",
  items: [
    { video_id: "fPgZhHMJc_I", url: "https://lilys.ai/digest/11132480" },
    { video_id: "bA2Rg0JE7xA", url: "https://lilys.ai/digest/11127660" },
  ],
};

const LIVEWIKI = {
  source: "livewiki",
  collected_at_kst: "2026-08-28 18:01:00 KST",
  items: [
    {
      video_id: "bA2Rg0JE7xA",
      url: "https://livewiki.com/ko/content/8900bc8e-053d-4214-9a42-051fb59f5a60",
    },
    {
      video_id: "XgGWUXVJzdg",
      url: "https://livewiki.com/ko/content/d33d3097-7dec-4d40-a0ce-0a87b23c9c46",
    },
  ],
};

async function tempDir() {
  return mkdtemp(path.join(os.tmpdir(), "ext-summaries-"));
}

async function writeJson(filePath, payload) {
  await writeFile(filePath, JSON.stringify(payload), "utf8");
  return filePath;
}

test("U1 두 입력을 합치면 같은 영상에 두 링크가 함께 매달린다", () => {
  const items = buildItems(LILYS, LIVEWIKI);

  assert.deepEqual(items.bA2Rg0JE7xA, {
    lilys: "https://lilys.ai/digest/11127660",
    livewiki: "https://livewiki.com/ko/content/8900bc8e-053d-4214-9a42-051fb59f5a60",
  });
  // 한쪽에만 있는 영상은 없는 쪽이 null 로 남는다.
  assert.equal(items.fPgZhHMJc_I.livewiki, null);
  assert.equal(items.XgGWUXVJzdg.lilys, null);
  // 키는 정렬돼 있어야 매 실행 diff 가 흔들리지 않는다.
  assert.deepEqual(Object.keys(items), [...Object.keys(items)].sort());
});

test("U2 한쪽 입력만 있어도 실패하지 않고 없는 쪽은 null 이다", async () => {
  const dir = await tempDir();
  const lilysPath = await writeJson(path.join(dir, "lilys.json"), LILYS);
  const outPath = path.join(dir, "out.json");

  const result = await run({
    lilys: lilysPath,
    livewiki: path.join(dir, "missing-livewiki.json"),
    out: outPath,
  });

  assert.equal(result.skipped, false);
  const saved = JSON.parse(await readFile(outPath, "utf8"));
  assert.equal(saved.sources.livewiki, null);
  assert.equal(saved.sources.lilys.count, 2);
  assert.equal(saved.total_video_count, 2);
  assert.equal(saved.items.fPgZhHMJc_I.livewiki, null);
});

test("U3 입력이 둘 다 없으면 기존 출력을 덮어쓰지 않는다", async () => {
  const dir = await tempDir();
  const outPath = path.join(dir, "out.json");
  const existing = { generated_at_kst: "이전 성공본", items: { keepme: { lilys: "x", livewiki: null } } };
  await writeJson(outPath, existing);

  const result = await run({
    lilys: path.join(dir, "missing-lilys.json"),
    livewiki: path.join(dir, "missing-livewiki.json"),
    out: outPath,
  });

  assert.equal(result.skipped, true);
  assert.equal(result.reason, "no-input");
  const after = JSON.parse(await readFile(outPath, "utf8"));
  assert.deepEqual(after, existing);
});

test("U3b dry-run 은 계산만 하고 저장하지 않는다", async () => {
  const dir = await tempDir();
  const lilysPath = await writeJson(path.join(dir, "lilys.json"), LILYS);
  const livewikiPath = await writeJson(path.join(dir, "livewiki.json"), LIVEWIKI);
  const outPath = path.join(dir, "out.json");

  const result = await run({
    lilys: lilysPath,
    livewiki: livewikiPath,
    out: outPath,
    "dry-run": true,
  });

  assert.equal(result.skipped, true);
  assert.equal(result.reason, "dry-run");
  assert.equal(result.payload.total_video_count, 3);
  await assert.rejects(() => readFile(outPath, "utf8"));
});

test("diffItems 는 추가·삭제·갱신·유지를 나눠 센다", () => {
  const before = {
    a: { lilys: "1", livewiki: null },
    b: { lilys: null, livewiki: "2" },
  };
  const after = {
    a: { lilys: "1", livewiki: null },
    b: { lilys: "3", livewiki: "2" },
    c: { lilys: null, livewiki: "4" },
  };

  const delta = diffItems(before, after);
  assert.deepEqual(delta.added, ["c"]);
  assert.deepEqual(delta.removed, []);
  assert.deepEqual(delta.changed, ["b"]);
  assert.equal(delta.kept, 1);
});

test("잘못된 입력 파일은 조용히 넘기지 않고 끊는다", async () => {
  const dir = await tempDir();
  const badPath = path.join(dir, "bad.json");
  await writeFile(badPath, JSON.stringify({ source: "lilys" }), "utf8");

  await assert.rejects(
    () => run({ lilys: badPath, livewiki: path.join(dir, "none.json"), out: path.join(dir, "o.json") }),
    /items 배열이 없습니다/
  );
});
