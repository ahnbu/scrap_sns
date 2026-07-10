import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { applyExistingStreak, loadExistingIdsFile } from "../../scripts/linkedin_opencli_shadow_collect.mjs";

test("applyExistingStreak reaches limit after consecutive existing IDs", () => {
  const existingIds = new Set(Array.from({ length: 25 }, (_, index) => `old-${index + 1}`));
  const orderedIds = Array.from({ length: 20 }, (_, index) => `old-${index + 1}`);

  const result = applyExistingStreak(orderedIds, existingIds, 0, 20);

  assert.deepEqual(result, { streak: 20, reached: true });
});

test("applyExistingStreak resets streak when a new ID appears", () => {
  const existingIds = new Set(["old-1", "old-2", "old-3"]);

  const result = applyExistingStreak(["old-1", "old-2", "new-1", "old-3"], existingIds, 0, 3);

  assert.deepEqual(result, { streak: 1, reached: false });
});

test("applyExistingStreak ignores duplicate IDs that were already seen by caller", () => {
  const existingIds = new Set(["old-1", "old-2"]);

  const result = applyExistingStreak(["old-1", "old-2"], existingIds, 18, 20);

  assert.deepEqual(result, { streak: 20, reached: true });
});

test("applyExistingStreak is disabled when limit is zero", () => {
  const existingIds = new Set(["old-1"]);

  const result = applyExistingStreak(["old-1"], existingIds, 0, 0);

  assert.deepEqual(result, { streak: 1, reached: false });
});

test("loadExistingIdsFile reads platform IDs from JSON array", () => {
  const dir = mkdtempSync(join(tmpdir(), "linkedin-existing-"));
  const file = join(dir, "existing_ids.json");
  writeFileSync(file, `${JSON.stringify(["111", "222", "", null])}\n`, "utf8");
  try {
    const result = loadExistingIdsFile(file);
    assert.deepEqual([...result].sort(), ["111", "222"]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
