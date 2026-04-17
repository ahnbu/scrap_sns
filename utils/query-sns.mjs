import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PROJECT_ROOT = path.resolve(__dirname, '..');
const OUTPUT_TOTAL_DIR = path.join(PROJECT_ROOT, 'output_total');
const TAGS_PATH = path.join(PROJECT_ROOT, 'web_viewer', 'sns_tags.json');

function printUsage() {
  process.stderr.write(`Usage: node utils/query-sns.mjs <command> [args] [options]

Commands:
  recent [N]
  get <platform_id>
  search <keyword>
  by-platform <platform>
  by-user <keyword>
  by-tag <tag>
  tag list [url]
  stats

Options:
  --platform <platform>   Filter by platform
  --from <YYYY-MM-DD>     Include posts from this date
  --to <YYYY-MM-DD>       Include posts until this date
  --limit <N>             Limit results (default: 10)
  --format <json|brief>   Output format (default: json)
  --help, -h              Show this help
`);
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, ''));
}

function resolveLatestJson() {
  if (!fs.existsSync(OUTPUT_TOTAL_DIR)) {
    throw new Error(`output directory not found: ${OUTPUT_TOTAL_DIR}`);
  }

  const files = fs
    .readdirSync(OUTPUT_TOTAL_DIR)
    .filter((name) => /^total_full_\d{8}\.json$/.test(name))
    .sort();

  if (files.length === 0) {
    throw new Error('no total_full_YYYYMMDD.json file found');
  }

  return path.join(OUTPUT_TOTAL_DIR, files[files.length - 1]);
}

function loadPosts() {
  const file = resolveLatestJson();
  const data = readJson(file);
  const posts = Array.isArray(data) ? data : data.posts || [];

  if (!Array.isArray(posts)) {
    throw new Error('latest data file does not contain a posts array');
  }

  return { data, posts, file };
}

function loadTags() {
  if (!fs.existsSync(TAGS_PATH)) {
    return {};
  }

  const data = readJson(TAGS_PATH);
  return data && typeof data === 'object' ? data : {};
}

function normalizePlatformName(value = '') {
  const normalized = String(value).trim().toLowerCase();

  if (!normalized) return '';
  if (normalized === 'x' || normalized === 'twitter' || normalized === '트위터') return 'x';
  if (normalized === 'threads' || normalized === 'thread' || normalized === '스레드') return 'threads';
  if (normalized === 'linkedin' || normalized === '링크드인') return 'linkedin';
  return normalized;
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const options = {
    command: null,
    positional: [],
    platform: '',
    from: '',
    to: '',
    limit: 10,
    format: 'json',
  };

  let index = 0;
  while (index < args.length) {
    const value = args[index];
    if (value === '--help' || value === '-h') {
      printUsage();
      process.exit(0);
    } else if (value === '--platform' && args[index + 1]) {
      options.platform = normalizePlatformName(args[++index]);
    } else if (value === '--from' && args[index + 1]) {
      options.from = args[++index];
    } else if (value === '--to' && args[index + 1]) {
      options.to = args[++index];
    } else if (value === '--limit' && args[index + 1]) {
      const parsed = Number.parseInt(args[++index], 10);
      if (!Number.isFinite(parsed) || parsed < 0) {
        fail('invalid --limit value');
      }
      options.limit = parsed;
    } else if (value === '--format' && args[index + 1]) {
      options.format = args[++index];
    } else if (!options.command) {
      options.command = value;
    } else {
      options.positional.push(value);
    }
    index += 1;
  }

  if (!['json', 'brief'].includes(options.format)) {
    fail('invalid --format value. expected json or brief');
  }

  return options;
}

function extractDateValue(post) {
  return String(post.created_at || post.date || '').slice(0, 10);
}

function extractSortValue(post) {
  return String(post.created_at || post.date || '');
}

function sortByCreatedDesc(posts) {
  return [...posts].sort((left, right) => extractSortValue(right).localeCompare(extractSortValue(left)));
}

function resolvePostUrl(post) {
  const normalizeThreadsUrl = (url) => {
    if (!url || typeof url !== 'string') return '';
    return url
      .replace(/^https?:\/\/www\.threads\.net\//, 'https://www.threads.com/')
      .replace(/^https?:\/\/threads\.net\//, 'https://www.threads.com/')
      .replace(/^https?:\/\/threads\.com\//, 'https://www.threads.com/');
  };

  if (post.url) {
    return normalizeThreadsUrl(post.url) || post.url;
  }

  const platform = normalizePlatformName(post.sns_platform);
  if (platform === 'threads') {
    const user = post.username || post.user;
    const code = post.platform_id || post.code;
    if (user && code) {
      return `https://www.threads.com/@${user}/post/${code}`;
    }
  }

  if (platform === 'threads') {
    return normalizeThreadsUrl(post.post_url || post.source_url || '');
  }

  return post.post_url || post.source_url || '';
}

function getTagsForPost(post, tagsMap) {
  const key = resolvePostUrl(post);
  const tags = key ? tagsMap[key] : [];
  return Array.isArray(tags) ? tags : [];
}

function createExcerpt(text, limit = 120) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit - 3)}...`;
}

function postToResult(post, tags, extras = {}) {
  return {
    sequence_id: post.sequence_id ?? null,
    platform_id: post.platform_id || '',
    code: post.code || post.platform_id || '',
    sns_platform: normalizePlatformName(post.sns_platform),
    username: post.username || '',
    display_name: post.display_name || post.username || '',
    url: resolvePostUrl(post),
    created_at: post.created_at || '',
    date: post.date || extractDateValue(post),
    text_excerpt: createExcerpt(post.full_text, 140),
    media_count: Array.isArray(post.media) ? post.media.length : 0,
    tags,
    ...extras,
  };
}

function formatBrief(post) {
  const platform = post.sns_platform || 'unknown';
  const user = post.username || post.display_name || 'unknown';
  const date = post.date || String(post.created_at || '').slice(0, 10) || 'unknown';
  const text = createExcerpt(post.text_excerpt || post.full_text || '', 80);
  const tags = Array.isArray(post.tags) && post.tags.length > 0 ? ` [${post.tags.join(', ')}]` : '';
  return `[${platform}] @${user} (${date}) ${text}${tags}`.trim();
}

function applyFilters(posts, options) {
  return posts.filter((post) => {
    const postPlatform = normalizePlatformName(post.sns_platform);
    const postDate = extractDateValue(post);

    if (options.platform && postPlatform !== options.platform) {
      return false;
    }
    if ((options.from || options.to) && !postDate) {
      return false;
    }
    if (options.from && postDate && postDate < options.from) {
      return false;
    }
    if (options.to && postDate && postDate > options.to) {
      return false;
    }
    return true;
  });
}

function limitPosts(posts, limit) {
  return limit > 0 ? posts.slice(0, limit) : posts;
}

function buildListEnvelope(command, basePosts, mappedPosts, extras = {}) {
  return {
    command,
    total_matches: basePosts.length,
    returned: mappedPosts.length,
    posts: mappedPosts,
    ...extras,
  };
}

function cmdRecent(posts, tagsMap, options) {
  const filtered = sortByCreatedDesc(applyFilters(posts, options));
  const limit = Number.parseInt(options.positional[0], 10) || options.limit;
  const limited = limitPosts(filtered, limit);
  return buildListEnvelope(
    'recent',
    filtered,
    limited.map((post) => postToResult(post, getTagsForPost(post, tagsMap)))
  );
}

function cmdGet(posts, tagsMap, platformId) {
  if (!platformId) {
    fail('get requires a platform_id');
  }

  const found = posts.find((post) => String(post.platform_id) === platformId) ||
    posts.find((post) => String(post.code) === platformId);

  if (!found) {
    return { command: 'get', found: false, platform_id: platformId };
  }

  return {
    command: 'get',
    found: true,
    platform_id: platformId,
    post: {
      ...found,
      url: resolvePostUrl(found),
      tags: getTagsForPost(found, tagsMap),
    },
  };
}

function cmdByPlatform(posts, tagsMap, platform, options) {
  const normalizedPlatform = normalizePlatformName(platform);
  if (!normalizedPlatform) {
    fail('by-platform requires a platform name');
  }

  const filtered = sortByCreatedDesc(
    applyFilters(posts, { ...options, platform: normalizedPlatform })
  );
  const limited = limitPosts(filtered, options.limit);

  return buildListEnvelope(
    'by-platform',
    filtered,
    limited.map((post) => postToResult(post, getTagsForPost(post, tagsMap))),
    { platform: normalizedPlatform }
  );
}

function cmdByUser(posts, tagsMap, keyword, options) {
  const needle = String(keyword || '').trim().toLowerCase();
  if (!needle) {
    fail('by-user requires a username or display name keyword');
  }

  const filtered = sortByCreatedDesc(
    applyFilters(posts, options).filter((post) => {
      const username = String(post.username || '').toLowerCase();
      const displayName = String(post.display_name || '').toLowerCase();
      return username.includes(needle) || displayName.includes(needle);
    })
  );
  const limited = limitPosts(filtered, options.limit);

  return buildListEnvelope(
    'by-user',
    filtered,
    limited.map((post) => postToResult(post, getTagsForPost(post, tagsMap))),
    { keyword }
  );
}

function cmdSearch(posts, tagsMap, keyword, options) {
  const needle = String(keyword || '').trim().toLowerCase();
  if (!needle) {
    fail('search requires a keyword');
  }

  const matched = applyFilters(posts, options)
    .flatMap((post) => {
      const tags = getTagsForPost(post, tagsMap);
      const matchFields = [];

      if (String(post.full_text || '').toLowerCase().includes(needle)) {
        matchFields.push('full_text');
      }
      if (String(post.display_name || '').toLowerCase().includes(needle)) {
        matchFields.push('display_name');
      }
      if (String(post.username || '').toLowerCase().includes(needle)) {
        matchFields.push('username');
      }
      if (tags.some((tag) => String(tag).toLowerCase().includes(needle))) {
        matchFields.push('tags');
      }

      if (matchFields.length === 0) {
        return [];
      }

      return [{ post, tags, matchFields }];
    })
    .sort((left, right) => extractSortValue(right.post).localeCompare(extractSortValue(left.post)));

  const limited = limitPosts(matched, options.limit);
  return buildListEnvelope(
    'search',
    matched,
    limited.map(({ post, tags, matchFields }) => postToResult(post, tags, { match_fields: matchFields })),
    { keyword }
  );
}

function cmdByTag(posts, tagsMap, tag, options) {
  const needle = String(tag || '').trim().toLowerCase();
  if (!needle) {
    fail('by-tag requires a tag value');
  }

  const filtered = sortByCreatedDesc(
    applyFilters(posts, options).filter((post) =>
      getTagsForPost(post, tagsMap).some((item) => String(item).toLowerCase() === needle)
    )
  );
  const limited = limitPosts(filtered, options.limit);

  return buildListEnvelope(
    'by-tag',
    filtered,
    limited.map((post) => postToResult(post, getTagsForPost(post, tagsMap))),
    { tag }
  );
}

function resolveTagLookup(posts, tagsMap, lookup) {
  if (!lookup) return '';
  if (tagsMap[lookup]) return lookup;

  const found = posts.find((post) => {
    const resolvedUrl = resolvePostUrl(post);
    return resolvedUrl === lookup || String(post.platform_id) === lookup || String(post.code) === lookup;
  });

  return found ? resolvePostUrl(found) : lookup;
}

function cmdTagList(posts, tagsMap, lookup) {
  const resolved = resolveTagLookup(posts, tagsMap, lookup);

  if (lookup) {
    return {
      command: 'tag list',
      lookup,
      resolved_url: resolved,
      tags: Array.isArray(tagsMap[resolved]) ? tagsMap[resolved] : [],
    };
  }

  const counts = new Map();
  for (const value of Object.values(tagsMap)) {
    if (!Array.isArray(value)) continue;
    for (const tag of value) {
      counts.set(tag, (counts.get(tag) || 0) + 1);
    }
  }

  const tags = [...counts.entries()]
    .map(([name, count]) => ({ tag: name, count }))
    .sort((left, right) => right.count - left.count || left.tag.localeCompare(right.tag));

  return {
    command: 'tag list',
    total_tags: tags.length,
    tags,
  };
}

function cmdStats(posts, tagsMap, dataFile, options, data) {
  const filtered = applyFilters(posts, options);
  const platformCounts = {};
  const tagCounts = new Map();
  const authorCounts = new Map();
  const dates = [];

  for (const post of filtered) {
    const platform = normalizePlatformName(post.sns_platform) || 'unknown';
    platformCounts[platform] = (platformCounts[platform] || 0) + 1;

    const authorKey = post.display_name || post.username || 'unknown';
    authorCounts.set(authorKey, (authorCounts.get(authorKey) || 0) + 1);

    const date = extractDateValue(post);
    if (date) {
      dates.push(date);
    }

    const uniqueTags = new Set(getTagsForPost(post, tagsMap));
    for (const tag of uniqueTags) {
      tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
    }
  }

  const topTags = [...tagCounts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((left, right) => right.count - left.count || left.tag.localeCompare(right.tag))
    .slice(0, 20);

  const topAuthors = [...authorCounts.entries()]
    .map(([author, count]) => ({ author, count }))
    .sort((left, right) => right.count - left.count || left.author.localeCompare(right.author))
    .slice(0, 10);

  const sortedDates = dates.sort();
  return {
    command: 'stats',
    total_posts: filtered.length,
    platform_counts: platformCounts,
    date_range: {
      from: sortedDates[0] || null,
      to: sortedDates[sortedDates.length - 1] || null,
    },
    top_tags: topTags,
    top_authors: topAuthors,
    files: {
      posts: path.relative(PROJECT_ROOT, dataFile).replace(/\\/g, '/'),
      tags: fs.existsSync(TAGS_PATH) ? path.relative(PROJECT_ROOT, TAGS_PATH).replace(/\\/g, '/') : null,
    },
    metadata: data && typeof data === 'object' && !Array.isArray(data) ? data.metadata || null : null,
  };
}

function renderBrief(payload) {
  if (Array.isArray(payload.posts)) {
    return payload.posts.map((post) => formatBrief(post)).join('\n');
  }
  if (payload.post) {
    return formatBrief(postToResult(payload.post, payload.post.tags || []));
  }
  if (payload.command === 'tag list' && Array.isArray(payload.tags)) {
    return payload.tags
      .map((entry) => (typeof entry === 'string' ? entry : `${entry.tag} (${entry.count})`))
      .join('\n');
  }
  if (payload.command === 'stats') {
    const platforms = Object.entries(payload.platform_counts)
      .map(([name, count]) => `${name}:${count}`)
      .join(', ');
    return `total=${payload.total_posts} range=${payload.date_range.from || '-'}..${payload.date_range.to || '-'} platforms=${platforms}`;
  }
  return JSON.stringify(payload, null, 2);
}

function printPayload(payload, options) {
  if (options.format === 'brief') {
    process.stdout.write(`${renderBrief(payload)}\n`);
    return;
  }
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
}

function main() {
  const options = parseArgs(process.argv);
  if (!options.command) {
    printUsage();
    process.exit(0);
  }

  try {
    const { data, posts, file } = loadPosts();
    const tagsMap = loadTags();

    let payload;
    switch (options.command) {
      case 'recent':
        payload = cmdRecent(posts, tagsMap, options);
        break;
      case 'get':
        payload = cmdGet(posts, tagsMap, options.positional[0]);
        break;
      case 'search':
        payload = cmdSearch(posts, tagsMap, options.positional[0], options);
        break;
      case 'by-platform':
        payload = cmdByPlatform(posts, tagsMap, options.positional[0], options);
        break;
      case 'by-user':
        payload = cmdByUser(posts, tagsMap, options.positional[0], options);
        break;
      case 'by-tag':
        payload = cmdByTag(posts, tagsMap, options.positional[0], options);
        break;
      case 'tag':
        if (options.positional[0] !== 'list') {
          fail('supported tag subcommand: list');
        }
        payload = cmdTagList(posts, tagsMap, options.positional[1]);
        break;
      case 'stats':
        payload = cmdStats(posts, tagsMap, file, options, data);
        break;
      default:
        fail(`unknown command: ${options.command}`);
    }

    printPayload(payload, options);
  } catch (error) {
    process.stderr.write(`Error: ${error.message}\n`);
    process.exit(1);
  }
}

main();
