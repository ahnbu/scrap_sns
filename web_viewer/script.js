document.addEventListener('DOMContentLoaded', () => {
    // const feedJsonPath = 'output_total/total_full_20260201.json'; // ❌ 삭제됨 (동적 로딩으로 변경)
    const masonryGrid = document.getElementById('masonryGrid');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const noResults = document.getElementById('noResults');
    const totalPostsCount = document.getElementById('totalPostsCount');
    const searchInput = document.getElementById('searchInput');
    const filterContainer = document.getElementById('filterContainer');
    const refreshBtn = document.getElementById('refreshBtn');

    // Modal elements
    const imageModal = document.getElementById('imageModal');
    const modalImage = document.getElementById('modalImage');
    const modalCaption = document.getElementById('modalCaption');
    const closeModal = document.getElementById('closeModal');

    // Management Modal elements
    const settingsBtn = document.getElementById('settingsBtn');
    const managementModal = document.getElementById('managementModal');
    const closeManagementModalBtn = document.getElementById('closeManagementModal');
    const invisiblePostsList = document.getElementById('invisiblePostsList');

    let allPosts = [];
    let currentFilter = 'all';
    let searchQuery = '';
    let currentSort = localStorage.getItem('sns_sort_order') || 'date'; // Persist sort order

    // Load states from localStorage
    const favorites = new Set(JSON.parse(localStorage.getItem('sns_favorites') || '[]'));
    const invisiblePosts = new Set(JSON.parse(localStorage.getItem('sns_invisible_posts') || '[]'));
    const foldedPosts = new Set(JSON.parse(localStorage.getItem('sns_folded_posts') || '[]'));
    const postTags = JSON.parse(localStorage.getItem('sns_tags') || '{}');
    
    // Cleanup 'undefined' key from postTags if it exists (remnant of failed migration)
    if (postTags['undefined']) {
        console.warn('🧹 Cleaning up invalid "undefined" key from localStorage tags');
        delete postTags['undefined'];
        localStorage.setItem('sns_tags', JSON.stringify(postTags));
    }
    
    let currentTag = null;

    // Sync Initial Sort UI
    function syncSortUI() {
        const activeSortBtn = document.querySelector(`[data-sort="${currentSort}"]`);
        if (activeSortBtn) {
            document.getElementById('currentSortLabel').textContent = activeSortBtn.textContent.trim();
            document.querySelectorAll('[data-sort]').forEach(b => b.classList.remove('font-bold', 'text-primary'));
            activeSortBtn.classList.add('font-bold', 'text-primary');
        }
    }
    syncSortUI();

    // Initialize
    fetchData();

    // --- Event Listeners ---
    // Search
    searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value.toLowerCase();
        renderPosts();
    });

    // Filters
    filterContainer.addEventListener('click', (e) => {
        const btn = e.target.closest('.filter-chip');
        if (!btn) return;

        // Update active visual state
        document.querySelectorAll('.filter-chip').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        currentFilter = btn.dataset.filter;
        renderPosts();
    });

    // Sort Dropdown Toggle
    const sortBtn = document.getElementById('sortBtn');
    const sortDropdown = document.getElementById('sortDropdown');

    sortBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        sortDropdown.classList.toggle('hidden');
    });

    document.addEventListener('click', (e) => {
        if (!sortBtn.contains(e.target) && !sortDropdown.contains(e.target)) {
            sortDropdown.classList.add('hidden');
        }
    });

    // Sort Selection Logic
    document.querySelectorAll('[data-sort]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            currentSort = e.target.dataset.sort;
            localStorage.setItem('sns_sort_order', currentSort); // Save to storage
            document.getElementById('currentSortLabel').textContent = e.target.textContent.trim();
            // Close dropdown
            document.getElementById('sortDropdown').classList.add('hidden');
            
            // Visual feedback
            document.querySelectorAll('[data-sort]').forEach(b => b.classList.remove('font-bold', 'text-primary'));
            e.target.classList.add('font-bold', 'text-primary');

            renderPosts();
        });
    });

    refreshBtn.addEventListener('click', fetchData);

    // Run Scraper functionality
    const runScrapBtn = document.getElementById('runScrapBtn');
    runScrapBtn.addEventListener('click', async () => {
        if (!confirm('스크래핑을 시작하시겠습니까? (이 작업은 수 분이 소요될 수 있습니다)')) return;

        // UI State: Loading
        const originalContent = runScrapBtn.innerHTML;
        runScrapBtn.disabled = true;
        runScrapBtn.classList.add('opacity-50', 'cursor-not-allowed');
        runScrapBtn.innerHTML = `
            <span class="material-symbols-outlined text-[20px] animate-spin text-primary">sync</span>
            <span class="font-medium whitespace-nowrap">Running...</span>
        `;

        try {
            // First, check if server is running
            const statusCheck = await fetch('http://localhost:5000/api/status').catch(() => null);
            if (!statusCheck || !statusCheck.ok) {
                alert('Flask 서버가 실행되고 있지 않습니다. 터미널에서 "python server.py"를 실행해주세요.');
                return;
            }

            const response = await fetch('http://localhost:5000/api/run-scrap', {
                method: 'POST'
            });
            const result = await response.json();

            if (result.status === 'success') {
                alert('스크래핑이 완료되었습니다! 데이터를 새로고침합니다.');
                fetchData(); // Refresh feed
            } else {
                alert(`에러 발생: ${result.message}`);
            }
        } catch (error) {
            console.error('Scraping Error:', error);
            alert('서버와 통신 중 오류가 발생했습니다.');
        } finally {
            // Restore UI State
            runScrapBtn.disabled = false;
            runScrapBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            runScrapBtn.innerHTML = originalContent;
        }
    });

    // Download Functionality
    const downloadBtn = document.getElementById('downloadBtn');
    const downloadDropdown = document.getElementById('downloadDropdown');

    if (downloadBtn && downloadDropdown) {
        downloadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            downloadDropdown.classList.toggle('hidden');
        });

        document.addEventListener('click', (e) => {
            if (!downloadBtn.contains(e.target) && !downloadDropdown.contains(e.target)) {
                downloadDropdown.classList.add('hidden');
            }
        });

        document.querySelectorAll('[data-action^="download-"]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = e.currentTarget.dataset.action;
                const [_, scope, format] = action.split('-'); // e.g., download-filtered-json
                downloadData(scope, format);
                downloadDropdown.classList.add('hidden');
            });
        });
    }

    function downloadData(scope, format) {
        const postsToSave = scope === 'all' ? allPosts : getFilteredPosts();
        
        if (postsToSave.length === 0) {
            alert('저장할 데이터가 없습니다.');
            return;
        }

        const dateStr = new Date().toISOString().slice(0, 10);
        let content = '';
        
        let filenameLabel = scope;
        if (scope === 'filtered' && searchQuery) {
            // Sanitize: allow Korean, alphanumeric, replace spaces with underscore
            const safeQuery = searchQuery.replace(/[^a-zA-Z0-9가-힣\s]/g, '').trim().replace(/\s+/g, '_');
            if (safeQuery) filenameLabel = safeQuery;
        }

        let filename = `sns_data_${filenameLabel}_${dateStr}.${format === 'json' ? 'json' : 'md'}`;
        let mimeType = format === 'json' ? 'application/json' : 'text/markdown';

        // Map data to required fields
        const mappedData = postsToSave.map(post => {
            const dateObj = post._dateObj || new Date(post.created_at || post.crawled_at);
            return {
                author: post.username,
                date: dateObj.toISOString().slice(0, 10), // yyyy-mm-dd
                body: post.full_text,
                link: post.post_url,
                platform: post.sns_platform
            };
        });

        if (format === 'json') {
            content = JSON.stringify(mappedData, null, 2);
        } else {
            // Markdown Format
            content = mappedData.map(item => {
                return `## [${item.date}] ${item.author} (${item.platform})
[Original Link](${item.link})

${item.body}

---`;
            }).join('\n\n');
        }

        // Trigger Download
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // Modal Events
    closeModal.addEventListener('click', hideModal);
    imageModal.addEventListener('click', (e) => {
        if (e.target === imageModal) hideModal();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && imageModal.classList.contains('show')) hideModal();
    });

    // Window resize handling for Masonry
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(renderPosts, 200); // Debounce
    });

    // --- Core Functions ---
    /**
     * 자동 태그 규칙을 게시물에 적용
     * @param {Array} posts - 대상 게시물
     * @param {boolean} silent - true면 알림 없음, false면 결과 알림 및 렌더링
     */
    async function applyAutoTags(posts, silent = true, onProgress = null) {
        const manualRules = JSON.parse(localStorage.getItem('sns_auto_tag_rules') || '[]');
        
        // 1. Collect all unique tags from existing posts (Implicit Rules)
        const existingTags = new Set();
        Object.values(postTags).forEach(tags => tags.forEach(tag => existingTags.add(tag)));
        
        // 2. Combine Rules: Manual Rules + Implicit Rules (Keyword = Tag)
        const allRules = new Map();
        
        // Helper to validate rule
        const isValidRule = (kw) => kw && kw.trim().length > 0;

        // Add implicit rules first
        existingTags.forEach(tag => {
            if (isValidRule(tag)) {
                allRules.set(tag.toLowerCase(), tag);
            }
        });

        // Add/Overwrite with manual rules
        manualRules.forEach(rule => {
            if (isValidRule(rule.keyword)) {
                allRules.set(rule.keyword.toLowerCase(), rule.tag);
            }
        });

        if (allRules.size === 0) return 0;

        let updateCount = 0;
        let debugStats = { hits: 0, skips: 0, distinctTags: existingTags.size };
        
        const total = posts.length;
        const CHUNK_SIZE = 100;
        
        for (let i = 0; i < total; i += CHUNK_SIZE) {
            const chunk = posts.slice(i, i + CHUNK_SIZE);
            
            chunk.forEach(post => {
                const text = (post.full_text || '').toLowerCase();
                const url = post.post_url || post.source_url || post.code;
                
                if (!postTags[url]) postTags[url] = [];
                let tags = postTags[url];
                let modified = false;

                allRules.forEach((tagName, keyword) => {
                    // Use simple includes() for partial matching as requested by user
                    // This matches "AI" in "AI", "AInews", "GenAI", etc.
                    if (text.includes(keyword)) {
                        if (!tags.includes(tagName)) {
                            tags.push(tagName);
                            modified = true;
                            updateCount++;
                        } else {
                            debugStats.skips++;
                        }
                        debugStats.hits++;
                    }
                });

                if (modified) {
                    postTags[url] = tags;
                }
            });

            // Update Progress
            if (onProgress) {
                const percent = Math.min(100, Math.round(((i + chunk.length) / total) * 100));
                onProgress(percent);
                await new Promise(requestAnimationFrame); // Yield to UI
            }
        }

        if (updateCount > 0) {
            localStorage.setItem('sns_tags', JSON.stringify(postTags));
            updateGlobalTags();
            if (!silent) {
                renderPosts();
            }
        } 
        
        return { count: updateCount, ruleCount: allRules.size, stats: debugStats };
    }

    // --- Data Loading ---
    async function fetchData() {
        if (loadingIndicator) loadingIndicator.classList.remove('hidden');
        if (noResults) noResults.classList.add('hidden');
        if (masonryGrid) masonryGrid.innerHTML = ''; 
        
        let data = null;
        let loadMode = 'unknown';

        try {
            // 1순위: 서버 API 호출 (최신 데이터 + 태그 통합 로드)
            const [postsRes, tagsRes] = await Promise.all([
                fetch('http://localhost:5000/api/latest-data'),
                fetch('http://localhost:5000/api/get-tags')
            ]);

            if (postsRes.ok) {
                data = await postsRes.json();
                loadMode = 'live';
                console.log('✨ Live Mode: Loaded posts from server');
                
                if (tagsRes.ok) {
                    const serverTags = await tagsRes.json();
                    console.log('🔗 Loaded tags from server sync:', Object.keys(serverTags).length);
                    // Merge server tags into postTags
                    Object.assign(postTags, serverTags);
                    
                    // Cleanup: Remove empty/invalid tags from all postTags
                    Object.keys(postTags).forEach(url => {
                        postTags[url] = postTags[url].filter(t => t && t.trim().length > 0);
                        if (postTags[url].length === 0) delete postTags[url];
                    });

                    localStorage.setItem('sns_tags', JSON.stringify(postTags));
                    syncTagsToServer(); // Update server with cleaned data if needed
                }
            } else {
                throw new Error('Server response not OK');
            }
        } catch (error) {
            // 2순위: 로컬 data.js 폴백
            console.warn('📡 Server unavailable, falling back to local data.js');
            if (typeof window.snsFeedData !== 'undefined') {
                data = window.snsFeedData;
                loadMode = 'offline';
                console.log('📦 Offline Mode: Loaded from data.js');
            } else if (typeof snsFeedData !== 'undefined') {
                // 핸들링 보완: window 생략된 경우 대비
                data = snsFeedData;
                loadMode = 'offline';
                console.log('📦 Offline Mode: Loaded from data.js (global)');
            } else {
                // 3순위: 데이터 없음 에러
                console.error('❌ Data load failed: No source available');
                if (noResults) {
                    noResults.innerHTML = `
                        <div class="text-center p-12">
                            <span class="material-symbols-outlined text-gray-500 text-6xl mb-4">cloud_off</span>
                            <p class="text-xl text-gray-300">데이터를 불러올 수 없습니다.</p>
                            <p class="text-sm text-gray-500 mt-2">서버가 실행 중인지 확인하거나 data.js 파일이 존재하는지 확인하세요.</p>
                        </div>
                    `;
                    noResults.classList.remove('hidden');
                }
                if (loadingIndicator) loadingIndicator.classList.add('hidden');
                return;
            }
        }

        // 데이터 적용
        allPosts = Array.isArray(data) ? data : (data.posts || []);
        
        // Pre-process (날짜 포맷 정규화)
        allPosts.forEach(post => {
            let dateStr = post.created_at || post.crawled_at;
            if (dateStr && typeof dateStr === 'string' && dateStr.includes(' ') && !dateStr.includes('T')) {
                dateStr = dateStr.replace(' ', 'T');
            }
            post._dateObj = dateStr ? new Date(dateStr) : new Date(0);
            post._seqId = post.sequence_id || 0;
        });

        // 자동 태그 적용 및 렌더링
        await applyAutoTags(allPosts, true);
        
        if (totalPostsCount) {
            totalPostsCount.textContent = `${allPosts.length} 건`;
        }
        
        renderPosts();
        
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
        
        // 모드 알림 토스트 (오프라인일 때만)
        if (loadMode === 'offline') {
            const toast = document.createElement('div');
            toast.className = 'fixed bottom-6 right-6 bg-yellow-500/10 border border-yellow-500/30 text-yellow-300 px-4 py-2 rounded-xl text-xs backdrop-blur-md z-50 animate-fade-in-up';
            toast.innerHTML = '📂 Offline Mode: 로컬 데이터 로드됨';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 4000);
        }
    }

    function getFilteredPosts() {
        return allPosts.filter(post => {
            const matchesSearch = 
                (post.full_text || '').toLowerCase().includes(searchQuery) ||
                (post.username || '').toLowerCase().includes(searchQuery);
            
            const postUrl = post.post_url || post.source_url || post.code;
            
            const matchesFilter = 
                currentFilter === 'all' || 
                (currentFilter === 'favorites' ? favorites.has(postUrl) : (post.sns_platform || '').toLowerCase() === currentFilter);

            const matchesTag = !currentTag || (postTags[postUrl] || []).includes(currentTag);
            const matchesVisibility = !invisiblePosts.has(postUrl);

            return matchesSearch && matchesFilter && matchesTag && matchesVisibility;
        });
    }

    function renderPosts() {
        // Update global tags first to ensure the list is fresh
        updateGlobalTags();
        
        // 1. Filter Data
        let filtered = getFilteredPosts();

        // 2. Sort Data
        if (currentSort === 'date') {
            filtered.sort((a, b) => b._dateObj - a._dateObj);
        } else if (currentSort === 'saved') {
            filtered.sort((a, b) => b._seqId - a._seqId); // Descending ID
            // If sequence_id is not reliable, use original index (but filter breaks original index access)
            // Assuming sequence_id is reliable.
        } else if (currentSort === 'favorites') {
            filtered.sort((a, b) => {
                const aUrl = a.post_url || a.source_url || a.code;
                const bUrl = b.post_url || b.source_url || b.code;
                const aFav = favorites.has(aUrl);
                const bFav = favorites.has(bUrl);
                if (aFav && !bFav) return -1;
                if (!aFav && bFav) return 1;
                return b._dateObj - a._dateObj; // Secondary sort by date
            });
        }

        // 3. UI Updates
        if (filtered.length === 0) {
            noResults.classList.remove('hidden');
            masonryGrid.innerHTML = '';
            return;
        } else {
            noResults.classList.add('hidden');
        }

        // 3. Masonry Distribution
        let colCount = 1;
        const width = window.innerWidth;
        if (width >= 1536) colCount = 4;
        else if (width >= 1024) colCount = 3;
        else if (width >= 768) colCount = 2;

        // Reset Grid structure
        masonryGrid.innerHTML = '';
        const columns = [];
        for (let i = 0; i < colCount; i++) {
            const colDiv = document.createElement('div');
            colDiv.className = 'masonry-col flex-1 flex flex-col gap-6 min-w-0';
            masonryGrid.appendChild(colDiv);
            columns.push(colDiv);
        }

        // Distribute posts
        filtered.forEach((post, index) => {
            const card = createCard(post);
            const colIndex = index % colCount;
            columns[colIndex].appendChild(card);
        });
    }

    function createCard(post) {
        const article = document.createElement('article');
        article.className = 'glass-card rounded-2xl p-4 flex flex-col gap-3 group break-inside-avoid relative overflow-hidden transition-all duration-300';
        
        // --- Platform Config ---
        const platform = (post.sns_platform || 'other').toLowerCase();
        let platformConfig = { icon: 'link', color: '#888', name: platform };
        
        if (platform.includes('thread')) platformConfig = { icon: 'alternate_email', color: '#fff', name: 'Threads' };
        else if (platform.includes('linkedin')) platformConfig = { icon: 'work', color: '#0A66C2', name: 'LinkedIn' };
        else if (platform.includes('twitter') || platform.includes('x')) platformConfig = { icon: 'flutter_dash', color: '#1DA1F2', name: 'Twitter' };
        else if (platform.includes('insta')) platformConfig = { icon: 'photo_camera', color: '#E1306C', name: 'Instagram' };

        // Date Logic
        const dateObj = post._dateObj;
        const options = { year: 'numeric', month: 'numeric', day: 'numeric' };
        
        let dateLabel;
        if (post.created_at) {
            dateLabel = dateObj.toLocaleDateString('ko-KR', options);
        } else if (post.time_text) {
            dateLabel = post.time_text;
        } else {
            dateLabel = `${dateObj.toLocaleDateString('ko-KR', options)}`;
        }



        // --- Header ---
        const header = document.createElement('div');
        header.className = 'flex items-center justify-between';
        
        let iconHtml;
        if (platform.includes('linkedin')) {
            iconHtml = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#0A66C2">
                    <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
                </svg>
            `;
        } else {
            iconHtml = `<span class="material-symbols-outlined text-[20px]" style="color: ${platformConfig.color}">${platformConfig.icon}</span>`;
        }

        const postUrl = post.post_url || post.source_url || post.code;
        const isFavorited = favorites.has(postUrl);
        const isFolded = foldedPosts.has(postUrl) && !searchQuery; // Show content if searching

        if (isFolded) {
            article.classList.add('minimized');
        }

        header.innerHTML = `
            <div class="flex items-center gap-3">
                ${iconHtml}
                <div class="min-w-0">
                    <h3 class="text-sm font-semibold text-white truncate max-w-[150px]">${post.username || 'Unknown'}</h3>
                    <p class="text-xs text-gray-400 truncate" title="${post.created_at || post.crawled_at}">
                        ${dateLabel}
                    </p>
                </div>
            </div>
            <div class="flex items-center gap-1">
                <button class="fold-btn p-1.5 rounded-lg hover:bg-white/10 text-gray-400" data-url="${postUrl}" title="${isFolded ? 'Unfold card' : 'Fold card'}">
                    <span class="material-symbols-outlined text-[20px]">
                        ${isFolded ? 'expand_more' : 'expand_less'}
                    </span>
                </button>
                <button class="invisible-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-400 hover:text-red-400" data-url="${postUrl}" title="Hide post">
                    <span class="material-symbols-outlined text-[20px]">visibility</span>
                </button>
                <button class="copy-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-400 hover:text-primary" data-url="${postUrl}" title="Copy text">
                    <span class="material-symbols-outlined text-[20px]">content_copy</span>
                </button>
                <button class="favorite-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors group/fav" data-url="${postUrl}">
                    <span class="material-symbols-outlined text-[20px] ${isFavorited ? 'text-yellow-400 fill-1' : 'text-gray-500 group-hover/fav:text-yellow-400'} transition-all">
                        ${isFavorited ? 'star' : 'star'}
                    </span>
                </button>
            </div>
        `;


        const favBtn = header.querySelector('.favorite-btn');
        favBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const url = post.post_url;
            const icon = favBtn.querySelector('span');
            
            if (favorites.has(url)) {
                favorites.delete(url);
                icon.classList.remove('text-yellow-400', 'fill-1');
                icon.classList.add('text-gray-500');
                if (currentFilter === 'favorites') {
                    // Smoothly remove the card if we're in the favorites view
                    article.style.opacity = '0';
                    article.style.transform = 'scale(0.9)';
                    setTimeout(() => renderPosts(), 200);
                }
            } else {
                favorites.add(url);
                icon.classList.add('text-yellow-400', 'fill-1');
                icon.classList.remove('text-gray-500');
                
                // Add a little pop animation
                icon.animate([
                    { transform: 'scale(1)' },
                    { transform: 'scale(1.4)' },
                    { transform: 'scale(1)' }
                ], { duration: 300, easing: 'cubic-bezier(0.175, 0.885, 0.32, 1.275)' });
            }
            
        localStorage.setItem('sns_favorites', JSON.stringify([...favorites]));
            updateGlobalTags(); // Update global tags to reflect favorite/tag changes if needed (though favorites doesn't affect tags currently)
        });

        // --- Copy Text Handler ---
        const copyBtn = header.querySelector('.copy-btn');
        copyBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const textToCopy = post.full_text || '';
            const icon = copyBtn.querySelector('span');

            try {
                await navigator.clipboard.writeText(textToCopy);
                
                // Visual Feedback
                const originalIcon = icon.textContent;
                icon.textContent = 'check';
                icon.classList.add('text-green-400');
                
                setTimeout(() => {
                    icon.textContent = originalIcon;
                    icon.classList.remove('text-green-400');
                }, 2000);
            } catch (err) {
                console.error('Failed to copy: ', err);
                alert('복사에 실패했습니다.');
            }
        });

        // --- Invisible Toggle Handler ---
        const invisibleBtn = header.querySelector('.invisible-btn');
        invisibleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const url = postUrl;
            
            if (confirm('이 게시글을 피드에서 숨기시겠습니까? (추후 설정에서 복구 가능)')) {
                invisiblePosts.add(url);
                localStorage.setItem('sns_invisible_posts', JSON.stringify([...invisiblePosts]));
                
                // Add fade-out animation
                article.style.opacity = '0';
                article.style.transform = 'scale(0.9)';
                article.style.transition = 'all 0.3s ease';
                
                setTimeout(() => renderPosts(), 300);
            }
        });

        // --- Content Text ---
        const content = document.createElement('div');
        if (isFolded) content.classList.add('hidden-content');
        
        const cleanText = (post.full_text || '').replace(/\n/g, '<br>');
        const isLongText = (post.full_text || '').length > 150; // Simple length check
        
        content.innerHTML = `
            <div class="relative ${isLongText ? 'cursor-pointer group/text' : ''}">
                <p class="text-sm text-gray-200 leading-relaxed font-light ${isLongText ? 'line-clamp-4' : ''} transition-all select-none" id="text-${postUrl}">
                    ${cleanText}
                </p>
                ${isLongText ? `
                <div class="mt-2 text-xs font-medium text-gray-500 group-hover/text:text-gray-300 transition-colors flex items-center gap-1 read-more-indicator">
                    <span>Read more</span>
                    <span class="material-symbols-outlined text-[14px]">expand_more</span>
                </div>` : ''}
            </div>
        `;

        if (isLongText) {
            content.addEventListener('click', (e) => {
                e.stopPropagation();
                const p = content.querySelector('p');
                const indicator = content.querySelector('.read-more-indicator');
                const isCollapsed = p.classList.contains('line-clamp-4');
                
                if (isCollapsed) {
                    p.classList.remove('line-clamp-4');
                    if (indicator) indicator.innerHTML = `<span>Show less</span><span class="material-symbols-outlined text-[14px]">expand_less</span>`;
                } else {
                    p.classList.add('line-clamp-4');
                    if (indicator) indicator.innerHTML = `<span>Read more</span><span class="material-symbols-outlined text-[14px]">expand_more</span>`;
                }
            });
        }

        // --- Images ---
        let imageDiv = null;
        if (post.images && post.images.length > 0) {
            // Use Image Proxy to bypass CORS/CORP issues specially for Instagram/Threads CDN
            const originalUrl = post.images[0];
            const isVideo = originalUrl.toLowerCase().includes('.mp4');
            
            let imgUrl = `https://wsrv.nl/?url=${encodeURIComponent(originalUrl)}&output=webp`;
            
            // 1. Try Local Image first
            if (post.local_images && post.local_images.length > 0) {
                imgUrl = post.local_images[0];
            } 
            // 2. LinkedIn images (licdn.com) often work better directly without proxy
            else if (originalUrl.includes('licdn.com')) {
                imgUrl = originalUrl;
            }
            
            const moreCount = post.images.length - 1;
            
            imageDiv = document.createElement('div');
            imageDiv.className = 'rounded-xl overflow-hidden relative group/image mt-2 border border-white/5 bg-black/20';
            if (isFolded) imageDiv.classList.add('hidden-content');
            
            if (isVideo) {
                // Placeholder for video posts
                imageDiv.innerHTML = `
                    <div class="w-full min-h-[200px] flex flex-col items-center justify-center bg-black/40 cursor-pointer py-10" 
                         onclick="window.open('${postUrl}', '_blank')">
                        <span class="material-symbols-outlined text-4xl text-white/50 mb-2">play_circle</span>
                        <span class="text-xs text-white/40">Video Post (Click to view)</span>
                    </div>
                `;
            } else {
                const placeholderImg = "https://placehold.co/400x300/222/555?text=Image+Unavailable";
                imageDiv.innerHTML = `
                    <img src="${imgUrl}" 
                         class="w-full h-auto max-h-[600px] object-contain cursor-zoom-in transition-transform duration-500 group-hover/image:scale-105"
                         data-src="${imgUrl}"
                         data-original="${originalUrl}"
                         data-caption="${post.username}: ${post.full_text?.slice(0,50)}..."
                         onerror="if(this.src!=='${originalUrl}'){this.src='${originalUrl}';console.log('Proxy failed, trying original');}else{this.src='${placeholderImg}';this.onerror=null;console.log('All attempts failed');}"
                         alt="SNS Post Image">
                    ${moreCount > 0 ? `
                    <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-xs text-white flex items-center gap-1 pointer-events-none">
                        <span class="material-symbols-outlined text-[12px]">filter</span>
                        +${moreCount}
                    </div>` : ''}
                `;
                
                // Image click handler (only for actual images)
                const imgEl = imageDiv.querySelector('img');
                if (imgEl) {
                    imgEl.addEventListener('click', (e) => {
                        showModal(e.target.dataset.src, e.target.dataset.caption);
                    });
                }
            }
        }

        // --- Tags Section ---
        const tagsWrapper = document.createElement('div');
        tagsWrapper.className = 'flex flex-col gap-2 mt-2';
        if (isFolded) tagsWrapper.classList.add('hidden-content');
        
        function renderTags(container, url) {
            container.innerHTML = '';
            // Clear any lingering suggestions when re-rendering tags
            if (container.parentElement) {
                const existingSuggestions = container.parentElement.querySelectorAll('.tag-suggestions');
                existingSuggestions.forEach(s => s.remove());
            }
            const tags = postTags[url] || [];
            
            tags.forEach(tag => {
                const tagChip = document.createElement('div');
                tagChip.className = 'tag-chip';
                tagChip.innerHTML = `
                    <span>${tag}</span>
                    <span class="tag-remove material-symbols-outlined text-[12px]" data-tag="${tag}">close</span>
                `;
                tagChip.querySelector('.tag-remove').addEventListener('click', (e) => {
                    e.stopPropagation();
                    const tagToRemove = e.currentTarget.dataset.tag;
                    postTags[url] = postTags[url].filter(t => t !== tagToRemove);
                    if (postTags[url].length === 0) delete postTags[url];
                    localStorage.setItem('sns_tags', JSON.stringify(postTags));
                    renderTags(container, url);
                    updateGlobalTags();
                    syncTagsToServer(); // Real-time sync
                });
                container.appendChild(tagChip);
            });

            // Add Input / Add Button
            const addBtn = document.createElement('button');
            addBtn.className = 'tag-add-btn';
            addBtn.innerHTML = `<span class="material-symbols-outlined text-[14px]">add</span>Tag`;
            
            addBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                addBtn.style.display = 'none';
                
                const input = document.createElement('input');
                input.className = 'tag-input rounded-full';
                input.placeholder = 'Add tag...';
                input.type = 'text';
                
                container.appendChild(input);
                input.focus();

                // Suggestions logic
                const allExistingTags = new Set();
                Object.values(postTags).forEach(tags => tags.forEach(tag => allExistingTags.add(tag)));
                const postExistingTags = new Set(postTags[url] || []);
                const suggestions = Array.from(allExistingTags)
                    .filter(tag => !postExistingTags.has(tag))
                    .sort();

                let suggestionsDiv = null;
                if (suggestions.length > 0) {
                    suggestionsDiv = document.createElement('div');
                    suggestionsDiv.className = 'tag-suggestions w-full'; // Ensure full width
                    suggestions.forEach(tag => {
                        const item = document.createElement('div');
                        item.className = 'suggestion-item';
                        item.textContent = tag;
                        item.addEventListener('mousedown', (ev) => {
                            ev.preventDefault();
                            if (!postTags[url]) postTags[url] = [];
                            postTags[url].push(tag);
                            localStorage.setItem('sns_tags', JSON.stringify(postTags));
                            renderTags(container, url);
                            updateGlobalTags();
                            syncTagsToServer(); // Real-time sync
                        });
                        suggestionsDiv.appendChild(item);
                    });
                    // Clear any existing suggestions in this post card first
                    const existingSuggestions = container.parentElement.querySelectorAll('.tag-suggestions');
                    existingSuggestions.forEach(s => s.remove());
                    
                    container.parentElement.appendChild(suggestionsDiv);
                }

                const handleAdd = () => {
                    const val = input.value.trim();
                    if (val) {
                        if (!postTags[url]) postTags[url] = [];
                        if (!postTags[url].includes(val)) {
                            postTags[url].push(val);
                            localStorage.setItem('sns_tags', JSON.stringify(postTags));
                            updateGlobalTags();
                            syncTagsToServer(); // Real-time sync
                        }
                    }
                    renderTags(container, url);
                };

                input.addEventListener('keydown', (ev) => {
                    if (ev.key === 'Enter') handleAdd();
                    if (ev.key === 'Escape') renderTags(container, url);
                });
                
                input.addEventListener('blur', () => {
                    // Small delay to allow suggestion click to fire
                    setTimeout(handleAdd, 150);
                });
            });
            
            container.appendChild(addBtn);
        }

        const tagContainer = document.createElement('div');
        tagContainer.className = 'tag-container';
        renderTags(tagContainer, postUrl);
        tagsWrapper.appendChild(tagContainer);
        
        article.appendChild(header);
        article.appendChild(content);
        if (imageDiv) {
            article.appendChild(imageDiv);
        }
        article.appendChild(tagsWrapper);

        // --- Footer (Actions) ---
        const footer = document.createElement('div');
        footer.className = 'flex items-center gap-4 pt-3 mt-auto border-t border-white/5 text-gray-500 text-xs';
        if (isFolded) footer.classList.add('hidden-content');
        footer.innerHTML = `
            <a href="${postUrl || '#'}" target="_blank" class="flex items-center gap-1 hover:text-primary transition-colors ml-auto">
                <span>View Original</span>
                <span class="material-symbols-outlined text-[16px]">open_in_new</span>
            </a>
        `;
        article.appendChild(footer);

        // *** Fold Toggle Handler ***
        const foldBtn = header.querySelector('.fold-btn');
        foldBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const url = post.post_url;
            
            // Toggle state
            const isCurrentlyFolded = foldedPosts.has(url);
            if (isCurrentlyFolded) {
                foldedPosts.delete(url);
            } else {
                foldedPosts.add(url);
            }
            localStorage.setItem('sns_folded_posts', JSON.stringify([...foldedPosts]));
            
            // Update UI directly
            const newFoldedState = !isCurrentlyFolded;
            
            // Update button icon/tooltip
            const icon = foldBtn.querySelector('span');
            icon.textContent = newFoldedState ? 'expand_more' : 'expand_less';
            foldBtn.setAttribute('title', newFoldedState ? 'Unfold card' : 'Fold card');
            
            // Toggle minimized class on card
            if (newFoldedState) {
                article.classList.add('minimized');
            } else {
                article.classList.remove('minimized');
            }
            
            // Toggle hidden-content class on actual elements
            const elementsToToggle = [content, tagsWrapper, footer];
            if (imageDiv) elementsToToggle.push(imageDiv);
            
            elementsToToggle.forEach(el => {
                if (newFoldedState) {
                    el.classList.add('hidden-content');
                } else {
                    el.classList.remove('hidden-content');
                }
            });
        });

        return article;
    }

    function updateGlobalTags() {
        const container = document.getElementById('globalTagsContainer');
        if (!container) return;

        // Extract unique tags
        const allUniqueTags = new Set();
        Object.values(postTags).forEach(tags => tags.forEach(tag => allUniqueTags.add(tag)));
        
        const sortedTags = Array.from(allUniqueTags).sort();
        
        if (sortedTags.length === 0) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = '';
        
        sortedTags.forEach(tag => {
            const tagBtn = document.createElement('button');
            tagBtn.className = `global-tag-chip ${currentTag === tag ? 'active' : ''}`;
            tagBtn.textContent = tag;
            tagBtn.addEventListener('click', () => {
                if (currentTag === tag) {
                    currentTag = null; // Unselect
                } else {
                    currentTag = tag;
                }
                renderPosts();
            });
            container.appendChild(tagBtn);
        });

        if (currentTag && !allUniqueTags.has(currentTag)) {
            currentTag = null; // If selected tag was deleted
        }
    }

    // Modal Logic
    function showModal(src, caption) {
        // Apply fallback also for modal
        modalImage.onerror = function() {
            if (this.src !== this.dataset.original && this.dataset.original) {
                console.log('Modal proxy failed, trying original');
                this.src = this.dataset.original;
            } else {
                this.onerror = null; // Prevent infinite loop
            }
        };
        
        modalImage.src = src;
        // Store original URL if it was proxied, to use in fallback
        if (src.includes('wsrv.nl')) {
             const urlParams = new URLSearchParams(new URL(src).search);
             modalImage.dataset.original = urlParams.get('url');
        } else {
             modalImage.dataset.original = '';
        }

        modalCaption.textContent = caption || '';
        imageModal.classList.remove('hidden');
        // Small delay to allow display:block to apply before opacity transition
        requestAnimationFrame(() => {
            imageModal.classList.add('show');
            document.body.classList.add('modal-open');
        });
    }

    function hideModal() {
        imageModal.classList.remove('show');
        document.body.classList.remove('modal-open');
        setTimeout(() => {
            imageModal.classList.add('hidden');
            modalImage.src = '';
        }, 300);
    }

    // --- Management Modal Functions ---
    // --- Server Sync Functions ---
    async function syncTagsToServer() {
        try {
            const tags = JSON.parse(localStorage.getItem('sns_tags') || '{}');
            const response = await fetch('http://localhost:5000/api/save-tags', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(tags)
            });
            const result = await response.json();
            if (result.status === 'success') {
                console.log('📤 Tags synced to server successfully');
            } else {
                console.error('Failed to sync tags:', result.message);
            }
        } catch (error) {
            console.error('Error syncing tags to server:', error);
        }
    }

    function openManagementModal() {
        managementModal.classList.remove('hidden');
        requestAnimationFrame(() => {
            managementModal.classList.add('show');
            document.body.classList.add('modal-open');
        });
        
        // Sync tags to server for export
        syncTagsToServer();

        // Default to Hidden Posts tab
        switchTab('tabHidden');
        renderInvisibleList();
        renderAutoTagRules();
    }

    function hideManagementModal() {
        managementModal.classList.remove('show');
        document.body.classList.remove('modal-open');
        setTimeout(() => {
            managementModal.classList.add('hidden');
        }, 300);
    }

    // Tab Switching
    function switchTab(targetId) {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            if (btn.dataset.target === targetId) {
                btn.classList.add('active', 'border-primary', 'text-white');
                btn.classList.remove('border-transparent', 'text-gray-500');
            } else {
                btn.classList.remove('active', 'border-primary', 'text-white');
                btn.classList.add('border-transparent', 'text-gray-500');
            }
        });

        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.toggle('hidden', pane.id !== targetId);
        });

        // Update Header Icon/Title based on tab

    }

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.target));
    });

    function renderInvisibleList() {
        invisiblePostsList.innerHTML = '';
        const noHiddenPosts = document.getElementById('noHiddenPosts');
        
        if (invisiblePosts.size === 0) {
            noHiddenPosts.classList.remove('hidden');
            invisiblePostsList.classList.add('hidden');
            return;
        }

        noHiddenPosts.classList.add('hidden');
        invisiblePostsList.classList.remove('hidden');

        const hiddenItems = allPosts.filter(post => invisiblePosts.has(post.post_url));
        hiddenItems.forEach(post => {
            const item = document.createElement('div');
            item.className = 'invisible-post-item w-full';
            const platform = (post.sns_platform || 'other').toLowerCase();
            let icon = 'link';
            let iconColor = '#888';
            if (platform.includes('thread')) { icon = 'alternate_email'; iconColor = '#fff'; }
            else if (platform.includes('linkedin')) { icon = 'work'; iconColor = '#0A66C2'; }
            
            item.innerHTML = `
                <span class="material-symbols-outlined text-[20px] shrink-0" style="color: ${iconColor}">${icon}</span>
                <div class="invisible-content">
                    <h4 class="truncate">${post.username || 'Unknown'}</h4>
                    <p class="truncate text-xs opacity-60">${(post.full_text || 'No content').slice(0, 100)}</p>
                </div>
                <button class="restore-btn hover:scale-105 active:scale-95 transition-all shrink-0" data-url="${post.post_url}">
                    Restore
                </button>
            `;
            
            item.querySelector('.restore-btn').addEventListener('click', (e) => {
                const url = e.target.dataset.url;
                invisiblePosts.delete(url);
                localStorage.setItem('sns_invisible_posts', JSON.stringify([...invisiblePosts]));
                renderInvisibleList();
                renderPosts();
            });
            invisiblePostsList.appendChild(item);
        });
    }

    // --- Auto Tagging Rules UI ---
    function renderAutoTagRules() {
        const manualRules = JSON.parse(localStorage.getItem('sns_auto_tag_rules') || '[]');
        const container = document.getElementById('autoTagRulesList');
        container.innerHTML = '';
        
        // 1. Collect and Merge Rules
        const mergedRules = [];
        
        // A. Manual Rules
        manualRules.forEach((rule, index) => {
            mergedRules.push({
                type: 'manual',
                keyword: rule.keyword,
                tag: rule.tag,
                index: index
            });
        });
        
        // B. Implicit Rules (from Tags)
        const existingTags = new Set();
        Object.values(postTags).forEach(tags => tags.forEach(tag => existingTags.add(tag)));
        
        existingTags.forEach(tag => {
            // Only add if not covered by manual rules (exact match)
            const exists = manualRules.some(r => r.keyword.toLowerCase() === tag.toLowerCase() && r.tag === tag);
            if (!exists) {
                mergedRules.push({
                    type: 'auto',
                    keyword: tag, // Keyword is the tag itself
                    tag: tag,
                    index: -1
                });
            }
        });
        
        // Sort: Manual first, then alphabetical by tag
        mergedRules.sort((a, b) => {
            if (a.type !== b.type) return a.type === 'manual' ? -1 : 1;
            return a.tag.localeCompare(b.tag);
        });

        if (mergedRules.length === 0) {
            container.innerHTML = '<p class="text-center py-10 text-gray-600 text-sm italic">No rules defined yet.</p>';
            return;
        }

        mergedRules.forEach(rule => {
            const isManual = rule.type === 'manual';
            const badgeColor = isManual ? 'bg-primary/10 border-primary/20 text-primary' : 'bg-blue-400/10 border-blue-400/20 text-blue-400';
            const badgeLabel = isManual ? 'Manual' : 'Auto';
            
            const div = document.createElement('div');
            div.className = 'flex items-center justify-between p-4 bg-white/5 rounded-2xl border border-white/5 group/rule hover:bg-white/10 transition-colors';
            
            div.innerHTML = `
                <div class="flex items-center gap-3">
                    <div class="px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${badgeColor}">${badgeLabel}</div>
                    ${!isManual ? `<div class="text-[10px] text-gray-500 uppercase font-bold tracking-wider">Tag</div>` : `<div class="px-2 py-0.5 rounded bg-gray-700/50 text-gray-400 text-[10px] font-bold border border-white/10">Key</div>`}
                    <span class="text-sm font-medium text-white">${rule.keyword}</span>
                    
                    ${isManual ? `
                    <span class="material-symbols-outlined text-gray-600 text-sm">arrow_forward</span>
                    <div class="px-2 py-0.5 rounded bg-green-900/30 text-green-400 text-[10px] font-bold border border-green-500/20">Tag</div>
                    <span class="text-sm font-medium text-white">${rule.tag}</span>
                    ` : ''}
                </div>
                
                ${isManual ? `
                <button class="delete-rule-btn opacity-0 group-hover/rule:opacity-100 p-2 text-gray-500 hover:text-red-400 transition-all" data-index="${rule.index}">
                    <span class="material-symbols-outlined text-[20px]">delete</span>
                </button>` : `
                <div class="opacity-0 group-hover/rule:opacity-100 cursor-help" title="Generated from existing tag">
                    <span class="material-symbols-outlined text-[18px] text-gray-600">auto_awesome</span>
                </div>
                `}
            `;
            
            if (isManual) {
                div.querySelector('.delete-rule-btn').addEventListener('click', () => {
                    manualRules.splice(rule.index, 1);
                    localStorage.setItem('sns_auto_tag_rules', JSON.stringify(manualRules));
                    renderAutoTagRules();
                });
            }
            container.appendChild(div);
        });
    }

    // Add Rule
    document.getElementById('addAutoTagRuleBtn').addEventListener('click', () => {
        const keywordInput = document.getElementById('autoTagKeyword');
        const tagInput = document.getElementById('autoTagTagName');
        const keyword = keywordInput.value.trim();
        const tag = tagInput.value.trim();

        if (!keyword || !tag) {
            alert('Please enter both keyword and tag name.');
            return;
        }

        const rules = JSON.parse(localStorage.getItem('sns_auto_tag_rules') || '[]');
        rules.push({ keyword, tag });
        localStorage.setItem('sns_auto_tag_rules', JSON.stringify(rules));

        keywordInput.value = '';
        tagInput.value = '';
        renderAutoTagRules();
    });

    // Batch Update
    document.getElementById('runBatchAutoTagBtn').addEventListener('click', async () => {
        if (!confirm(`총 ${allPosts.length}개의 게시물에 대해 자동 태그 규칙을 적용하시겠습니까?`)) return;

        const btn = document.getElementById('runBatchAutoTagBtn');
        const statusArea = document.getElementById('batchUpdateStatus');
        const progressBar = document.getElementById('batchProgressBar');
        const progressPercent = document.getElementById('batchProgressPercent');
        const resultMessage = document.getElementById('batchResultMessage');

        // Reset UI
        btn.disabled = true;
        statusArea.classList.remove('hidden');
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';
        resultMessage.classList.add('hidden');
        
        // Run
        // Run
        const { count, ruleCount, stats } = await applyAutoTags(allPosts, false, (percent) => {
            progressBar.style.width = `${percent}%`;
            progressPercent.textContent = `${percent}%`;
        });

        // Done
        progressBar.style.width = '100%';
        progressPercent.textContent = '100%';
        
        let msg = count > 0 
            ? `완료! 총 ${count}개의 태그가 추가되었습니다.` 
            : `완료! 새로 적용된 태그가 없습니다.`;
            
        // Add debug info
        msg += ` (규칙: ${ruleCount}, 감지: ${stats.hits}, 중복건너뜀: ${stats.skips})`;
        
        resultMessage.textContent = msg;
        resultMessage.classList.remove('hidden');

        // Re-enable button after 500ms
        setTimeout(() => {
            btn.disabled = false;
        }, 500);
    });

    // Logo / Home Logic
    const logoHome = document.getElementById('logoHome');
    if (logoHome) logoHome.addEventListener('click', () => location.reload());

    // Settings Event Listeners
    if (settingsBtn) settingsBtn.addEventListener('click', openManagementModal);
    if (closeManagementModalBtn) closeManagementModalBtn.addEventListener('click', hideManagementModal);
    managementModal.addEventListener('click', (e) => {
        if (e.target === managementModal) hideManagementModal();
    });
});
