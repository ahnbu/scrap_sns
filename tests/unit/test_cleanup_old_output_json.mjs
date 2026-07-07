import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  TARGETS,
  getKstTodayYmd,
  listTargetFiles,
  planCleanup,
  parseArgs,
} from "../../scripts/cleanup_old_output_json.mjs";

async function touchJson(root, relativePath) {
  const filePath = path.join(root, relativePath);
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, "{\"posts\":[]}\n", "utf8");
  return filePath;
}

test("parseArgs defaults to dry-run and rejects apply plus dry-run together", () => {
  assert.equal(parseArgs([]).mode, "dry-run");
  assert.throws(() => parseArgs(["--apply", "--dry-run"]), /Choose only one/);
});

test("getKstTodayYmd formats the current day in KST", () => {
  assert.equal(getKstTodayYmd(new Date("2026-07-06T16:00:00.000Z")), "20260707");
});

test("listTargetFiles returns only exact date-stamped target files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sns-cleanup-list-"));
  await touchJson(root, "output_threads/python/threads_py_full_20260411.json");
  await touchJson(root, "output_threads/python/threads_py_full_20260411.json.bak");
  await touchJson(root, "output_threads/python/threads_py_full_20260411_20260417_122609.bak.json");
  await touchJson(root, "output_threads/python/update/threads_py_full_update_20260411_120000.json");
  await touchJson(root, "output_total/total_full_20260411.md");

  const files = await listTargetFiles(
    root,
    TARGETS.find((target) => target.id === "threads_full"),
  );

  assert.equal(files.length, 1);
  assert.equal(path.basename(files[0].path), "threads_py_full_20260411.json");
  assert.equal(files[0].ymd, "20260411");
});

test("planCleanup keeps today, latest 5, recent 30 days, and monthly latest", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sns-cleanup-"));
  const dates = [
    "20260201",
    "20260213",
    "20260310",
    "20260318",
    "20260411",
    "20260425",
    "20260501",
    "20260529",
    "20260603",
    "20260614",
    "20260623",
    "20260707",
  ];

  for (const ymd of dates) {
    await touchJson(root, `output_total/total_full_${ymd}.json`);
  }

  const plan = await planCleanup({
    root,
    todayYmd: "20260707",
    keepDays: 30,
    keepLatest: 5,
    targets: [TARGETS.find((target) => target.id === "total_full")],
  });

  const kept = plan.groups[0].keep.map((item) => path.basename(item.path)).sort();
  const cleanup = plan.groups[0].delete.map((item) => path.basename(item.path)).sort();

  assert.deepEqual(kept, [
    "total_full_20260213.json",
    "total_full_20260318.json",
    "total_full_20260425.json",
    "total_full_20260529.json",
    "total_full_20260603.json",
    "total_full_20260614.json",
    "total_full_20260623.json",
    "total_full_20260707.json",
  ]);
  assert.deepEqual(cleanup, [
    "total_full_20260201.json",
    "total_full_20260310.json",
    "total_full_20260411.json",
    "total_full_20260501.json",
  ]);
});
