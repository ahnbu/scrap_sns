import fs from "node:fs";
import path from "node:path";

const aliasCode = process.argv[2];
const mode = process.argv.includes("--apply") ? "apply" : "dry-run";

if (!aliasCode || (!process.argv.includes("--dry-run") && !process.argv.includes("--apply"))) {
  console.error("Usage: node scripts/fix_threads_redirect_alias.mjs <alias_code> --dry-run|--apply");
  process.exit(2);
}

function readJson(filePath) {
  const text = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(text);
}

function writeJson(filePath, data) {
  fs.writeFileSync(filePath, `\uFEFF${JSON.stringify(data, null, 4)}\n`, "utf8");
}

function latestFile(dirPath, pattern) {
  if (!fs.existsSync(dirPath)) {
    return null;
  }
  return fs
    .readdirSync(dirPath)
    .filter((name) => pattern.test(name))
    .sort()
    .reverse()
    .map((name) => path.join(dirPath, name))[0] || null;
}

function codeOf(post) {
  return post?.code || post?.platform_id || "";
}

function findCanonical(posts, aliasPost) {
  const explicitCode = aliasPost?.duplicate_of || aliasPost?.canonical_code || null;
  if (explicitCode) {
    return posts.find((post) => codeOf(post) === explicitCode);
  }

  return posts.find((post) => {
    const code = codeOf(post);
    if (!code || code === aliasCode) {
      return false;
    }
    return post.root_code === aliasCode || post.requested_code === aliasCode;
  });
}

function aliasPayload(aliasPost, canonicalPost) {
  return {
    code: aliasCode,
    url: aliasPost?.url || `https://www.threads.com/@${aliasPost?.username || ""}/post/${aliasCode}`,
    username: aliasPost?.username || "",
    duplicate_of: codeOf(canonicalPost),
  };
}

function addRedirectAlias(post, alias) {
  const aliases = Array.isArray(post.redirect_aliases) ? post.redirect_aliases : [];
  if (!aliases.some((item) => item.code === alias.code && item.url === alias.url)) {
    aliases.push(alias);
  }
  post.redirect_aliases = aliases;
}

function markSimpleAlias(post, canonicalPost, aliasPost) {
  post.detail_status = "duplicate_of_canonical";
  post.duplicate_of = codeOf(canonicalPost);
  post.canonical_code = codeOf(canonicalPost);
  post.canonical_username = canonicalPost.username || "";
  post.requested_url = aliasPost.url || post.url || "";
  post.final_url = canonicalPost.url || "";
  post.is_detail_collected = true;
}

function summarizePosts(posts) {
  return posts.map((post) => ({
    sequence_id: post.sequence_id,
    code: codeOf(post),
    username: post.username,
    detail_status: post.detail_status || null,
    duplicate_of: post.duplicate_of || null,
    root_code: post.root_code || null,
  }));
}

function formatKstIso(date = new Date()) {
  const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
  return kst.toISOString().slice(0, 19);
}

function updateMetadata(data, posts) {
  data.metadata = data.metadata || {};
  data.metadata.total_count = posts.length;
  data.metadata.max_sequence_id = Math.max(0, ...posts.map((post) => Number(post.sequence_id) || 0));
  data.metadata.updated_at = formatKstIso();
}

function updateTotalMetadata(data, posts) {
  updateMetadata(data, posts);
  data.metadata.threads_count = posts.filter((post) => {
    const platform = String(post.sns_platform || "").toLowerCase();
    return platform === "threads" || platform === "thread";
  }).length;
  data.metadata.linkedin_count = posts.filter((post) => String(post.sns_platform || "").toLowerCase() === "linkedin").length;
  data.metadata.twitter_count = posts.filter((post) => {
    const platform = String(post.sns_platform || "").toLowerCase();
    return platform === "x" || platform === "twitter";
  }).length;
}

function backupFiles(files) {
  const stamp = new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14);
  const backupDir = path.join(repoRoot, "tmp", `threads_redirect_alias_backup_${stamp}`);
  fs.mkdirSync(backupDir, { recursive: true });
  for (const filePath of files) {
    fs.copyFileSync(filePath, path.join(backupDir, path.basename(filePath)));
  }
  return backupDir;
}

function patchDataSet(data, canonicalCode, aliasPost, canonicalPost, options) {
  const posts = Array.isArray(data.posts) ? data.posts : [];
  let markedSimple = 0;
  let removedAlias = 0;
  let canonicalUpdated = 0;
  const alias = aliasPayload(aliasPost, canonicalPost);

  if (options.keepAlias) {
    for (const post of posts) {
      if (codeOf(post) === aliasCode) {
        markSimpleAlias(post, canonicalPost, aliasPost);
        markedSimple += 1;
      }
    }
    return { posts, markedSimple, removedAlias, canonicalUpdated };
  }

  const keptPosts = [];
  for (const post of posts) {
    if (codeOf(post) === aliasCode) {
      removedAlias += 1;
      continue;
    }
    if (codeOf(post) === canonicalCode) {
      addRedirectAlias(post, alias);
      if (post.root_code === aliasCode) {
        post.root_code = canonicalCode;
      }
      canonicalUpdated += 1;
    }
    keptPosts.push(post);
  }

  data.posts = keptPosts;
  return { posts: keptPosts, markedSimple, removedAlias, canonicalUpdated };
}

const repoRoot = path.resolve(import.meta.dirname, "..");
const simplePath = latestFile(path.join(repoRoot, "output_threads", "python"), /^threads_py_simple_\d+\.json$/);
const fullPath = latestFile(path.join(repoRoot, "output_threads", "python"), /^threads_py_full_\d+\.json$/);
const totalPath = latestFile(path.join(repoRoot, "output_total"), /^total_full_\d+\.json$/);

if (!simplePath || !fullPath || !totalPath) {
  console.error("Required latest simple/full/total files were not found.");
  process.exit(1);
}

const simpleData = readJson(simplePath);
const fullData = readJson(fullPath);
const totalData = readJson(totalPath);
const simplePosts = Array.isArray(simpleData.posts) ? simpleData.posts : [];
const totalPosts = Array.isArray(totalData.posts) ? totalData.posts : [];
const totalAliasPost = totalPosts.find((post) => codeOf(post) === aliasCode);
const totalCanonicalPost = findCanonical(totalPosts, totalAliasPost);
const simpleAliasPost = simplePosts.find((post) => codeOf(post) === aliasCode);
const existingCanonicalPost = totalPosts.find((post) => {
  const aliases = Array.isArray(post.redirect_aliases) ? post.redirect_aliases : [];
  return aliases.some((alias) => alias.code === aliasCode);
});

if (!totalAliasPost || !totalCanonicalPost) {
  if (
    !totalAliasPost &&
    simpleAliasPost?.detail_status === "duplicate_of_canonical" &&
    simpleAliasPost?.duplicate_of &&
    existingCanonicalPost
  ) {
    console.log(JSON.stringify({
      mode,
      alias_code: aliasCode,
      canonical_code: codeOf(existingCanonicalPost),
      status: "already_fixed",
      checks: {
        simple_alias_status: simpleAliasPost.detail_status,
        simple_duplicate_of: simpleAliasPost.duplicate_of,
        total_alias_present: false,
        canonical_has_redirect_alias: true,
      },
      files: {
        simple: simplePath,
        full: fullPath,
        total: totalPath,
      },
    }, null, 2));
    process.exit(0);
  }

  console.log(JSON.stringify({
    mode,
    alias_code: aliasCode,
    status: "not_detected",
    total_file: totalPath,
  }, null, 2));
  process.exit(0);
}

const canonicalCode = codeOf(totalCanonicalPost);
const summary = {
  mode,
  alias_code: aliasCode,
  canonical_code: canonicalCode,
  files: {
    simple: simplePath,
    full: fullPath,
    total: totalPath,
  },
};

const simpleResult = patchDataSet(simpleData, canonicalCode, totalAliasPost, totalCanonicalPost, { keepAlias: true });
const fullResult = patchDataSet(fullData, canonicalCode, totalAliasPost, totalCanonicalPost, { keepAlias: false });
const totalResult = patchDataSet(totalData, canonicalCode, totalAliasPost, totalCanonicalPost, { keepAlias: false });

updateMetadata(fullData, fullData.posts || []);
updateTotalMetadata(totalData, totalData.posts || []);

summary.changes = {
  simple: {
    marked_alias: simpleResult.markedSimple,
    remaining_alias: summarizePosts((simpleData.posts || []).filter((post) => codeOf(post) === aliasCode)),
  },
  full: {
    removed_alias: fullResult.removedAlias,
    canonical_updated: fullResult.canonicalUpdated,
    remaining_targets: summarizePosts((fullData.posts || []).filter((post) => [aliasCode, canonicalCode].includes(codeOf(post)))),
  },
  total: {
    removed_alias: totalResult.removedAlias,
    canonical_updated: totalResult.canonicalUpdated,
    remaining_targets: summarizePosts((totalData.posts || []).filter((post) => [aliasCode, canonicalCode].includes(codeOf(post)))),
  },
};

if (mode === "apply") {
  summary.backup_dir = backupFiles([simplePath, fullPath, totalPath]);
  writeJson(simplePath, simpleData);
  writeJson(fullPath, fullData);
  writeJson(totalPath, totalData);
  summary.status = "applied";
} else {
  summary.status = "dry_run";
}

console.log(JSON.stringify(summary, null, 2));
