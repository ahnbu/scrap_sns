import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude',
  'skills',
  '_shared',
  'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

async function main() {
  const browser = await launchHeadlessChromium();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const scriptUrls = new Set();
  let searchRequestCount = 0;
  const consistencyPost = {
    sequence_id: 999001,
    platform_id: 'li-consistency-20260504',
    sns_platform: 'linkedin',
    url: 'https://www.linkedin.com/feed/update/urn:li:activity:li-consistency-20260504',
    canonical_url: 'https://www.linkedin.com/feed/update/urn:li:activity:li-consistency-20260504',
    display_name: 'Consistency Tester',
    username: 'consistency-tester',
    created_at: '2026-05-04T09:00:00+09:00',
    crawled_at: '2026-05-04T09:05:00+09:00',
    full_text_preview: 'Unique Harness consistency probe'
  };

  try {
    page.on('request', request => {
      const url = request.url();
      if (url.includes('web_viewer/script.js')) {
        scriptUrls.add(url);
      }
    });

    await page.route('**/api/run-scrap', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          message: 'mock partial success with auth required',
          auth_required: ['x', 'threads'],
          platform_results: {
            threads: { status: 'auth_required' },
            linkedin: { status: 'ok' },
            x: { status: 'auth_required' }
          },
          stats: {
            total: 7,
            threads: 0,
            linkedin: 7,
            twitter: 0,
            total_count: 1,
            threads_count: 520,
            linkedin_count: 410,
            twitter_count: 318
          },
          consistency_probe: {
            source_file: 'output_total/sns_total_latest.json',
            updated_at: '2026-05-04T09:05:00+09:00',
            total_count: 1,
            platform_counts: {
              threads: 0,
              linkedin: 1,
              twitter: 0
            },
            new_counts: {
              threads: 0,
              linkedin: 1,
              twitter: 0
            },
            new_samples: {
              threads: [],
              linkedin: [{
                sequence_id: consistencyPost.sequence_id,
                platform_id: consistencyPost.platform_id,
                sns_platform: consistencyPost.sns_platform,
                url: consistencyPost.url,
                display_name: consistencyPost.display_name
              }],
              twitter: []
            }
          }
        })
      });
    });
    await page.route('**/api/status', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' })
      });
    });
    await page.route('**/api/posts?**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ posts: [consistencyPost] })
      });
    });
    await page.route('**/api/search?**', async route => {
      searchRequestCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ posts: [consistencyPost] })
      });
    });
    await page.route('**/api/get-tags', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({})
      });
    });

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

    const modalText = await page.locator('#scrapResultModal').innerText();
    await page.waitForTimeout(2200);
    const stillOpenAfterDelay = await page
      .locator('#scrapResultModal')
      .evaluate(el => el.classList.contains('show'));
    const authPanelVisible = await page
      .locator('#authRequiredPanel')
      .evaluate(el => !el.classList.contains('hidden'));
    const promptCopyVisible = await page.locator('#copyAuthRenewalPromptBtn').isVisible();

    await page.locator('#confirmScrapResultModal').click();
    await page.waitForFunction(
      () => document.querySelector('#scrapResultModal')?.classList.contains('hidden'),
      null,
      { timeout: 5000 }
    );

    const result = {
      ok: true,
      hasTitle: modalText.includes('업데이트 완료'),
      hasTotalLine: modalText.includes('총 7건 신규 추가'),
      hasLinkedInStats: modalText.includes('LinkedIn') && modalText.includes('7건 추가'),
      hasAuthNotice: modalText.includes('인증 갱신 필요'),
      hasAuthPlatforms: modalText.includes('X, Threads'),
      blocksAutomatedLogin: modalText.includes('자동화 브라우저로 감지'),
      hasPrompt: modalText.includes('README.md의 인증 갱신 섹션'),
      hasNoConsistencySection: !modalText.includes('정합성 확인'),
      hasNoSearchProbe: searchRequestCount === 0,
      promptCopyVisible,
      stillOpenAfterDelay,
      authPanelHidden: !authPanelVisible,
      hiddenAfterClose: await page
        .locator('#scrapResultModal')
        .evaluate(el => el.classList.contains('hidden')),
      restoredRunText: await page.locator('#runScrapBtn').innerText(),
      scriptUrls: Array.from(scriptUrls)
    };

    const failed = Object.entries({
      hasTitle: result.hasTitle,
      hasTotalLine: result.hasTotalLine,
      hasLinkedInStats: result.hasLinkedInStats,
      hasAuthNotice: result.hasAuthNotice,
      hasAuthPlatforms: result.hasAuthPlatforms,
      blocksAutomatedLogin: result.blocksAutomatedLogin,
      hasPrompt: result.hasPrompt,
      hasNoConsistencySection: result.hasNoConsistencySection,
      hasNoSearchProbe: result.hasNoSearchProbe,
      promptCopyVisible: result.promptCopyVisible,
      stillOpenAfterDelay: result.stillOpenAfterDelay,
      authPanelHidden: result.authPanelHidden,
      hiddenAfterClose: result.hiddenAfterClose,
      scriptVersionLoaded: result.scriptUrls.some(url => url.includes('v=20260504-scrap-result-modal'))
    }).filter(([, passed]) => !passed);

    if (failed.length > 0) {
      result.ok = false;
      result.failed = failed.map(([name]) => name);
      console.error(JSON.stringify(result, null, 2));
      process.exitCode = 1;
      return;
    }

    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
