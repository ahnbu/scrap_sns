#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

function parseArgs(argv) {
  const args = { session: "linkedin_saved_shadow", url: "https://www.linkedin.com/my-items/saved-posts/" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) continue;
    const key = arg.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function timestamp() {
  const formatted = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(new Date());
  return formatted.replace(/[-: ]/g, "");
}

function runOpenCli(args, { expectJson = false } = {}) {
  const command = process.platform === "win32" ? "node" : "opencli";
  const commandArgs = process.platform === "win32"
    ? [openCliMainPath(), ...args]
    : args;
  const result = spawnSync(command, commandArgs, {
    encoding: "utf8",
    maxBuffer: 1024 * 1024 * 50,
    shell: false,
  });
  if (result.status !== 0) {
    throw new Error(`opencli ${args.join(" ")} failed: ${result.error?.message || result.stderr || result.stdout}`);
  }
  const stdout = result.stdout.replace(/^\uFEFF/, "").trim();
  return expectJson ? JSON.parse(stdout) : stdout;
}

function openCliMainPath() {
  const appData = process.env.APPDATA;
  if (!appData) return "opencli";
  return `${appData.replace(/\\/g, "/")}/npm/node_modules/@jackwener/opencli/dist/src/main.js`;
}

function browser(session, commandArgs, options = {}) {
  return runOpenCli(["browser", session, ...commandArgs], options);
}

function closeBrowserSession(session) {
  browser(session, ["unbind"]);
  browser(session, ["close"]);
}

function sleep(seconds) {
  browser("_noop", ["wait", "time", String(seconds)]).catch?.(() => {});
}

function wait(session, seconds) {
  browser(session, ["wait", "time", String(seconds)]);
}

function getNetworkEntries(session, since = "30s") {
  return browser(
    session,
    ["network", "--since", since, "--filter", "searchDashClustersByAll"],
    { expectJson: true },
  ).entries || [];
}

function getDetail(session, key) {
  return browser(session, ["network", "--detail", key], { expectJson: true });
}

function fetchGraphqlPage(session, start, paginationToken) {
  const script = `
(async () => {
  const token = ${JSON.stringify(paginationToken)};
  const start = ${Number(start)};
  const csrf = (document.cookie.match(/JSESSIONID="?([^";]+)/) || [])[1] || "";
  const variables = token
    ? \`(start:\${start},paginationToken:\${encodeURIComponent(token)},query:(flagshipSearchIntent:SEARCH_MY_ITEMS_SAVED_POSTS))\`
    : \`(start:\${start},query:(flagshipSearchIntent:SEARCH_MY_ITEMS_SAVED_POSTS))\`;
  const url = \`/voyager/api/graphql?variables=\${variables}&queryId=voyagerSearchDashClusters.a7a0567fa66c52d645b5ff2f960b92aa\`;
  const response = await fetch(url, {
    credentials: "include",
    headers: {
      accept: "application/vnd.linkedin.normalized+json+2.1",
      "csrf-token": csrf
    }
  });
  const text = await response.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    return { status: response.status, url, size: text.length, body: null, text: text.slice(0, 200) };
  }
  return { status: response.status, url, size: text.length, body };
})()
`;
  const fetched = browser(session, ["eval", script], { expectJson: true });
  if (fetched.status !== 200 || !fetched.body) {
    throw new Error(`GraphQL fetch failed: status=${fetched.status} text=${fetched.text || ""}`);
  }
  return {
    key: `FETCH www.linkedin.com/voyager/api/graphql#${start}`,
    url: `https://www.linkedin.com${fetched.url}`,
    method: "GET",
    status: fetched.status,
    ct: "application/vnd.linkedin.normalized+json+2.1",
    size: fetched.size,
    timestamp: new Date().toISOString(),
    body: fetched.body,
  };
}

function extractCluster(detail) {
  return detail?.body?.data?.data?.searchDashClustersByAll || {};
}

function extractItems(detail) {
  return Array.isArray(detail?.body?.included)
    ? detail.body.included.filter((item) => item?.$type === "com.linkedin.voyager.dash.search.EntityResultViewModel")
    : [];
}

function activityIdsFromDetail(detail) {
  return extractItems(detail)
    .map((item) => String(item.entityUrn || "").match(/activity:(\d+)/)?.[1])
    .filter(Boolean);
}

function latestGraphqlEntry(entries, seenUrls) {
  const candidates = entries.filter((entry) => String(entry.url || "").includes("SEARCH_MY_ITEMS_SAVED_POSTS"));
  for (let i = candidates.length - 1; i >= 0; i -= 1) {
    if (!seenUrls.has(candidates[i].url)) return candidates[i];
  }
  return null;
}

function clickLoadMore(session) {
  const clicked = browser(session, ["click", "--text", "결과 더보기"], { expectJson: true });
  return Boolean(clicked.clicked);
}

function scrollDown(session) {
  browser(session, ["scroll", "down", "--amount", "1800"]);
}

function pageState(session) {
  return browser(session, ["state"]);
}

function writeRaw(outDir, stamp, pageIndex, detail) {
  mkdirSync(outDir, { recursive: true });
  const padded = String(pageIndex).padStart(3, "0");
  const path = join(outDir, `linkedin_opencli_raw_${stamp}_page${padded}.json`);
  writeFileSync(path, `${JSON.stringify(detail, null, 2)}\n`, "utf8");
  return path;
}

function readRaw(rawPath) {
  return readFileSync(rawPath, "utf8").replace(/^\uFEFF/, "");
}

let activeSession = "";

function main() {
  const args = parseArgs(process.argv.slice(2));
  const session = args.session;
  activeSession = session;
  const url = args.url;
  const outDir = args.out || "output_linkedin/opencli_shadow/raw";
  const stamp = timestamp();
  const dryRun = Boolean(args["dry-run"]);
  const maxPages = Number(args["max-pages"] || 200);
  const useBoundSession = Boolean(args["use-bound-session"]);

  if (!useBoundSession) {
    browser(session, ["open", url, "--window", "background"], { expectJson: true });
    wait(session, 5);
  }

  const state = pageState(session);
  if (!state.includes("저장한 게시물") && !state.includes("Saved")) {
    throw new Error("LinkedIn saved posts page was not confirmed");
  }

  const seenUrls = new Set();
  const seenIds = new Set();
  const seenTokens = new Set();
  const pages = [];
  let noNewIdsAttempts = 0;
  let endReason = "max_pages";

  for (let pageIndex = 1; pageIndex <= maxPages; pageIndex += 1) {
    const entry = latestGraphqlEntry(getNetworkEntries(session, pageIndex === 1 ? "2m" : "45s"), seenUrls);
    if (!entry) {
      if (pageIndex === 1) {
        const fetchedDetail = fetchGraphqlPage(session, 0, "");
        seenUrls.add(fetchedDetail.url);
        const fetchedCluster = extractCluster(fetchedDetail);
        const fetchedIds = activityIdsFromDetail(fetchedDetail);
        const before = seenIds.size;
        fetchedIds.forEach((id) => seenIds.add(id));
        const newIds = seenIds.size - before;
        noNewIdsAttempts = newIds > 0 ? 0 : noNewIdsAttempts + 1;
        const token = fetchedCluster?.metadata?.paginationToken || "";
        const rawPath = dryRun ? "" : writeRaw(outDir, stamp, pageIndex, fetchedDetail);
        pages.push({
          page: pageIndex,
          key: fetchedDetail.key,
          raw_path: rawPath,
          url: fetchedDetail.url,
          start: fetchedCluster?.paging?.start ?? null,
          count: fetchedCluster?.paging?.count ?? null,
          total: fetchedCluster?.paging?.total ?? null,
          metadata_total: fetchedCluster?.metadata?.totalResultCount ?? null,
          pagination_token_present: Boolean(token),
          unique_activity_ids_in_page: new Set(fetchedIds).size,
          new_activity_ids: newIds,
          response_size: fetchedDetail.size,
        });
        if (token) {
          seenTokens.add(token);
        }
      } else {
        noNewIdsAttempts += 1;
      }
    } else {
      seenUrls.add(entry.url);
      const detail = getDetail(session, entry.key);
      const cluster = extractCluster(detail);
      const token = cluster?.metadata?.paginationToken || "";
      const ids = activityIdsFromDetail(detail);
      const before = seenIds.size;
      ids.forEach((id) => seenIds.add(id));
      const newIds = seenIds.size - before;
      noNewIdsAttempts = newIds > 0 ? 0 : noNewIdsAttempts + 1;

      const rawPath = dryRun ? "" : writeRaw(outDir, stamp, pageIndex, detail);
      pages.push({
        page: pageIndex,
        key: entry.key,
        raw_path: rawPath,
        url: entry.url,
        start: cluster?.paging?.start ?? null,
        count: cluster?.paging?.count ?? null,
        total: cluster?.paging?.total ?? null,
        metadata_total: cluster?.metadata?.totalResultCount ?? null,
        pagination_token_present: Boolean(token),
        unique_activity_ids_in_page: new Set(ids).size,
        new_activity_ids: newIds,
        response_size: entry.size,
      });

      if (token) {
        if (seenTokens.has(token)) {
          endReason = "repeated_pagination_token";
          break;
        }
        seenTokens.add(token);
      }

      if (dryRun) {
        endReason = "dry_run";
        break;
      }
    }

    if (noNewIdsAttempts >= 3) {
      endReason = "no_new_ids_after_3_attempts";
      break;
    }

    const lastPage = pages[pages.length - 1];
    const lastDetail = lastPage ? JSON.parse(readRaw(lastPage.raw_path, lastPage, dryRun)) : null;
    const lastCluster = lastDetail ? extractCluster(lastDetail) : null;
    const lastToken = lastCluster?.metadata?.paginationToken || "";
    if (!lastToken) {
      endReason = "load_button_absent";
      break;
    }
    const nextStart = (lastCluster?.paging?.start || 0) + (lastPage?.unique_activity_ids_in_page || 0);
    try {
      const fetchedDetail = fetchGraphqlPage(session, nextStart, lastToken);
      seenUrls.add(fetchedDetail.url);
      const fetchedCluster = extractCluster(fetchedDetail);
      const fetchedIds = activityIdsFromDetail(fetchedDetail);
      const before = seenIds.size;
      fetchedIds.forEach((id) => seenIds.add(id));
      const newIds = seenIds.size - before;
      noNewIdsAttempts = newIds > 0 ? 0 : noNewIdsAttempts + 1;
      const token = fetchedCluster?.metadata?.paginationToken || "";
      const rawPath = dryRun ? "" : writeRaw(outDir, stamp, pageIndex + 1, fetchedDetail);
      pages.push({
        page: pageIndex + 1,
        key: fetchedDetail.key,
        raw_path: rawPath,
        url: fetchedDetail.url,
        start: fetchedCluster?.paging?.start ?? null,
        count: fetchedCluster?.paging?.count ?? null,
        total: fetchedCluster?.paging?.total ?? null,
        metadata_total: fetchedCluster?.metadata?.totalResultCount ?? null,
        pagination_token_present: Boolean(token),
        unique_activity_ids_in_page: new Set(fetchedIds).size,
        new_activity_ids: newIds,
        response_size: fetchedDetail.size,
      });
      if (!token) {
        endReason = "load_button_absent";
        break;
      }
      if (seenTokens.has(token)) {
        endReason = "repeated_pagination_token";
        break;
      }
      seenTokens.add(token);
    } catch {
      let clicked = false;
      try {
        clicked = clickLoadMore(session);
      } catch {
        clicked = false;
      }
      if (!clicked) {
        scrollDown(session);
        wait(session, 3);
        try {
          clicked = clickLoadMore(session);
        } catch {
          clicked = false;
        }
      }
      if (!clicked) {
        endReason = "load_button_absent";
        break;
      }
      wait(session, 4);
    }
  }

  const summary = {
    generated_at: new Date().toISOString(),
    session,
    url,
    dry_run: dryRun,
    end_reason: endReason,
    pages_collected: pages.length,
    total_unique_activity_ids: seenIds.size,
    pages,
  };

  if (!dryRun) {
    mkdirSync(join(outDir, ".."), { recursive: true });
    writeFileSync(
      join(outDir, "..", `session_${stamp}.json`),
      `${JSON.stringify(summary, null, 2)}\n`,
      "utf8",
    );
  }
  console.log(JSON.stringify(summary, null, 2));
}

try {
  main();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  if (activeSession) {
    try {
      closeBrowserSession(activeSession);
    } catch (error) {
      console.error(`OpenCLI browser cleanup failed: ${error.message}`);
    }
  }
}
