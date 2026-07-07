#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptPath = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(scriptPath), "..");

export const TARGETS = [
  {
    id: "linkedin_full",
    label: "LinkedIn full",
    dir: "output_linkedin/python",
    regex: /^linkedin_py_full_(\d{8})\.json$/,
  },
  {
    id: "threads_full",
    label: "Threads full",
    dir: "output_threads/python",
    regex: /^threads_py_full_(\d{8})\.json$/,
  },
  {
    id: "threads_simple",
    label: "Threads simple",
    dir: "output_threads/python",
    regex: /^threads_py_simple_(\d{8})\.json$/,
  },
  {
    id: "twitter_full",
    label: "X full",
    dir: "output_twitter/python",
    regex: /^twitter_py_full_(\d{8})\.json$/,
  },
  {
    id: "twitter_simple",
    label: "X simple",
    dir: "output_twitter/python",
    regex: /^twitter_py_simple_(\d{8})\.json$/,
  },
  {
    id: "total_full",
    label: "Total full",
    dir: "output_total",
    regex: /^total_full_(\d{8})\.json$/,
  },
];

function usage() {
  return `Usage: node scripts/cleanup_old_output_json.mjs [options]

Options:
  --dry-run          Print cleanup candidates without moving files. Default.
  --apply            Move cleanup candidates to trash with safe-trash.
  --root <path>      Repository root. Default: current script repository.
  --today YYYYMMDD   KST date used for retention decisions. Default: today.
  --keep-days N      Keep all files from the recent N days. Default: 30.
  --keep-latest N    Keep the latest N files per target. Default: 5.
  --json             Print JSON summary.
  --help             Print this help.
`;
}

function requireValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} requires a value.`);
  }
  return value;
}

function parsePositiveInteger(value, flag) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${flag} must be a non-negative integer.`);
  }
  return parsed;
}

export function parseArgs(argv) {
  const options = {
    mode: "dry-run",
    root: repoRoot,
    todayYmd: null,
    keepDays: 30,
    keepLatest: 5,
    json: false,
    help: false,
  };
  let explicitDryRun = false;
  let explicitApply = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--dry-run") {
      explicitDryRun = true;
      options.mode = "dry-run";
    } else if (arg === "--apply") {
      explicitApply = true;
      options.mode = "apply";
    } else if (arg === "--root") {
      options.root = path.resolve(requireValue(argv, index, arg));
      index += 1;
    } else if (arg === "--today") {
      options.todayYmd = requireValue(argv, index, arg);
      if (!/^\d{8}$/.test(options.todayYmd)) {
        throw new Error("--today must use YYYYMMDD.");
      }
      index += 1;
    } else if (arg === "--keep-days") {
      options.keepDays = parsePositiveInteger(requireValue(argv, index, arg), arg);
      index += 1;
    } else if (arg === "--keep-latest") {
      options.keepLatest = parsePositiveInteger(requireValue(argv, index, arg), arg);
      index += 1;
    } else if (arg === "--json") {
      options.json = true;
    } else if (arg === "--help") {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (explicitDryRun && explicitApply) {
    throw new Error("Choose only one of --dry-run or --apply.");
  }

  if (!options.todayYmd) {
    options.todayYmd = getKstTodayYmd();
  }

  return options;
}

export function getKstTodayYmd(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}${values.month}${values.day}`;
}

function ymdToUtcDay(ymd) {
  const year = Number(ymd.slice(0, 4));
  const month = Number(ymd.slice(4, 6));
  const day = Number(ymd.slice(6, 8));
  return Date.UTC(year, month - 1, day) / 86400000;
}

export async function listTargetFiles(root, target) {
  const dirPath = path.join(root, target.dir);
  let entries = [];
  try {
    entries = await readdir(dirPath, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }

  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => {
      const match = target.regex.exec(entry.name);
      if (!match) return null;
      return {
        path: path.join(dirPath, entry.name),
        relativePath: path.join(target.dir, entry.name).replace(/\\/g, "/"),
        name: entry.name,
        ymd: match[1],
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.ymd.localeCompare(b.ymd) || a.name.localeCompare(b.name));
}

export async function planCleanup({
  root = repoRoot,
  todayYmd = getKstTodayYmd(),
  keepDays = 30,
  keepLatest = 5,
  targets = TARGETS,
} = {}) {
  const groups = [];
  const todayDay = ymdToUtcDay(todayYmd);

  for (const target of targets) {
    const files = await listTargetFiles(root, target);
    const keepPaths = new Set();

    for (const file of files) {
      if (file.ymd === todayYmd) keepPaths.add(file.path);
      if (todayDay - ymdToUtcDay(file.ymd) <= keepDays) keepPaths.add(file.path);
    }

    for (const file of [...files].sort((a, b) => b.ymd.localeCompare(a.ymd)).slice(0, keepLatest)) {
      keepPaths.add(file.path);
    }

    const monthlyLatest = new Map();
    for (const file of files) {
      if (file.ymd === todayYmd) continue;
      if (todayDay - ymdToUtcDay(file.ymd) <= keepDays) continue;
      const month = file.ymd.slice(0, 6);
      const current = monthlyLatest.get(month);
      if (!current || file.ymd > current.ymd) monthlyLatest.set(month, file);
    }
    for (const file of monthlyLatest.values()) keepPaths.add(file.path);

    const keep = files.filter((file) => keepPaths.has(file.path));
    const deleteItems = files.filter((file) => !keepPaths.has(file.path));
    groups.push({ target, files, keep, delete: deleteItems });
  }

  return {
    todayYmd,
    keepDays,
    keepLatest,
    groups,
    delete: groups.flatMap((group) => group.delete),
    keep: groups.flatMap((group) => group.keep),
  };
}

function resolveSafeTrashCommand() {
  const where = spawnSync("where.exe", ["safe-trash"], { encoding: "utf8" });
  if (where.status !== 0) return null;
  return where.stdout.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || null;
}

export function runSafeTrash(paths) {
  if (paths.length === 0) return;

  const command = resolveSafeTrashCommand();
  if (!command) {
    throw new Error("safe-trash command was not found on PATH.");
  }

  for (const targetPath of paths) {
    const result = spawnSync(
      "powershell",
      ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", command, targetPath],
      { stdio: "inherit" },
    );
    if (result.status !== 0) {
      throw new Error(`safe-trash failed for ${targetPath}`);
    }
  }
}

function buildSummary(plan, mode) {
  return {
    mode,
    todayYmd: plan.todayYmd,
    keepDays: plan.keepDays,
    keepLatest: plan.keepLatest,
    deleteCount: plan.delete.length,
    keepCount: plan.keep.length,
    groups: plan.groups.map((group) => ({
      id: group.target.id,
      label: group.target.label,
      fileCount: group.files.length,
      keepCount: group.keep.length,
      deleteCount: group.delete.length,
    })),
  };
}

function formatHuman(plan, mode, trashedCount = null) {
  const lines = [
    `Mode: ${mode}`,
    `Today(KST): ${plan.todayYmd}`,
    `Policy: keep latest ${plan.keepLatest}, keep recent ${plan.keepDays} days, keep monthly latest before that`,
  ];

  for (const group of plan.groups) {
    lines.push(
      `[${group.target.label}] files=${group.files.length} keep=${group.keep.length} cleanup=${group.delete.length}`,
    );
    for (const item of group.delete) {
      lines.push(`  cleanup ${item.relativePath}`);
    }
  }

  lines.push(`Summary: cleanup candidates ${plan.delete.length}, kept ${plan.keep.length}`);
  if (trashedCount !== null) {
    lines.push(`Moved to trash: ${trashedCount} files`);
  }
  return `${lines.join("\n")}\n`;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }

  const plan = await planCleanup({
    root: options.root,
    todayYmd: options.todayYmd,
    keepDays: options.keepDays,
    keepLatest: options.keepLatest,
  });

  let trashedCount = null;
  if (options.mode === "apply") {
    runSafeTrash(plan.delete.map((item) => item.path));
    trashedCount = plan.delete.length;
  }

  if (options.json) {
    process.stdout.write(`${JSON.stringify(buildSummary(plan, options.mode), null, 2)}\n`);
  } else {
    process.stdout.write(formatHuman(plan, options.mode, trashedCount));
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
