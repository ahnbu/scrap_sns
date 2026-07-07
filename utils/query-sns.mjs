import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PROJECT_ROOT = path.resolve(__dirname, '..');
const OUTPUT_TOTAL_DIR = path.join(PROJECT_ROOT, 'output_total');
const TAGS_PATH = path.join(PROJECT_ROOT, 'web_viewer', 'sns_tags.json');
const USER_METADATA_PATH = path.join(PROJECT_ROOT, 'web_viewer', 'sns_user_metadata.json');

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
  export <command> [args]

Options:
  --platform <platform>   Filter by platform
  --from <YYYY-MM-DD>     Include posts from this date
  --to <YYYY-MM-DD>       Include posts until this date
  --limit <N>             Limit results (default: 10)
  --format <json|brief|md> Output format (default: json; md is for export)
  --out <path>            Export output path
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

function loadUserMetadata() {
  if (!fs.existsSync(USER_METADATA_PATH)) {
    return {};
  }

  const data = readJson(USER_METADATA_PATH);
  return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
}

function normalizePlatformName(value = '') {
  const normalized = String(value).trim().toLowerCase();

  if (!normalized) return '';
  if (normalized === 'x' || normalized === 'twitter' || normalized === '트위터') return 'x';
  if (normalized === 'threads' || normalized === 'thread' || normalized === '스레드') return 'threads';
  if (normalized === 'linkedin' || normalized === '링크드인') return 'linkedin';
  return normalized;
}

function normalizeSearchText(value = '') {
  return String(value || '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function splitSearchTerms(value = '') {
  return normalizeSearchText(value).split(' ').filter(Boolean);
}

function matchesSearchText(value, query) {
  const haystack = normalizeSearchText(value);
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return false;
  if (haystack.includes(normalizedQuery)) return true;
  const terms = splitSearchTerms(query);
  return terms.length > 0 && terms.every((term) => haystack.includes(term));
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
    out: '',
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
    } else if (value === '--out' && args[index + 1]) {
      options.out = args[++index];
    } else if (!options.command) {
      options.command = value;
    } else {
      options.positional.push(value);
    }
    index += 1;
  }

  if (!['json', 'brief', 'md'].includes(options.format)) {
    fail('invalid --format value. expected json, brief, or md');
  }
  if (options.format === 'md' && options.command !== 'export') {
    fail('md format is only supported for export');
  }
  if (options.command === 'export' && options.format === 'brief') {
    fail('export format must be json or md');
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

function buildPostKey(post) {
  const platform = normalizePlatformName(post.sns_platform);
  const identifier = post.platform_id || post.code || post.urn;
  if (platform && identifier) {
    return `${platform}:${identifier}`;
  }

  const url = resolvePostUrl(post);
  if (platform && url) {
    return `${platform}:url:${url}`;
  }
  return url ? `url:${url}` : '';
}

function getTagsForPost(post, tagsMap) {
  const key = resolvePostUrl(post);
  const tags = key ? tagsMap[key] : [];
  return Array.isArray(tags) ? tags : [];
}

function getUserNoteForPost(post, userMetadata) {
  const key = post.post_key || buildPostKey(post);
  const entry = key ? userMetadata[key] : null;
  if (!entry || typeof entry !== 'object') {
    return '';
  }
  return String(entry.note || '').trim();
}

function createExcerpt(text, limit = 120) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit - 3)}...`;
}

function formatKstTimestamp(date = new Date()) {
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
  return `${parts} KST`;
}

function makeSafeSlug(value = 'export') {
  const slug = String(value || 'export')
    .normalize('NFKC')
    .replace(/[^0-9A-Za-z가-힣_-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60);
  return slug || 'export';
}

function resolveExportPath(options, exportCommand, keyword, format) {
  const extension = format === 'json' ? 'json' : 'md';
  const basePath = options.out
    ? path.resolve(PROJECT_ROOT, options.out)
    : path.join(
        PROJECT_ROOT,
        'output_exports',
        `sns_export_${makeSafeSlug(exportCommand)}_${makeSafeSlug(keyword)}.${extension}`
      );

  if (!fs.existsSync(basePath)) return basePath;

  const parsed = path.parse(basePath);
  const stamp = formatKstTimestamp().slice(0, 16).replace(/[-: ]/g, '');
  return path.join(parsed.dir, `${parsed.name}_${stamp}${parsed.ext}`);
}

function withOptionalNote(result, note) {
  const trimmed = String(note || '').trim();
  return trimmed ? { ...result, note: trimmed } : result;
}

function postToResult(post, tags, extras = {}) {
  const { note = '', ...restExtras } = extras;
  return withOptionalNote({
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
    ...restExtras,
  }, note);
}

function postToExportResult(post, tags, extras = {}) {
  const { note = '', ...restExtras } = extras;
  return withOptionalNote({
    sequence_id: post.sequence_id ?? null,
    platform_id: post.platform_id || '',
    code: post.code || post.platform_id || '',
    sns_platform: normalizePlatformName(post.sns_platform),
    username: post.username || '',
    display_name: post.display_name || post.username || '',
    url: resolvePostUrl(post),
    created_at: post.created_at || '',
    date: post.date || extractDateValue(post),
    full_text: post.full_text || '',
    media: Array.isArray(post.media) ? post.media : [],
    local_images: Array.isArray(post.local_images) ? post.local_images : [],
    tags,
    ...restExtras,
  }, note);
}

function renderMarkdownExport(payload, context) {
  const lines = [
    '# SNS 조회 Export',
    '',
    '## 출처/조회조건',
    '',
    `- 생성일: ${context.generatedAt}`,
    `- 실행한 조회: \`${context.invocation}\``,
    `- 사용한 데이터: \`${context.dataFile}\``,
    `- 사용한 태그 파일: ${context.tagsFile ? `\`${context.tagsFile}\`` : '없음'}`,
    `- 전체 검색 결과: ${payload.total_matches}`,
    `- 저장된 결과: ${payload.returned}`,
    '',
    '---',
    '',
  ];

  payload.posts.forEach((post, index) => {
    const author = post.display_name || post.username || 'unknown';
    const username = post.username ? `@${post.username}` : 'unknown';
    const tags = post.tags.length > 0 ? post.tags.join(', ') : '없음';
    lines.push(`## ${index + 1}. [${post.date || 'unknown'}] ${author} (${username}) - ${post.sns_platform || 'unknown'}`);
    lines.push('');
    lines.push(`- URL: ${post.url ? `[Original](${post.url})` : '없음'}`);
    lines.push(`- ID: ${post.platform_id || post.code || '없음'}`);
    lines.push(`- Tags: ${tags}`);
    if (post.note) {
      lines.push(`- Note: ${post.note}`);
    }
    if (Array.isArray(post.match_fields) && post.match_fields.length > 0) {
      lines.push(`- Match fields: ${post.match_fields.join(', ')}`);
    }
    lines.push('');
    lines.push(post.full_text || '(본문 없음)');
    lines.push('');
    lines.push('---');
    lines.push('');
  });

  return lines.join('\n');
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

function cmdRecent(posts, tagsMap, userMetadata, options) {
  const filtered = sortByCreatedDesc(applyFilters(posts, options));
  const limit = Number.parseInt(options.positional[0], 10) || options.limit;
  const limited = limitPosts(filtered, limit);
  return buildListEnvelope(
    'recent',
    filtered,
    limited.map((post) => postToResult(post, getTagsForPost(post, tagsMap), {
      note: getUserNoteForPost(post, userMetadata),
    }))
  );
}

function cmdGet(posts, tagsMap, userMetadata, platformId) {
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
    post: withOptionalNote({
      ...found,
      url: resolvePostUrl(found),
      tags: getTagsForPost(found, tagsMap),
    }, getUserNoteForPost(found, userMetadata)),
  };
}

function cmdByPlatform(posts, tagsMap, userMetadata, platform, options) {
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
    limited.map((post) => postToResult(post, getTagsForPost(post, tagsMap), {
      note: getUserNoteForPost(post, userMetadata),
    })),
    { platform: normalizedPlatform }
  );
}

function cmdByUser(posts, tagsMap, userMetadata, keyword, options) {
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
    limited.map((post) => postToResult(post, getTagsForPost(post, tagsMap), {
      note: getUserNoteForPost(post, userMetadata),
    })),
    { keyword }
  );
}

function cmdSearch(posts, tagsMap, userMetadata, keyword, options) {
  const normalizedKeyword = normalizeSearchText(keyword);
  if (!normalizedKeyword) {
    fail('search requires a keyword');
  }

  const matched = applyFilters(posts, options)
    .flatMap((post) => {
      const tags = getTagsForPost(post, tagsMap);
      const note = getUserNoteForPost(post, userMetadata);
      const matchFields = [];

      if (matchesSearchText(post.full_text, keyword)) {
        matchFields.push('full_text');
      }
      if (matchesSearchText(post.display_name, keyword)) {
        matchFields.push('display_name');
      }
      if (matchesSearchText(post.username, keyword)) {
        matchFields.push('username');
      }
      if (tags.some((tag) => matchesSearchText(tag, keyword))) {
        matchFields.push('tags');
      }
      if (matchesSearchText(note, keyword)) {
        matchFields.push('note');
      }

      if (matchFields.length === 0) {
        return [];
      }

      return [{ post, tags, note, matchFields }];
    })
    .sort((left, right) => extractSortValue(right.post).localeCompare(extractSortValue(left.post)));

  const limited = limitPosts(matched, options.limit);
  return buildListEnvelope(
    'search',
    matched,
    limited.map(({ post, tags, note, matchFields }) => postToResult(post, tags, { note, match_fields: matchFields })),
    { keyword }
  );
}

function cmdByTag(posts, tagsMap, userMetadata, tag, options) {
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
    limited.map((post) => postToResult(post, getTagsForPost(post, tagsMap), {
      note: getUserNoteForPost(post, userMetadata),
    })),
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

function buildPayload({ data, posts, file, tagsMap, userMetadata, options }) {
  switch (options.command) {
    case 'recent':
      return cmdRecent(posts, tagsMap, userMetadata, options);
    case 'get':
      return cmdGet(posts, tagsMap, userMetadata, options.positional[0]);
    case 'search':
      return cmdSearch(posts, tagsMap, userMetadata, options.positional[0], options);
    case 'by-platform':
      return cmdByPlatform(posts, tagsMap, userMetadata, options.positional[0], options);
    case 'by-user':
      return cmdByUser(posts, tagsMap, userMetadata, options.positional[0], options);
    case 'by-tag':
      return cmdByTag(posts, tagsMap, userMetadata, options.positional[0], options);
    case 'tag':
      if (options.positional[0] !== 'list') {
        fail('supported tag subcommand: list');
      }
      return cmdTagList(posts, tagsMap, options.positional[1]);
    case 'stats':
      return cmdStats(posts, tagsMap, file, options, data);
    default:
      fail(`unknown command: ${options.command}`);
  }
}

const EXPORTABLE_COMMANDS = new Set(['recent', 'search', 'by-platform', 'by-user', 'by-tag']);

function findSourcePost(posts, result) {
  const bySequence = posts.find((post) =>
    post.sequence_id != null &&
    result.sequence_id != null &&
    String(post.sequence_id) === String(result.sequence_id)
  );
  if (bySequence) return bySequence;

  return posts.find((post) =>
    normalizePlatformName(post.sns_platform) === result.sns_platform &&
    String(post.platform_id || post.code) === String(result.platform_id || result.code)
  );
}

function cmdExport(context, options) {
  const [exportCommand, ...exportPositionals] = options.positional;
  if (!exportCommand) {
    fail('export requires a command');
  }
  if (!EXPORTABLE_COMMANDS.has(exportCommand)) {
    fail(`export supports: ${[...EXPORTABLE_COMMANDS].join(', ')}`);
  }

  const innerOptions = {
    ...options,
    command: exportCommand,
    positional: exportPositionals,
    format: 'json',
  };
  const payload = buildPayload({ ...context, options: innerOptions });
  const exportPosts = payload.posts.map((result) => {
    const source = findSourcePost(context.posts, result);
    return source
      ? postToExportResult(source, result.tags || [], {
          note: getUserNoteForPost(source, context.userMetadata),
          match_fields: result.match_fields || [],
        })
      : result;
  });

  const exportPayload = {
    ...payload,
    posts: exportPosts,
  };

  const format = options.format === 'md' ? 'md' : 'json';
  const outputPath = resolveExportPath(options, exportCommand, exportPositionals.join('_'), format);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });

  const dataFile = path.relative(PROJECT_ROOT, context.file).replace(/\\/g, '/');
  const tagsFile = fs.existsSync(TAGS_PATH) ? path.relative(PROJECT_ROOT, TAGS_PATH).replace(/\\/g, '/') : null;
  const invocation = process.argv.slice(2).join(' ');
  const generatedAt = formatKstTimestamp();

  const fileContent = format === 'json'
    ? `${JSON.stringify(exportPayload, null, 2)}\n`
    : renderMarkdownExport(exportPayload, { generatedAt, invocation, dataFile, tagsFile });
  fs.writeFileSync(outputPath, fileContent, 'utf8');

  return {
    command: 'export',
    source_command: exportCommand,
    total_matches: exportPayload.total_matches,
    returned: exportPayload.returned,
    export: {
      format,
      output_path: path.relative(PROJECT_ROOT, outputPath).replace(/\\/g, '/'),
    },
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
    const userMetadata = loadUserMetadata();
    const context = { data, posts, file, tagsMap, userMetadata };

    const payload = options.command === 'export'
      ? cmdExport(context, options)
      : buildPayload({ ...context, options });

    printPayload(payload, options.command === 'export' ? { ...options, format: 'json' } : options);
  } catch (error) {
    process.stderr.write(`Error: ${error.message}\n`);
    process.exit(1);
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  main();
}

export {
  normalizeSearchText,
  splitSearchTerms,
  matchesSearchText,
};
