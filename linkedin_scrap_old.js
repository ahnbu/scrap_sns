import { chromium } from 'playwright-core';
import { startPlayWriterCDPRelayServer, getCdpUrl } from 'playwriter';
import fs from 'fs';

const OUTPUT_DIR = 'output_linkedin/js';

// ===========================
// File Management Logic
// ===========================

function findLatestFullFile() {
  if (!fs.existsSync(OUTPUT_DIR)) return null;
  const files = fs.readdirSync(OUTPUT_DIR)
    .filter(f => f.startsWith('linkedin_js_full_') && f.endsWith('.json'))
    .sort((a, b) => {
      const dateA = a.match(/_full_(\d{8})/)?.[1] || "";
      const dateB = b.match(/_full_(\d{8})/)?.[1] || "";
      if (dateA !== dateB) return dateB.localeCompare(dateA);
      return fs.statSync(`${OUTPUT_DIR}/${b}`).mtime.getTime() - fs.statSync(`${OUTPUT_DIR}/${a}`).mtime.getTime();
    });
  return files.length > 0 ? `${OUTPUT_DIR}/${files[0]}` : null;
}

function updateFullVersion(newData, stopCode, crawlStartTime) {
  const today = new Date().toISOString().split('T')[0].replace(/-/g, '');
  const todayFull = `${OUTPUT_DIR}/linkedin_js_full_${today}.json`;
  
  let latestFull = fs.existsSync(todayFull) ? todayFull : findLatestFullFile();
  let existingPosts = [];
  let existingMergeHistory = [];
  let sourceFilename = null;

  if (latestFull) {
    console.log(`📂 기존 Full 파일 로드: ${latestFull}`);
    sourceFilename = latestFull.split('/').pop();
    const content = JSON.parse(fs.readFileSync(latestFull, 'utf8'));
    if (content.posts) {
      existingPosts = content.posts;
      existingMergeHistory = content.metadata?.merge_history || [];
    } else {
      existingPosts = content; 
    }

    const existingCodes = new Set(existingPosts.map(p => p.code));
    const maxExistingSeq = Math.max(0, ...existingPosts.map(p => p.sequence_id || 0));
    
    const newItems = newData.filter(p => !existingCodes.has(p.code));
    const duplicateCount = newData.length - newItems.length;

    newItems.forEach((p, i) => {
      p.sequence_id = maxExistingSeq + newItems.length - i;
      p.crawled_at = crawlStartTime;
    });

    const mergedPosts = [...newItems, ...existingPosts];
    const mergeHistory = [...existingMergeHistory];
    
    if (newItems.length > 0) {
      mergeHistory.push({
        merged_at: new Date().toISOString(),
        new_items_count: newItems.length,
        duplicates_removed: duplicateCount,
        source_file: sourceFilename,
        stop_code: stopCode
      });
    }

    saveFullFile(todayFull, mergedPosts, mergeHistory, crawlStartTime, "update only");
    console.log(`✅ 병합 완료: ${newItems.length}개 신규 추가 + ${existingPosts.length}개 기존 = ${mergedPosts.length}개`);
  } else {
    // 최초 Full 생성
    console.log("⚠️ 기존 Full 파일 없음 - 현재 결과를 Full로 저장");
    newData.forEach((p, i) => {
      p.sequence_id = newData.length - i;
      p.crawled_at = crawlStartTime;
    });
    saveFullFile(todayFull, newData, [], crawlStartTime, "all");
  }
}

function saveFullFile(path, posts, history, startTime, mode) {
  const now = new Date().toISOString();
  const maxSeq = Math.max(0, ...posts.map(p => p.sequence_id || 0));
  const legacyCount = posts.filter(p => !p.crawled_at).length;
  const verifiedCount = posts.length - legacyCount;

  const metadata = {
    version: "1.0",
    crawled_at: now,
    total_count: posts.length,
    max_sequence_id: maxSeq,
    first_code: posts[0]?.code || null,
    last_code: posts[posts.length - 1]?.code || null,
    crawl_mode: mode,
    legacy_data_count: legacyCount,
    verified_data_count: verifiedCount,
    merge_history: history
  };

  fs.writeFileSync(path, JSON.stringify({ metadata, posts }, null, 2));
  console.log(`📦 Full 버전 저장됨: ${path}`);
}

// ===========================
// Main Crawler Logic
// ===========================

async function main() {
  const startTimestamp = new Date();
  // Settings
  const TARGET_LIMIT = 30; // Reduced for debugging
  // const CRAWL_MODE = "update only";  // all, update only
  const CRAWL_MODE = "all";  // all, update only
  const MAX_NO_NEW_ITEMS = 5; // 스크롤 최대 시도 횟수

  const crawlStartTime = new Date().toISOString();
  console.log('🚀 Relay 서버 시작 중...');
  const server = await startPlayWriterCDPRelayServer();
  
  try {
    let browser;
    let retries = 20;
    
    console.log('🌐 브라우저 연결 시도 중 (CDP)...');
    
    while (retries > 0) {
      try {
        browser = await chromium.connectOverCDP(getCdpUrl());
        console.log('✅ Playwriter 확장 프로그램 연결 성공!');
        break;
      } catch (e) {
        if (e.message.includes('Extension not connected') || e.message.includes('ECONNREFUSED')) {
            console.log(`⏳ 확장 프로그램 연결 대기 중... (${retries}). 링크드인 페이지를 열거나 Playwriter 아이콘을 확인하세요.`);
            await new Promise(r => setTimeout(r, 2000));
            retries--;
        } else {
            throw e;
        }
      }
    }

    if (!browser) {
        throw new Error('Failed to connect to browser extension.');
    }

    // --- Incremental Load Strategy ---
    let stopCodes = new Set();
    if (CRAWL_MODE === "update only") {
        if (!fs.existsSync(OUTPUT_DIR)) {
            fs.mkdirSync(OUTPUT_DIR, { recursive: true });
        }
        const latestFull = findLatestFullFile();
        if (latestFull) {
            console.log(`🔄 UPDATE ONLY 모드: 최신 Full 파일 로드 - ${latestFull}`);
            try {
                const content = JSON.parse(fs.readFileSync(latestFull, 'utf8'));
                const lastPosts = content.posts || content;
                const codes = lastPosts.slice(0, 5).map(item => item.code);
                stopCodes = new Set(codes);
                console.log(`   기준 게시물(최신 5개): ${Array.from(stopCodes).join(', ')}`);
            } catch (e) {
                console.error(`⚠️ 기존 데이터 로드 실패: ${e.message}`);
            }
        }
    }

    const pages = browser.contexts()[0].pages();
    let page = pages.find(p => p.url().includes('linkedin.com')) || pages[0];
    
    if (!page) {
        console.log('🔍 기존 페이지 없음. 새 페이지 생성.');
        page = await browser.contexts()[0].newPage();
    }

    console.log(`✅ 페이지 연결: ${await page.title()}`);

    let collectedItems = new Map();
    let noNewItemsCount = 0;
    let stopCodeFound = false;

    // --- Network Listener (LinkedIn Saved Posts API) ---
    // ⚠️ CRITICAL: Register BEFORE page navigation!
    if (!fs.existsSync('output_linkedin/debug')) fs.mkdirSync('output_linkedin/debug', { recursive: true });
    console.log('🔌 네트워크 리스너 등록 중...');

    // Helper function to extract images
    function extractImages(entity) {
        const images = [];
        
        // Embedded image (entityEmbeddedObject)
        const embeddedImg = entity.entityEmbeddedObject?.image?.attributes?.[0]?.detailData?.vectorImage;
        if (embeddedImg?.artifacts?.length > 0) {
            const largestArtifact = embeddedImg.artifacts.sort((a, b) => b.width - a.width)[0];
            const imgUrl = embeddedImg.rootUrl + largestArtifact.fileIdentifyingUrlPathSegment;
            images.push(imgUrl);
        }
        
        return images.filter(Boolean);
    }

    page.on('response', async (response) => {
        if (stopCodeFound) return;
        
        const url = response.url();
        const type = response.request().resourceType();
        
        // Precise URL filtering for LinkedIn Saved Posts API
        const isSavedPostsAPI = url.includes('/voyager/api/graphql') && 
                                url.includes('queryId=voyagerSearchDashClusters');
        
        if ((type === 'xhr' || type === 'fetch') && isSavedPostsAPI) {
            try {
                const json = await response.json();
                
                // Debug: Save response
                console.log(`📡 [Saved Posts API Detected] ${url.substring(0, 80)}...`);
                const timestamp = new Date().getTime();
                const cleanUrl = url.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50);
                fs.writeFileSync(`output_linkedin/debug/resp_${timestamp}_${cleanUrl}.json`, JSON.stringify(json, null, 2));
            
                // Parsing Logic - LinkedIn API Structure
                //Step 1: Extract URN list from nested data.data structure
                const urnList = json?.data?.data?.searchDashClustersByAll?.elements?.[0]?.items || [];
                
                if (urnList.length === 0) {
                    console.log('⚠️ URN 목록이 비어있습니다.');
                    return;
                }

                // Step 2: Build entity map from included array
                const entityMap = new Map();
                (json.included || []).forEach(item => {
                    // Match the actual $type format from API
                    if (item.$type && item.$type.includes('EntityResultViewModel')) {
                        entityMap.set(item.entityUrn, item);
                    }
                });

                console.log(`📊 URN ${urnList.length}개, Entity ${entityMap.size}개 발견`);

                // Step 3: Map URNs to entities and extract data
                let processedCount = 0;
                let skippedCount = 0;
                for (const urnItem of urnList) {
                    // Access the nested item object first
                    const itemData = urnItem.item || urnItem;
                    const entityUrn = itemData['*entityResult'];
                    
                    if (!entityUrn) {
                        console.log(`⚠️ URN 항목에 *entityResult 필드 없음:`, Object.keys(itemData || {}).join(', '));
                        continue;
                    }

                    const entity = entityMap.get(entityUrn);
                    if (!entity) {
                        console.log(`⚠️ URN에 대응하는 Entity 없음: ${entityUrn.substring(0, 60)}...`);
                        continue;
                    }

                    const code = entity.trackingUrn; // "urn:li:activity:7419563139156992000"
                    if (!code) {
                        console.log(`⚠️ trackingUrn 없음 in entity: ${entity.entityUrn.substring(0, 60)}...`);
                        continue;
                    }
                    
                    console.log(`🔍 Processing trackingUrn: ${code}`);
                    
                    // Check if this is a stop code
                    if (stopCodes.has(code)) {
                        console.log(`✋ 기준 게시물 발견! (code: ${code}) - 수집 중단`);
                        stopCodeFound = true;
                        break;
                    }

                    // Skip duplicates
                    if (collectedItems.has(code)) {
                        console.log(`⏭️ 이미 수집된 항목: ${code}`);
                        skippedCount++;
                        continue;
                    }

                    // Extract post data
                    const username = entity.title?.text || 'Unknown';
                    const fullText = entity.summary?.text || '';
                    const timeText = entity.secondarySubtitle?.text?.replace(' • ', '').trim() || '';
                    const postUrl = entity.navigationUrl || `https://www.linkedin.com/feed/update/${code}`;
                    const images = extractImages(entity);

                    const post = {
                        code,
                        username,
                        full_text: fullText,
                        created_at: new Date().toISOString().replace('T', ' ').split('.')[0],
                        time_text: timeText,
                        post_url: postUrl,
                        images,
                        source: 'packet'
                    };

                    collectedItems.set(code, post);
                    console.log(`⚡ [Network] Collected: ${code.substring(code.lastIndexOf(':') + 1)} | ${username.substring(0, 15)}... | ${fullText.substring(0, 30)}...`);
                    
                    if (TARGET_LIMIT > 0 && collectedItems.size >= TARGET_LIMIT) {
                        console.log(`✅ 목표 개수(${TARGET_LIMIT}) 도달`);
                        stopCodeFound = true;
                        break;
                    }
                }
            } catch (e) {
                console.error(`❌ API 파싱 에러: ${e.message}`);
            }
        }
    });

    // --- Page Navigation (AFTER listener registration) ---
    if (!page.url().includes('my-items/saved-posts')) {
        console.log('🌐 저장된 게시물 페이지로 이동 중...');
        await page.goto('https://www.linkedin.com/my-items/saved-posts/', { waitUntil: 'domcontentloaded' });
    } else {
        console.log('🔄 페이지 새로고침 (네트워크 캡처 유도)...');
        await page.reload({ waitUntil: 'domcontentloaded' });
    }
    
    // Wait for content to load
    console.log('⏳ 게시물 로딩 대기 중...');
    try {
        await page.waitForSelector('li.reusable-search__result-container, .search-results-container', { timeout: 15000 });
        console.log('✅ 게시물 컨테이너 감지됨');
    } catch (e) {
        console.log('⚠️ 게시물 컨테이너 감지 실패 - 계속 진행합니다.');
    }
    await page.waitForTimeout(3000);

    console.log(`🔍 수집 시작 (모드: ${CRAWL_MODE}, 제한: ${TARGET_LIMIT || '무제한'})`);

    while (!stopCodeFound && (TARGET_LIMIT === 0 || collectedItems.size < TARGET_LIMIT) && noNewItemsCount < MAX_NO_NEW_ITEMS) {
        
        let addedInThisBatch = 0;
        
        // --- DOM Fallback Scraper ---
        const domItems = await page.evaluate(() => {
            const items = [];
            const cards = document.querySelectorAll('.entity-result__item, li.reusable-search__result-container');
            
            cards.forEach(card => {
                try {
                    // URN Extraction
                    const anchor = card.querySelector('a.app-aware-link');
                    const url = anchor ? anchor.href : '';
                    let code = '';
                    
                    // Try to extract URN from data attributes or URL
                    const containerDiv = card.querySelector('div[data-chameleon-result-urn]');
                    if (containerDiv) {
                        code = containerDiv.getAttribute('data-chameleon-result-urn');
                    } else if (url) {
                        const match = url.match(/(urn:li:activity:\d+|urn:li:share:\d+|urn:li:article:\d+)/);
                        if (match) code = match[1];
                    }

                    if (!code) return;

                    // Valid Post?
                    if (!url.includes('/activity/') && !url.includes('/pulse/')) return;

                    // Text
                    const summary = card.querySelector('.entity-result__content-summary');
                    const full_text = summary ? summary.innerText.trim() : '';

                    // Username
                    const actor = card.querySelector('.entity-result__title-text a');
                    const username = actor ? actor.innerText.trim() : 'Unknown';

                    // Time
                    const timeContainer = card.querySelector('.entity-result__primary-subtitle'); // Often role, so check secondary
                    const secondary = card.querySelector('.entity-result__secondary-subtitle');
                    const time_text = secondary ? secondary.innerText.trim() : '';
                    
                    // Image
                    const img = card.querySelector('img');
                    const images = img ? [img.src] : [];

                    items.push({
                        code,
                        username,
                        full_text,
                        post_url: url,
                        time_text,
                        images,
                        source: 'dom'
                    });
                } catch (e) { }
            });
            return items;
        });

        for (const item of domItems) {
            if (stopCodes.has(item.code)) {
                console.log(`✋ 기준 게시물 발견 (DOM): ${item.code}`);
                stopCodeFound = true;
                break;
            }
            if (!collectedItems.has(item.code)) {
                // Add default created_at since DOM doesn't give exact TS
                item.created_at = new Date().toISOString().replace('T', ' ').split('.')[0]; 
                collectedItems.set(item.code, item);
                addedInThisBatch++;
                console.log(`📄 [DOM] Collected: ${item.code}`);
            }
        }

        if (addedInThisBatch === 0) {
            noNewItemsCount++;
            console.log(`zzz... 신규 데이터 없음 (${noNewItemsCount}/${MAX_NO_NEW_ITEMS})`);
        } else {
            noNewItemsCount = 0;
        }

        if (stopCodeFound || (TARGET_LIMIT > 0 && collectedItems.size >= TARGET_LIMIT)) break;

        console.log('⬇️ 스크롤 및 다음 버튼 확인 중...');
        await page.evaluate(() => {
            window.scrollBy(0, window.innerHeight * 1.5);
            
            // "결과 더보기" 버튼 찾기 및 클릭 (LinkedIn 특정 UI 대응)
            const loadMoreButton = document.querySelector('.scaffold-finite-scroll__load-button');
            if (loadMoreButton && loadMoreButton.offsetParent !== null) { // 보이는 상태인지 확인
                console.log('🔘 [Action] 결과 더보기 버튼 클릭');
                loadMoreButton.click();
            }
        });
        
        // Random usage simulation
        await page.waitForTimeout(2000 + Math.random() * 2000);
    }

    // Save Logic
    const finalRawItems = Array.from(collectedItems.values());
    console.log(`\n✅ 수집 완료! 총 ${finalRawItems.length}개 항목 포착`);

    if (finalRawItems.length > 0) {
        if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });
        
        const now = new Date();
        const timestamp = now.getFullYear() +
            String(now.getMonth() + 1).padStart(2, '0') +
            String(now.getDate()).padStart(2, '0') + '_' +
            String(now.getHours()).padStart(2, '0') +
            String(now.getMinutes()).padStart(2, '0') +
            String(now.getSeconds()).padStart(2, '0');
        
        const fileName = `linkedin_js_${timestamp}.json`;
        const updateDir = `${OUTPUT_DIR}/update`;
        if (!fs.existsSync(updateDir)) fs.mkdirSync(updateDir, { recursive: true });
        
        const outputPath = `${updateDir}/${fileName}`;
        const finalIndexedItems = finalRawItems.map((item, idx) => ({ index: idx + 1, ...item }));
        
        fs.writeFileSync(outputPath, JSON.stringify(finalIndexedItems, null, 2));
        console.log(`💾 신규 파일: ${outputPath}`);

        const stopCodeToLog = Array.from(stopCodes)[0] || null;
        updateFullVersion(finalRawItems, stopCodeToLog, crawlStartTime);
    } else {
        console.log('😭 수집된 데이터가 없습니다.');
        // [Debug] Dump HTML
        if (!fs.existsSync('output_linkedin/debug')) fs.mkdirSync('output_linkedin/debug', { recursive: true });
        const html = await page.content();
        fs.writeFileSync(`output_linkedin/debug/error_snapshot.html`, html);
        console.log('📸 디버그용 HTML 스냅샷 저장됨: output_linkedin/debug/error_snapshot.html');
    }

  } catch (error) {
    console.error('Error:', error);
  } finally {
    server.close();
    console.log('Relay Server Closed.');
    process.exit(0); 
  }
}

main();
