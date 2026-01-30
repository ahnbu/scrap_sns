import { chromium } from 'playwright-core';
import { startPlayWriterCDPRelayServer, getCdpUrl } from 'playwriter';
import fs from 'fs';

const OUTPUT_DIR = 'output_threads/js';

function findLatestFullFile() {
  if (!fs.existsSync(OUTPUT_DIR)) return null;
  const files = fs.readdirSync(OUTPUT_DIR)
    .filter(f => f.startsWith('threads_js_full_') && f.endsWith('.json'))
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
  const todayFull = `${OUTPUT_DIR}/threads_js_full_${today}.json`;
  
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
      existingPosts = content; // 레거시
    }

    // 레거시 sequence_id 부여
    const hasLegacy = existingPosts.some(p => !p.hasOwnProperty('sequence_id'));
    if (hasLegacy) {
      console.log(`   📋 레거시 데이터 발견 - sequence_id 부여 중...`);
      const total = existingPosts.length;
      existingPosts.forEach((p, i) => {
        if (!p.hasOwnProperty('sequence_id')) {
          p.sequence_id = total - i;
          p.crawled_at = null;
        }
      });
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
  console.log(`   📊 데이터 품질: 타임스탬프 있음 ${verifiedCount}개 / 레거시 ${legacyCount}개`);
  console.log(`   🔢 Sequence ID 범위: 1 ~ ${maxSeq}`);
}

async function main() {
  const startTimestamp = new Date();
  // ===========================
  // ⚙️ 설정 (여기만 수정하세요)
  // ===========================
  const TARGET_LIMIT = 0; // 수집 목표 개수 (0이면 전체 수집)
  const CRAWL_MODE = "update only"; // "all" 또는 "update only"
  const MAX_NO_NEW_ITEMS = 5; // 새로운 항목이 발견되지 않을 때 최대 시도 횟수
  // ===========================

  const crawlStartTime = new Date().toISOString();
  console.log('🚀 Relay 서버 시작 중...');
  const server = await startPlayWriterCDPRelayServer();
  
  try {
    let browser;
    let retries = 20; // Wait up to 40 seconds
    
    console.log('🌐 브라우저 연결 시도 중 (CDP)...');
    
    while (retries > 0) {
      try {
        browser = await chromium.connectOverCDP(getCdpUrl());
        console.log('✅ Playwriter 확장 프로그램 연결 성공!');
        break;
      } catch (e) {
        if (e.message.includes('Extension not connected') || e.message.includes('ECONNREFUSED')) {
            console.log(`⏳ 확장 프로그램 연결 대기 중... (${retries}회 남음). Threads 페이지를 새로고침하거나 Playwriter 아이콘을 클릭해주세요.`);
            await new Promise(r => setTimeout(r, 2000));
            retries--;
        } else {
            throw e;
        }
      }
    }

    if (!browser) {
        throw new Error('Failed to connect to browser extension after multiple attempts.');
    }

    // --- [Update Only] 기존 데이터 로드 (중단점 확인용) ---
    let stopCodes = new Set();
    if (CRAWL_MODE === "update only") {
        if (!fs.existsSync(OUTPUT_DIR)) {
            fs.mkdirSync(OUTPUT_DIR, { recursive: true });
        }
        // 개별 파일이 아닌 full 파일에서 최신 게시글 5개를 가져옴
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
        } else {
            console.log('⚠️ 기존 Full 파일이 없습니다. 전체 수집으로 진행합니다.');
        }
    }

    // List available pages for debugging
    const pages = browser.contexts()[0].pages();
    console.log(`📄 발견된 페이지: ${pages.length}개`);
    pages.forEach((p, i) => console.log(`  [${i}] ${p.url()}`));
    
    // Try to find Threads page, or default to the first page if available
    let page = pages.find(p => p.url().includes('threads')) || pages[0];
    
    if (!page) {
        console.log('🔍 기존 페이지를 찾을 수 없습니다. 새 페이지를 생성합니다...');
        if (browser.contexts().length === 0) {
             throw new Error('브라우저 컨텍스트를 사용할 수 없습니다.');
        }
        page = await browser.contexts()[0].newPage();
        console.log('🌐 Threads 저장됨 페이지로 이동 중...');
        await page.goto('https://www.threads.net/saved');
        // Wait for manual login if needed
        await page.waitForTimeout(3000);
    }

    console.log(`✅ 페이지 연결 완료: ${await page.title()}`);

    if (!page.url().includes('threads.net/saved')) {
        console.log('🌐 저장됨 페이지로 진입 중...');
        await page.goto('https://www.threads.net/saved');
        await page.waitForLoadState('domcontentloaded');
    }

    // Wait for content to load
    await page.waitForSelector('div[data-pressable-container="true"]', { timeout: 10000 }).catch(() => console.log('⏳ 콘텐츠 로딩 대기 시간 초과, 계속 진행합니다.'));

    let collectedItems = new Map();
    let noNewItemsCount = 0;
    let stopCodeFound = false;

    // --- [Sweet Spot] 네트워크 패킷 캡처 핸들러 추가 ---
    page.on('response', async (response) => {
        if (stopCodeFound) return;
        
        const url = response.url();
        if (url.includes('graphql/query')) {
            try {
                const json = await response.json();
                const edges = json.data?.xdt_text_app_viewer?.saved_media?.edges || 
                              json.data?.viewer?.saved_media?.edges || [];
                
                if (edges.length > 0) {
                    console.log(`⚡ [네트워크 감지] 추가 데이터 ${edges.length}개 포착!`);
                    for (const edge of edges) {
                        const post = edge.node;
                        const code = post.code;
                        
                        if (code) {
                            // 중복 기준 확인
                            if (stopCodes.has(code)) {
                                console.log(`✋ 기준 게시물 발견! (code: ${code}) - 수집 중단`);
                                stopCodeFound = true;
                                break;
                            }

                            if (!collectedItems.has(code)) {
                                const username = post.user?.username || 'Unknown';
                                const fullText = post.caption?.text || '';
                                const images = post.image_versions2?.candidates?.map(c => c.url) || [];
                                
                                // 원본 데이터가 비디오인 경우 추가
                                if (post.video_versions && post.video_versions.length > 0) {
                                    images.push(post.video_versions[0].url);
                                }

                                collectedItems.set(code, {
                                    code,
                                    username,
                                    time_text: new Date(post.taken_at * 1000).toISOString().split('T')[0],
                                    post_url: `https://www.threads.net/@${username}/post/${code}`,
                                    images: [...new Set(images)],
                                    full_text: fullText,
                                    source: 'packet'
                                });
                                
                                if (TARGET_LIMIT > 0 && collectedItems.size >= TARGET_LIMIT) break;
                            }
                        }
                    }
                }
            } catch (e) {
                // GraphQL 응답이 JSON이 아니거나 파싱 실패 시 무시
            }
        }
    });
    // ------------------------------------------------

    console.log(`🔍 수집 시작 (모드: ${CRAWL_MODE}, 제한: ${TARGET_LIMIT || '무제한'})`);

    while (!stopCodeFound && (TARGET_LIMIT === 0 || collectedItems.size < TARGET_LIMIT) && noNewItemsCount < MAX_NO_NEW_ITEMS) {
        const currentBatch = await page.evaluate(() => {
            const posts = [];
            const articleElements = document.querySelectorAll('div[data-pressable-container="true"]');
            
            articleElements.forEach((el) => {
                // 1. Username Extraction
                let username = 'Unknown';
                const userLink = el.querySelector('a[href^="/@"]');
                if (userLink) {
                     username = userLink.innerText.split('\n')[0];
                } else {
                    const userElement = el.querySelector('h2') || el.querySelector('span[style*="font-weight: 600"]');
                    if (userElement) username = userElement.innerText;
                }

                // 2. Post Link & Timestamp
                let postUrl = '';
                let timeText = '';
                const postLinks = Array.from(el.querySelectorAll('a[href*="/post/"]'));
                if (postLinks.length > 0) {
                    postUrl = postLinks[0].href;
                    timeText = postLinks[0].innerText;
                }

                // 3. Images and Media
                const images = [];
                const imgTags = el.querySelectorAll('img');
                imgTags.forEach(img => {
                    if (img.alt && img.alt.includes('Profile picture')) return;
                    if (img.clientWidth > 50 && img.clientHeight > 50) {
                        images.push(img.src);
                    }
                });

                // 4. Date Conversion Logic
                function convertRelativeDate(text) {
                    if (!text) return '';
                    const now = new Date();
                    if (text.includes('시간') || text.includes('분')) {
                        return now.toISOString().split('T')[0];
                    }
                    const dayMatch = text.match(/(\d+)일/);
                    if (dayMatch) {
                        const days = parseInt(dayMatch[1], 10);
                        const targetDate = new Date(now);
                        targetDate.setDate(now.getDate() - days);
                        return targetDate.toISOString().split('T')[0];
                    }
                    const weekMatch = text.match(/(\d+)주/);
                    if (weekMatch) {
                        const weeks = parseInt(weekMatch[1], 10);
                        const targetDate = new Date(now);
                        targetDate.setDate(now.getDate() - (weeks * 7));
                        return targetDate.toISOString().split('T')[0];
                    }
                    return text;
                }

                const formattedDate = convertRelativeDate(timeText);

                // 5. Full Text cleaning
                const rawText = el.innerText;
                let lines = rawText.split('\n').map(l => l.trim()).filter(l => l);

                if (username === 'Unknown' || username === '') {
                    if (lines.length > 0) username = lines[0];
                }

                const cleanedLines = [];
                const datePatterns = [
                    /^\d+시간$/, /^\d+분$/, /^\d+일$/, /^\d+주$/, /^\d+년$/,
                    /^\d{4}-\d{2}-\d{2}$/,
                    /^AI Threads$/, /^수정됨$/
                ];

                let isBodyStarted = false;
                let startIndex = 0;
                if (lines.length > 0 && lines[0] === username) {
                    startIndex = 1;
                }

                for (let i = startIndex; i < lines.length; i++) {
                    let line = lines[i];
                    let isMetadata = false;
                    for (const pattern of datePatterns) {
                        if (pattern.test(line)) {
                            isMetadata = true;
                            break;
                        }
                    }
                    if (!isBodyStarted && isMetadata) continue;
                    if (!isMetadata) isBodyStarted = true;
                    if (isBodyStarted) {
                        if (/^\d+$/.test(line) || /^\d+\/\d+$/.test(line)) continue;
                        if (line === '더 보기' || line === 'See more') continue;
                        cleanedLines.push(line);
                    }
                }
                
                const fullText = cleanedLines.join('\n');

                let code = '';
                if (postUrl) {
                    const parts = postUrl.split('/post/');
                    if (parts.length > 1) {
                        code = parts[1].split('/')[0].split('?')[0];
                    }
                }

                if (code) {
                    posts.push({
                        code,
                        username,
                        time_text: formattedDate,
                        post_url: postUrl,
                        images,
                        full_text: fullText,
                        source: 'dom'
                    });
                }
            });
            return posts;
        });

        let addedInThisBatch = 0;
        for (const item of currentBatch) {
            // 중복 기준 확인
            if (stopCodes.has(item.code)) {
                console.log(`✋ 기준 게시물 발견! (code: ${item.code}) - 수집 중단`);
                stopCodeFound = true;
                break;
            }

            if (!collectedItems.has(item.code)) {
                collectedItems.set(item.code, item);
                addedInThisBatch++;
                if (TARGET_LIMIT > 0 && collectedItems.size >= TARGET_LIMIT) break;
            }
        }

        console.log(`📊 현재 수집 현황: ${collectedItems.size}${TARGET_LIMIT ? '/' + TARGET_LIMIT : ''} (+${addedInThisBatch} 신규)`);

        if (addedInThisBatch === 0) {
            noNewItemsCount++;
            console.log(`zzz... 신규 데이터를 찾지 못했습니다. (${noNewItemsCount}/${MAX_NO_NEW_ITEMS})`);
        } else {
            noNewItemsCount = 0;
        }

        if (stopCodeFound) break;
        if (TARGET_LIMIT > 0 && collectedItems.size >= TARGET_LIMIT) break;

        // Scroll down to load more content
        console.log('⬇️ 스크롤 중...');
        await page.evaluate(() => {
            window.scrollBy(0, window.innerHeight * 2);
        });
        
        // Wait for potential network requests and DOM updates
        await page.waitForTimeout(3000);
    }

    const finalRawItems = Array.from(collectedItems.values());
    console.log(`\n✅ 수집 완료! 총 ${finalRawItems.length}개 항목 포착`);
    
    // [1] 개별 결과 저장 (index 포함)
    if (finalRawItems.length > 0) {
        if (!fs.existsSync(OUTPUT_DIR)) {
            fs.mkdirSync(OUTPUT_DIR, { recursive: true });
        }
        
        const now = new Date();
        const timestamp = now.getFullYear() +
            String(now.getMonth() + 1).padStart(2, '0') +
            String(now.getDate()).padStart(2, '0') + '_' +
            String(now.getHours()).padStart(2, '0') +
            String(now.getMinutes()).padStart(2, '0') +
            String(now.getSeconds()).padStart(2, '0');
        
        const fileName = `threads_js_${timestamp}.json`;
        const updateDir = `${OUTPUT_DIR}/update`;
        if (!fs.existsSync(updateDir)) {
          fs.mkdirSync(updateDir, { recursive: true });
        }
        const outputPath = `${updateDir}/${fileName}`;
        
        const finalIndexedItems = finalRawItems.map((item, idx) => ({
            index: idx + 1,
            ...item
        }));
        
        fs.writeFileSync(outputPath, JSON.stringify(finalIndexedItems, null, 2));
        console.log(`💾 신규 스크랩 저장: ${outputPath}`);

        // [2] Full 버전 업데이트 (Python 방식 동기화)
        const stopCodeToLog = Array.from(stopCodes)[0] || null;
        updateFullVersion(finalRawItems, stopCodeToLog, crawlStartTime);
    } else {
        console.log('😭 수집된 데이터가 없습니다. 파일을 저장하지 않습니다.');
    }

  } catch (error) {
    console.error('Error:', error);
  } finally {
    const endTimestamp = new Date();
    const durationMs = endTimestamp - startTimestamp;
    const hours = Math.floor(durationMs / 3600000);
    const minutes = Math.floor((durationMs % 3600000) / 60000);
    
    const formatDate = (date) => {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        const hh = String(date.getHours()).padStart(2, '0');
        const mm = String(date.getMinutes()).padStart(2, '0');
        const ss = String(date.getSeconds()).padStart(2, '0');
        return `${y}-${m}-${d} ${hh}:${mm}:${ss}`;
    };

    console.log('\n' + '='.repeat(40));
    console.log(`시작시간 : ${formatDate(startTimestamp)}`);
    console.log(`종료시간 : ${formatDate(endTimestamp)}`);
    console.log(`소요시간: ${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`);
    console.log('='.repeat(40));

    server.close();
    console.log('Relay Server Closed.');
    process.exit(0); 
  }
}

main();
