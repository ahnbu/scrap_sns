
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

    // improved scraping logic
    const items = await page.evaluate(() => {
        function cleanText(rawText, username) {
            let lines = rawText.split('\n');
            const cleanedLines = [];

            // 1. Remove username from the first line if present
            if (lines.length > 0 && lines[0].trim() === username) {
                lines.shift();
            }

            const datePatterns = [
                /^\d+시간$/, /^\d+분$/, /^\d+일$/,
                /^\d{4}-\d{2}-\d{2}$/, /^\d+주$/,
                /^AI Threads$/, /^수정됨$/
            ];

            let isBodyStarted = false;

            for (let i = 0; i < lines.length; i++) {
                let line = lines[i].trim();
                // Skip empty lines
                if (!line) continue;

                let isMetadata = false;
                for (const pattern of datePatterns) {
                    if (pattern.test(line)) {
                        isMetadata = true;
                        break;
                    }
                }

                // If body hasn't started and this is metadata, skip it
                if (!isBodyStarted && isMetadata) continue;
                
                // If body hasn't started and this is NOT metadata, start body
                if (!isBodyStarted && !isMetadata) isBodyStarted = true;

                if (isBodyStarted) {
                    // Skip page numbers (e.g., "1", "1/4") or simple counters
                    if (/^\d+$/.test(line) || /^\d+\/\d+$/.test(line)) continue;
                    cleanedLines.push(line);
                }
            }
            return cleanedLines.join('\n').trim();
        }

        const posts = [];
        // Threads uses 'div[data-pressable-container="true"]' for the clickable area of posts
        const articleElements = document.querySelectorAll('div[data-pressable-container="true"]');
        
        articleElements.forEach((el, index) => {
            if (index >= 5) return; // Limit to 5
            
            // 1. Username Extraction
            // Look for the profile link which starts with /@
            let username = 'Unknown';
            const userLink = el.querySelector('a[href^="/@"]');
            if (userLink) {
                 // The text sometimes contains the ID and name, take the first line or specific span
                 username = userLink.innerText.split('\n')[0];
            } else {
                // Fallback: look for h2 or bold text
                const userElement = el.querySelector('h2') || el.querySelector('span[style*="font-weight: 600"]');
                if (userElement) username = userElement.innerText;
            }

            // 2. Post Link & Timestamp
            // The timestamp is usually a link to the post itself (contains /post/)
            let postUrl = '';
            let timeText = '';
            // Find links that contain /post/ and are NOT inside the quoted post (if any)
            const postLinks = Array.from(el.querySelectorAll('a[href*="/post/"]'));
            if (postLinks.length > 0) {
                // The first time link is usually the post's own link
                postUrl = postLinks[0].href;
                timeText = postLinks[0].innerText;
            }

            // 3. Images and Media
            const images = [];
            const imgTags = el.querySelectorAll('img');
            imgTags.forEach(img => {
                // Filter out small icons or likely profile pictures (heuristic: typically small or square with specific classes)
                // Threads images in posts are usually larger. Let's capture likely content images.
                // Profile pics often have alt text like "Profile picture of..."
                if (img.alt && img.alt.includes('Profile picture')) return;
                if (img.clientWidth > 50 && img.clientHeight > 50) {
                    images.push(img.src);
                }
            });

            // 4. Full Text cleaning & Username extraction fallback
            const rawText = el.innerText;
            let lines = rawText.split('\n').map(l => l.trim()).filter(l => l);

            // If username wasn't found via selector, take the first line
            if (username === 'Unknown' || username === '') {
                if (lines.length > 0) {
                    username = lines[0];
                }
            }

            // Date Conversion Logic
            function convertRelativeDate(text) {
                if (!text) return '';
                const now = new Date();
                
                // Hours or Minutes -> Today
                if (text.includes('시간') || text.includes('분')) {
                    return now.toISOString().split('T')[0];
                }
                
                // Days -> Subtract days
                const dayMatch = text.match(/(\d+)일/);
                if (dayMatch) {
                    const days = parseInt(dayMatch[1], 10);
                    const targetDate = new Date(now);
                    targetDate.setDate(now.getDate() - days);
                    return targetDate.toISOString().split('T')[0];
                }

                // Weeks -> Subtract weeks * 7
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

            // Cleaning Logic

            // Cleaning Logic
            const cleanedLines = [];
            const datePatterns = [
                /^\d+시간$/, /^\d+분$/, /^\d+일$/, /^\d+주$/, /^\d+년$/,
                /^\d{4}-\d{2}-\d{2}$/,
                /^AI Threads$/, /^수정됨$/
            ];

            let isBodyStarted = false;
            
            // Skip the first line if it matches the username (it usually does)
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

                // Skip metadata before body starts
                if (!isBodyStarted && isMetadata) continue;
                
                // If it's not metadata, body has started
                if (!isMetadata) isBodyStarted = true;

                if (isBodyStarted) {
                    // Skip counters and page numbers
                    if (/^\d+$/.test(line) || /^\d+\/\d+$/.test(line)) continue;
                    // Skip "See more" or "더 보기" text often found at the end
                    if (line === '더 보기' || line === 'See more') continue;
                    
                    cleanedLines.push(line);
                }
            }
            
            const fullText = cleanedLines.join('\n');

            // Extract code from postUrl
            let code = '';
            if (postUrl) {
                const parts = postUrl.split('/post/');
                if (parts.length > 1) {
                    code = parts[1].split('/')[0].split('?')[0];
                }
            }

            posts.push({
                index: index + 1,
                code,
                username,
                time_text: formattedDate,
                post_url: postUrl,
                images,
                full_text: fullText
            });
        });
        return posts;
    });

    console.log('--- Scraped Items ---');
    console.log(JSON.stringify(items, null, 2));
    
    // Save to file
    fs.writeFileSync('output2/scraped_items_playwriter.json', JSON.stringify(items, null, 2));
    console.log('Saved to output2/scraped_items_playwriter.json');

  } catch (error) {
    console.error('Error:', error);
  } finally {
    // Don't close the browser!
    server.close();
    console.log('Relay Server Closed.');
    process.exit(0); 
  }
}

main();
