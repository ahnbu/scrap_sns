import { chromium } from 'playwright-core';
import fs from 'fs';
import path from 'path';

// Chrome 실행 파일 경로 자동 감지 시도 또는 기본 경로
const EXECUTABLE_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const OUTPUT_FILE = 'output_total/simple_found_items.json';

async function main() {
  console.log('--- Simple Threads Data Finder ---');
  console.log('이 스크립트는 복잡한 설정 없이 브라우저를 띄워 데이터를 찾습니다.');
  console.log('브라우저가 열리면 로그인을 진행해주세요. 저장됨 페이지의 데이터를 자동으로 감지합니다.');

  // 브라우저 실행 (새 프로필, 헤드리스 끔)
  const browser = await chromium.launch({
    executablePath: EXECUTABLE_PATH,
    headless: false,
    args: ['--start-maximized'] // 창 최대화
  });

  const context = await browser.newContext({
    viewport: null // 뷰포트 크기 제한 없음
  });

  const page = await context.newPage();

  // 데이터 저장용 배열
  const capturedItems = [];
  const requiredCount = 10; // 테스트용으로 10개만 찾으면 성공으로 간주

  // 네트워크 핸들러 설정
  page.on('response', async (response) => {
    const url = response.url();
    // GraphQL 쿼리 감지
    if (url.includes('graphql/query')) {
      try {
        const json = await response.json();
        const data = json.data || {};
        
        // 데이터 위치 후보군
        const candidates = [
            data.xdt_text_app_viewer?.saved_media?.edges,
            data.viewer?.saved_media?.edges,
            data.text_post_app_user_saved_posts?.sections
        ];

        for(const items of candidates) {
            if (Array.isArray(items) && items.length > 0) {
                console.log(`\n⚡ 데이터 발견! (${items.length}개 항목)`);
                console.log(`   URL: ${url.substring(0, 100)}...`);
                
                // 간단한 파싱
                items.forEach(item => {
                    const node = item.node || item; // 구조에 따라 다름
                    if (node) {
                        capturedItems.push(node);
                    }
                });
                
                console.log(`   누적 수집량: ${capturedItems.length}개`);
            }
        }

      } catch (e) {
        // JSON 파싱 실패 등은 무시
      }
    }
  });

  try {
    console.log('🌐 Threads 저장됨 페이지로 이동합니다...');
    await page.goto('https://www.threads.net/saved');

    console.log('\n🛑 [ACTION REQUIRED]');
    console.log('   브라우저에서 로그인을 완료하고, "저장됨" 목록이 보일 때까지 스크롤하세요.');
    console.log('   데이터가 감지되면 자동으로 콘솔에 출력됩니다.');
    console.log('   10개 이상 찾으면 자동으로 종료하고 저장합니다.\n');

    // 무한 대기 (조건 충족 시 break)
    while (capturedItems.length < requiredCount) {
        if (page.isClosed()) {
            console.log('브라우저가 닫혔습니다. 종료합니다.');
            break;
        }
        await page.waitForTimeout(1000);
    }

    if (capturedItems.length >= requiredCount) {
        console.log(`\n🎉 목표 달성! (${capturedItems.length}개)`);
        
        // 결과 저장
        if (!fs.existsSync(path.dirname(OUTPUT_FILE))) {
            fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
        }
        fs.writeFileSync(OUTPUT_FILE, JSON.stringify(capturedItems, null, 2));
        console.log(`💾 데이터 저장됨: ${OUTPUT_FILE}`);
    }

  } catch (err) {
    console.error('오류 발생:', err);
  } finally {
    console.log('브라우저를 종료합니다.');
    await browser.close();
  }
}

main();
