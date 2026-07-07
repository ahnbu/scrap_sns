import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMediaAudit,
  classifyMediaSource,
  extractPosts,
  selectSpotcheckSamples,
} from "../../scripts/linkedin_media_audit.mjs";

test("classifyMediaSource labels embedded feedshare image as post media", () => {
  const result = classifyMediaSource({
    path: "$.body.included[19].entityEmbeddedObject.image.attributes[0].detailData.vectorImage.rootUrl",
    url: "https://media.licdn.com/dms/image/v2/D5622AQEF/feedshare-image-high-res/example",
  });

  assert.equal(result.label, "post_media_confirmed");
});

test("classifyMediaSource labels profile and company images as actor false positives", () => {
  const profile = classifyMediaSource({
    path: "$.body.included[19].image.attributes[0].detailData.nonEntityProfilePicture.vectorImage.artifacts[0].fileIdentifyingUrlPathSegment",
    url: "https://media.licdn.com/dms/image/v2/D5603AQ/profile-displayphoto-scale_100_100/example",
  });
  const company = classifyMediaSource({
    path: "$.body.included[20].image.attributes[0].detailData.companyLogo.vectorImage.artifacts[0].fileIdentifyingUrlPathSegment",
    url: "https://media.licdn.com/dms/image/v2/C4D0BAQ/company-logo_100_100/example",
  });

  assert.equal(profile.label, "actor_image_false_positive");
  assert.equal(company.label, "actor_image_false_positive");
});

test("classifyMediaSource labels article thumbnails separately", () => {
  const result = classifyMediaSource({
    path: "$.body.included[10].articleComponent.coverImage.attributes[0].detailData.vectorImage.rootUrl",
    url: "https://media.licdn.com/dms/image/v2/D4E12AQ/articleshare-shrink_800/example",
  });

  assert.equal(result.label, "article_or_link_thumbnail");
});

test("buildMediaAudit labels mismatches and preserves post context", () => {
  const compareReport = {
    media_count_mismatch: [
      {
        platform_id: "100",
        shadow_media_count: 1,
        baseline_media_count: 0,
      },
    ],
  };
  const shadowPosts = [
    {
      platform_id: "100",
      url: "https://www.linkedin.com/feed/update/urn:li:activity:100",
      full_text: "Saved post with media",
      media: ["https://media.licdn.com/dms/image/v2/D5622AQEF/feedshare-shrink_1280/example"],
    },
  ];
  const baselinePosts = [
    {
      platform_id: "100",
      media: [],
    },
  ];
  const rawRecords = [
    {
      file: "raw.json",
      body: {
        included: [
          {
            trackingUrn: "urn:li:activity:100",
            entityEmbeddedObject: {
              image: {
                attributes: [
                  {
                    detailData: {
                      vectorImage: {
                        rootUrl: "https://media.licdn.com/dms/image/v2/D5622AQEF/feedshare-",
                      },
                    },
                  },
                ],
              },
            },
          },
        ],
      },
    },
  ];

  const audit = buildMediaAudit({ compareReport, shadowPosts, baselinePosts, rawRecords });

  assert.equal(audit.summary.total_mismatch, 1);
  assert.equal(audit.summary.post_media_confirmed, 1);
  assert.equal(audit.items[0].platform_id, "100");
  assert.equal(audit.items[0].raw_path.includes("entityEmbeddedObject.image"), true);
  assert.equal(audit.items[0].post_url, "https://www.linkedin.com/feed/update/urn:li:activity:100");
});

test("selectSpotcheckSamples takes deterministic samples per label", () => {
  const audit = {
    items: [
      { platform_id: "2", label: "post_media_confirmed" },
      { platform_id: "1", label: "post_media_confirmed" },
      { platform_id: "3", label: "actor_image_false_positive" },
    ],
  };

  assert.deepEqual(selectSpotcheckSamples(audit, 1).map((item) => item.platform_id), ["1", "3"]);
});

test("extractPosts supports array and wrapped data", () => {
  const posts = [{ platform_id: "1" }];

  assert.deepEqual(extractPosts(posts), posts);
  assert.deepEqual(extractPosts({ posts }), posts);
  assert.deepEqual(extractPosts({ data: posts }), posts);
  assert.deepEqual(extractPosts({}), []);
});
