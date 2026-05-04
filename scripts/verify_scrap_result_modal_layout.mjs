import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const CAPTURE_DIR = path.join(process.cwd(), 'test_runs', 'scrap-result-modal-layout');
const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude',
  'skills',
  '_shared',
  'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

const VIEWPORTS = [
  { width: 1024, height: 768 },
  { width: 1280, height: 900 }
];

const MIN_OUTER_GAP = 24;
const MIN_HEADER_TOP_PADDING = 24;

function buildRunScrapPayload(authRequired) {
  return {
    status: 'success',
    message: authRequired ? 'mock success with auth required' : 'mock success',
    auth_required: authRequired ? ['x'] : [],
    platform_results: authRequired ? { x: { status: 'auth_required' } } : {},
    stats: {
      total: authRequired ? 1 : 3,
      threads: authRequired ? 0 : 1,
      linkedin: authRequired ? 1 : 2,
      twitter: 0,
      total_count: 1223,
      threads_count: 844,
      linkedin_count: 313,
      twitter_count: 82
    },
    consistency_probe: {
      source_file: 'output_total/sns_total_latest.json',
      total_count: 1223,
      new_counts: { threads: 0, linkedin: 0, twitter: 0 },
      new_samples: { threads: [], linkedin: [], twitter: [] }
    }
  };
}

async function mockApi(page, authRequired) {
  await page.route('**/api/status', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'ok' })
  }));
  await page.route('**/api/get-tags', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({})
  }));
  await page.route('**/api/posts?**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ posts: [] })
  }));
  await page.route('**/api/run-scrap', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(buildRunScrapPayload(authRequired))
  }));
}

async function openScrapResultModal(page) {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    window.confirm = () => true;
  });
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
  await page.locator('#runScrapBtn').click();
  await page.locator('#scrapResultModal.show').waitFor({ timeout: 5000 });
  await page.waitForFunction(
    () => !document.querySelector('#runScrapBtn')?.disabled,
    null,
    { timeout: 5000 }
  );
}

async function measureLayout(page) {
  return page.locator('#scrapResultModal > div').evaluate(panel => {
    const header = panel.querySelector('header');
    const body = panel.querySelector('#scrapResultBody');
    const footer = panel.querySelector('footer');
    const panelRect = panel.getBoundingClientRect();
    const footerRect = footer.getBoundingClientRect();
    const headerStyle = getComputedStyle(header);
    return {
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight
      },
      panel: {
        top: Math.round(panelRect.top),
        bottom: Math.round(window.innerHeight - panelRect.bottom),
        height: Math.round(panelRect.height)
      },
      headerPaddingTop: Math.round(parseFloat(headerStyle.paddingTop)),
      footerVisible:
        footerRect.top >= 0 &&
        footerRect.bottom <= window.innerHeight &&
        footerRect.height > 0,
      bodyHasScroll: body.scrollHeight > body.clientHeight + 1,
      bodyClientHeight: Math.round(body.clientHeight),
      bodyScrollHeight: Math.round(body.scrollHeight)
    };
  });
}

function checkLayout(metrics, mode) {
  const failed = [];
  if (metrics.panel.top < MIN_OUTER_GAP) {
    failed.push(`top gap ${metrics.panel.top}px < ${MIN_OUTER_GAP}px`);
  }
  if (metrics.panel.bottom < MIN_OUTER_GAP) {
    failed.push(`bottom gap ${metrics.panel.bottom}px < ${MIN_OUTER_GAP}px`);
  }
  if (metrics.headerPaddingTop < MIN_HEADER_TOP_PADDING) {
    failed.push(`header top padding ${metrics.headerPaddingTop}px < ${MIN_HEADER_TOP_PADDING}px`);
  }
  if (!metrics.footerVisible) {
    failed.push('footer is not fully visible');
  }
  if (mode === 'normal' && metrics.bodyHasScroll) {
    failed.push('normal modal should not create body scroll');
  }
  return failed;
}

async function runScenario(browser, viewport, mode) {
  const authRequired = mode === 'auth';
  const page = await browser.newPage({ viewport });
  await mockApi(page, authRequired);
  await openScrapResultModal(page);
  const metrics = await measureLayout(page);
  const failed = checkLayout(metrics, mode);
  const screenshotPath = path.join(
    CAPTURE_DIR,
    `scrap-result-modal-${mode}-${viewport.width}x${viewport.height}.png`
  );
  await page.screenshot({ path: screenshotPath, fullPage: false });
  await page.close();
  return {
    mode,
    screenshotPath,
    ...metrics,
    ok: failed.length === 0,
    failed
  };
}

async function main() {
  await mkdir(CAPTURE_DIR, { recursive: true });
  const browser = await launchHeadlessChromium();
  const results = [];
  try {
    for (const viewport of VIEWPORTS) {
      results.push(await runScenario(browser, viewport, 'normal'));
      results.push(await runScenario(browser, viewport, 'auth'));
    }
  } finally {
    await browser.close();
  }

  const failed = results.filter(result => !result.ok);
  const output = {
    ok: failed.length === 0,
    minOuterGap: MIN_OUTER_GAP,
    minHeaderTopPadding: MIN_HEADER_TOP_PADDING,
    captureDir: CAPTURE_DIR,
    results
  };
  const serialized = JSON.stringify(output, null, 2);
  if (failed.length > 0) {
    console.error(serialized);
    process.exitCode = 1;
    return;
  }
  console.log(serialized);
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
