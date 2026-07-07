import assert from "node:assert/strict";
import test from "node:test";

import {
  compareCanonicalPostSets,
  comparePostSets,
  extractPosts,
  getPostId,
} from "../../scripts/linkedin_shadow_compare.mjs";

test("extractPosts supports arrays and metadata-wrapped posts", () => {
  const posts = [{ platform_id: "1" }];

  assert.deepEqual(extractPosts(posts), posts);
  assert.deepEqual(extractPosts({ posts }), posts);
  assert.deepEqual(extractPosts({ data: posts }), posts);
  assert.deepEqual(extractPosts({}), []);
});

test("getPostId prefers platform_id and falls back to code", () => {
  assert.equal(getPostId({ platform_id: "747" }), "747");
  assert.equal(getPostId({ code: "fallback" }), "fallback");
  assert.equal(getPostId({}), "");
});

test("comparePostSets reports common, missing, shadow-only, and quality mismatches", () => {
  const shadowPosts = [
    {
      platform_id: "1",
      sns_platform: "linkedin",
      display_name: "Same Author",
      full_text: "same text",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:1",
      media: ["a", "b"],
    },
    {
      platform_id: "3",
      sns_platform: "linkedin",
      display_name: "Shadow Only",
      full_text: "new text",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:3",
      media: [],
    },
  ];
  const linkedinFullPosts = [
    {
      platform_id: "1",
      sns_platform: "linkedin",
      display_name: "Same Author",
      full_text: "same text",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:1",
      media: ["a"],
    },
    {
      platform_id: "2",
      sns_platform: "linkedin",
      display_name: "Missing Author",
      full_text: "baseline only",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:2",
      media: [],
    },
  ];

  const report = comparePostSets({ shadowPosts, linkedinFullPosts, totalPosts: [] });

  assert.deepEqual(report.common_ids, ["1"]);
  assert.deepEqual(report.missing_from_shadow_candidates, ["2"]);
  assert.deepEqual(report.shadow_only_candidates, ["3"]);
  assert.deepEqual(report.media_count_mismatch, [
    {
      platform_id: "1",
      shadow_media_count: 2,
      baseline_media_count: 1,
    },
  ]);
  assert.equal(report.counts.shadow, 2);
  assert.equal(report.counts.baseline_unique, 2);
  assert.equal(report.go_no_go_recommendation, "trial_fallback");
});

test("compareCanonicalPostSets classifies wrapper baseline as wrapper instead of real missing", () => {
  const shadowPosts = [
    {
      platform_id: "7449713771888971776",
      sns_platform: "linkedin",
      full_text: "Original saved post",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:7449713771888971776",
      diagnostics: {
        saved_activity_id: "7449713771888971776",
        entity_activity_id: "7449713771888971776",
        embedded_activity_ids: [],
        canonical_activity_id: "7449713771888971776",
        save_state_verified: true,
        cluster_reference_verified: true,
      },
    },
  ];
  const baselinePosts = [
    {
      platform_id: "7450664369769816064",
      sns_platform: "linkedin",
      full_text: "외우, 중요",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:7450664369769816064",
      canonical_activity_id: "7449713771888971776",
    },
    {
      platform_id: "999",
      sns_platform: "linkedin",
      full_text: "Actually missing",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:999",
      canonical_activity_id: "999",
    },
    {
      platform_id: "888",
      sns_platform: "linkedin",
      full_text: "Needs raw evidence",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:888",
    },
  ];

  const report = compareCanonicalPostSets({ shadowPosts, baselinePosts });

  assert.deepEqual(report.baseline_only_wrapper.map((item) => item.platform_id), ["7450664369769816064"]);
  assert.deepEqual(report.real_opencli_missing.map((item) => item.platform_id), ["999"]);
  assert.deepEqual(report.needs_raw_evidence.map((item) => item.platform_id), ["888"]);
  assert.equal(report.shadow_diagnostics[0].save_state_verified, true);
  assert.equal(report.shadow_diagnostics[0].cluster_reference_verified, true);
});
