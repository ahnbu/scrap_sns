
import { chromium } from 'playwright-core';
import { startPlayWriterCDPRelayServer, getCdpUrl } from 'playwriter';
import fs from 'fs';

async function main() {
  console.log('Starting Relay Server...');
  const server = await startPlayWriterCDPRelayServer();
  
  try {
    let browser;
    let retries = 20; // Wait up to 40 seconds
    
    console.log('Connecting to Browser via CDP...');
    
    while (retries > 0) {
      try {
        browser = await chromium.connectOverCDP(getCdpUrl());
        console.log('Successfully connected to Playwriter extension!');
        break;
      } catch (e) {
        if (e.message.includes('Extension not connected') || e.message.includes('ECONNREFUSED')) {
            console.log(`Waiting for extension connection... (${retries} attempts left). Please REFRESH the Threads page or click the Playwriter icon.`);
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
    
    // List available pages for debugging
    const pages = browser.contexts()[0].pages();
    console.log(`Found ${pages.length} pages:`);
    pages.forEach((p, i) => console.log(`  [${i}] ${p.url()} - ${typeof p.title === 'function' ? 'title ok' : 'title unknown'}`));
    
    // Try to find Threads page, or default to the first page if available
    let page = pages.find(p => p.url().includes('threads')) || pages[0];
    
    if (!page) {
        console.log('No existing page found. Creating a new page...');
        if (browser.contexts().length === 0) {
             throw new Error('No browser context available.');
        }
        page = await browser.contexts()[0].newPage();
        console.log('Navigating to Threads Saved page...');
        await page.goto('https://www.threads.net/saved');
        // Wait for manual login if needed
        await page.waitForTimeout(3000);
    }

    console.log(`Connected to page: ${await page.title()}`);

    // Navigate if not already there (optional, but ensures we are on the right page)
    if (!page.url().includes('threads.net/saved')) {
        console.log('Navigating to saved page...');
        await page.goto('https://www.threads.net/saved');
        await page.waitForLoadState('domcontentloaded');
    }

    // Wait for content to load
    await page.waitForSelector('div[data-pressable-container="true"]', { timeout: 10000 }).catch(() => console.log('Timeout waiting for selector, proceeding anyway.'));

    const TARGET_COUNT = 30;
    let collectedItems = new Map();
    let noNewItemsCount = 0;
    const MAX_NO_NEW_ITEMS = 5;

    // --- [Sweet Spot] 네트워크 패킷 캡처 핸들러 추가 ---
    page.on('response', async (response) => {
        const url = response.url();
        if (url.includes('graphql/query')) {
            try {
                const json = await response.json();
                const edges = json.data?.xdt_text_app_viewer?.saved_media?.edges || 
                              json.data?.viewer?.saved_media?.edges || [];
                
                if (edges.length > 0) {
                    console.log(`[Network] Detected ${edges.length} items from packet!`);
                    edges.forEach(edge => {
                        const post = edge.node;
                        const code = post.code;
                        if (code && !collectedItems.has(code)) {
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
                        }
                    });
                }
            } catch (e) {
                // GraphQL 응답이 JSON이 아니거나 파싱 실패 시 무시
            }
        }
    });
    // ------------------------------------------------

    console.log(`Starting collection. Target: ${TARGET_COUNT} items (Packet + DOM).`);

    while (collectedItems.size < TARGET_COUNT && noNewItemsCount < MAX_NO_NEW_ITEMS) {
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
            if (!collectedItems.has(item.code)) {
                collectedItems.set(item.code, item);
                addedInThisBatch++;
            }
        }

        console.log(`Current items: ${collectedItems.size}/${TARGET_COUNT} (+${addedInThisBatch} new)`);

        if (addedInThisBatch === 0) {
            noNewItemsCount++;
            console.log(`No new items found. (${noNewItemsCount}/${MAX_NO_NEW_ITEMS})`);
        } else {
            noNewItemsCount = 0;
        }

        if (collectedItems.size >= TARGET_COUNT) break;

        // Scroll down to load more content
        console.log('Scrolling down...');
        await page.evaluate(() => {
            window.scrollBy(0, window.innerHeight * 2);
        });
        
        // Wait for potential network requests and DOM updates
        await page.waitForTimeout(3000);
    }

    const finalItems = Array.from(collectedItems.values()).slice(0, TARGET_COUNT).map((item, idx) => ({
        index: idx + 1,
        ...item
    }));

    console.log(`--- Finished! Collected ${finalItems.length} items ---`);
    
    // Save to file
    if (!fs.existsSync('output2')) {
        fs.mkdirSync('output2');
    }
    fs.writeFileSync('output2/scraped_items_playwriter.json', JSON.stringify(finalItems, null, 2));
    console.log('Saved to output2/scraped_items_playwriter.json');

  } catch (error) {
    console.error('Error:', error);
  } finally {
    server.close();
    console.log('Relay Server Closed.');
    process.exit(0); 
  }
}

main();
