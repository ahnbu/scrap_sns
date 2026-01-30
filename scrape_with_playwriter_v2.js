
import { chromium } from 'playwright-core';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';

/**
 * [Threads Scraper v2 - Fresh Start]
 * v1의 성공 로직을 기반으로 재작성
 * - Chrome을 디버깅 모드로 실행
 * - CDP 직접 연결
 * - v1과 동일한 패킷 캡처 로직 사용
 */

async function main() {
    const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
    const USER_DATA_DIR = path.join(os.homedir(), 'AppData', 'Local', 'Google', 'Chrome', 'User Data');
    const REMOTE_DEBUGGING_PORT = 9222;
    const TARGET_COUNT = 30;
    
    console.log('=== 🚀 Threads Scraper v2 - Fresh Start ===\n');

    try {
        // Step 1: Chrome 디버깅 모드로 실행
        console.log('[1/5] Chrome 디버깅 모드 실행...');
        const chromeProcess = spawn(CHROME_PATH, [
            `--remote-debugging-port=${REMOTE_DEBUGGING_PORT}`,
            `--user-data-dir=${USER_DATA_DIR}`,
            '--profile-directory=Default',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-blink-features=AutomationControlled',
            '--remote-allow-origins=*'
        ], {
            detached: true,
            stdio: 'ignore',
            shell: true
        });
        chromeProcess.unref();
        
        console.log('   Chrome 시작... 10초 대기\n');
        await new Promise(r => setTimeout(r, 10000));

        // Step 2: CDP 연결
        console.log('[2/5] CDP 연결 시도...');
        const browser = await chromium.connectOverCDP(`http://127.0.0.1:${REMOTE_DEBUGGING_PORT}`);
        const context = browser.contexts()[0];
        console.log('   ✅ 연결 성공!\n');

        // Step 3: 페이지 확보 및 이동
        console.log('[3/5] 페이지 준비...');
        let page;
        const pages = context.pages();
        
        if (pages.length > 0) {
            console.log(`   기존 탭 ${pages.length}개 발견`);
            page = pages[0];
            await page.bringToFront();
        } else {
            console.log('   새 탭 생성');
            page = await context.newPage();
        }

        console.log('   Threads 저장 페이지로 이동...');
        await page.goto('https://www.threads.net/saved', { 
            waitUntil: 'networkidle',
            timeout: 60000 
        });
        console.log('   ✅ 페이지 로드 완료!\n');

        // 추가 대기 (페이지 완전 로딩)
        await page.waitForTimeout(3000);

        // Step 4: 네트워크 패킷 캡처 설정 (v1 로직 그대로)
        console.log('[4/5] 네트워크 패킷 캡처 시작...');
        let collectedItems = new Map();
        
        page.on('response', async (response) => {
            const url = response.url();
            if (url.includes('graphql/query')) {
                try {
                    const json = await response.json();
                    const edges = json.data?.xdt_text_app_viewer?.saved_media?.edges || 
                                  json.data?.viewer?.saved_media?.edges || [];
                    
                    if (edges.length > 0) {
                        console.log(`   📦 [패킷 감지] ${edges.length}개 포스트 발견`);
                        
                        edges.forEach(edge => {
                            const post = edge.node;
                            const code = post.code;
                            if (code && !collectedItems.has(code)) {
                                const username = post.user?.username || 'Unknown';
                                const fullText = post.caption?.text || '';
                                const images = post.image_versions2?.candidates?.map(c => c.url) || [];
                                if (post.video_versions?.length > 0) {
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
                            }
                        });
                        
                        console.log(`   ✅ 현재 수집: ${collectedItems.size}개\n`);
                    }
                } catch (e) {
                    // JSON 파싱 실패는 무시
                }
            }
        });

        // Step 5: 스크롤 및 데이터 수집
        console.log('[5/5] 자동 스크롤 시작...');
        console.log(`   목표: ${TARGET_COUNT}개\n`);
        
        let noNewItemsCount = 0;
        const MAX_NO_NEW_ITEMS = 10;
        
        while (collectedItems.size < TARGET_COUNT && noNewItemsCount < MAX_NO_NEW_ITEMS) {
            const beforeSize = collectedItems.size;
            
            // 스크롤
            await page.evaluate(() => window.scrollBy(0, window.innerHeight * 2));
            console.log(`   스크롤... (현재: ${collectedItems.size}/${TARGET_COUNT})`);
            
            // 대기
            await page.waitForTimeout(3000);
            
            // 진행 확인
            if (collectedItems.size === beforeSize) {
                noNewItemsCount++;
                console.log(`   ⚠️  새 아이템 없음 (${noNewItemsCount}/${MAX_NO_NEW_ITEMS})`);
            } else {
                noNewItemsCount = 0;
            }
        }

        // 결과 저장
        const finalItems = Array.from(collectedItems.values()).slice(0, TARGET_COUNT).map((item, idx) => ({
            index: idx + 1,
            ...item
        }));

        const outPath = 'output2/scraped_items_playwriter_v2.json';
        if (!fs.existsSync('output2')) fs.mkdirSync('output2');
        fs.writeFileSync(outPath, JSON.stringify(finalItems, null, 2));

        console.log(`\n=== 🎉 수집 완료! ===`);
        console.log(`결과: ${finalItems.length}개 아이템`);
        console.log(`파일: ${outPath}\n`);

    } catch (error) {
        console.error('\n❌ 에러 발생:', error.message);
        console.error('\n상세:', error);
    } finally {
        process.exit(0);
    }
}

main();
