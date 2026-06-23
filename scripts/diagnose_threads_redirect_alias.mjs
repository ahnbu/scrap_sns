import fs from "node:fs";
import path from "node:path";

const aliasCode = process.argv[2];

if (!aliasCode) {
  console.error("Usage: node scripts/diagnose_threads_redirect_alias.mjs <alias_code>");
  process.exit(2);
}

function readJson(filePath) {
  const text = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(text);
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

function findCanonical(posts, aliasPost) {
  const explicitCode =
    aliasPost?.duplicate_of ||
    aliasPost?.canonical_code ||
    aliasPost?.canonicalCode ||
    null;
  if (explicitCode) {
    return posts.find((post) => post.code === explicitCode || post.platform_id === explicitCode);
  }

  return posts.find((post) => {
    const code = post.code || post.platform_id;
    if (!code || code === aliasCode) {
      return false;
    }
    return post.root_code === aliasCode || post.requested_code === aliasCode;
  });
}

const repoRoot = path.resolve(import.meta.dirname, "..");
const totalPath = latestFile(path.join(repoRoot, "output_total"), /^total_full_\d+\.json$/);

if (!totalPath) {
  console.error("No output_total/total_full_*.json file found.");
  process.exit(1);
}

const totalData = readJson(totalPath);
const posts = Array.isArray(totalData.posts) ? totalData.posts : [];
const aliasPost = posts.find((post) => post.code === aliasCode || post.platform_id === aliasCode);
const canonicalPost = findCanonical(posts, aliasPost);

if (!aliasPost || !canonicalPost) {
  console.log(`alias_code=${aliasCode}`);
  console.log("status=not_detected");
  console.log(`source_file=${totalPath}`);
  process.exit(0);
}

const canonicalCode = canonicalPost.code || canonicalPost.platform_id || "";

console.log(`alias_code=${aliasCode}`);
console.log(`alias_url=${aliasPost.url || ""}`);
console.log(`canonical_code=${canonicalCode}`);
console.log(`canonical_url=${canonicalPost.url || ""}`);
console.log("action=remove_alias_card_from_total_and_link_to_canonical");
console.log(`source_file=${totalPath}`);
