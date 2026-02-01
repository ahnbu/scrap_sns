document.addEventListener('DOMContentLoaded', () => {
    const feedJsonPath = 'output_total/total_full_20260201.json';
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

    let allPosts = [];
    let currentFilter = 'all';
    let searchQuery = '';
    let currentSort = 'date'; // 'date' (latest first) or 'saved' (sequence_id desc)

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

    async function fetchData() {
        noResults.classList.add('hidden');
        masonryGrid.innerHTML = ''; 

        try {
            // Check if data loaded from data.js
            // ⚠️ 강제 JSON Fetch 모드: data.js가 오래된 데이터일 수 있으므로 항상 JSON 파일을 로드합니다.
            if (typeof snsFeedData !== 'undefined') {
                allPosts = Array.isArray(snsFeedData) ? snsFeedData : (snsFeedData.posts || []);
                
                // Pre-process dates for consistent sorting
                allPosts.forEach(post => {
                    let dateStr = post.created_at || post.crawled_at;
                    // Ensure ISO format for consistent parsing (replace space with T)
                    if (dateStr && dateStr.includes(' ') && !dateStr.includes('T')) {
                        dateStr = dateStr.replace(' ', 'T');
                    }
                    post._dateObj = dateStr ? new Date(dateStr) : new Date(0);
                    post._seqId = post.sequence_id || 0;
                });

                totalPostsCount.textContent = `${allPosts.length} items`;
                renderPosts();
            } else {
                // Fallback to fetch for server environments if data.js missing
                const response = await fetch(feedJsonPath);
                if (!response.ok) throw new Error('Failed to load JSON');
                const data = await response.json();
                allPosts = Array.isArray(data) ? data : (data.posts || []);
                
                // Pre-process dates for consistent sorting (also for fallback)
                allPosts.forEach(post => {
                    let dateStr = post.created_at || post.crawled_at;
                    if (dateStr && dateStr.includes(' ') && !dateStr.includes('T')) {
                        dateStr = dateStr.replace(' ', 'T');
                    }
                    post._dateObj = dateStr ? new Date(dateStr) : new Date(0);
                    post._seqId = post.sequence_id || 0;
                });

                totalPostsCount.textContent = `${allPosts.length} items`;
                renderPosts();
            }
        } catch (error) {
            console.error('Error loading data:', error);
            // Error UI logic could go here if needed, but keeping it simple as requested
        }
    }

    function getFilteredPosts() {
        return allPosts.filter(post => {
            const matchesSearch = 
                (post.full_text || '').toLowerCase().includes(searchQuery) ||
                (post.username || '').toLowerCase().includes(searchQuery);
            
            const matchesFilter = 
                currentFilter === 'all' || 
                (post.sns_platform || '').toLowerCase() === currentFilter;

            return matchesSearch && matchesFilter;
        });
    }

    function renderPosts() {
        // 1. Filter Data
        let filtered = getFilteredPosts();

        // 2. Sort Data
        if (currentSort === 'date') {
            filtered.sort((a, b) => b._dateObj - a._dateObj);
        } else if (currentSort === 'saved') {
            filtered.sort((a, b) => b._seqId - a._seqId); // Descending ID
            // If sequence_id is not reliable, use original index (but filter breaks original index access)
            // Assuming sequence_id is reliable.
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
        header.innerHTML = `
            <div class="flex items-center gap-3">
                <span class="material-symbols-outlined text-[20px]" style="color: ${platformConfig.color}">${platformConfig.icon}</span>
                <div class="min-w-0">
                    <h3 class="text-sm font-semibold text-white truncate max-w-[150px]">${post.username || 'Unknown'}</h3>
                    <p class="text-xs text-gray-400 truncate" title="${post.created_at || post.crawled_at}">
                        ${dateLabel}
                    </p>
                </div>
            </div>
        `;

        // --- Content Text ---
        const content = document.createElement('div');
        const cleanText = (post.full_text || '').replace(/\n/g, '<br>');
        const isLongText = (post.full_text || '').length > 150; // Simple length check
        
        content.innerHTML = `
            <div class="relative ${isLongText ? 'cursor-pointer group/text' : ''}">
                <p class="text-sm text-gray-200 leading-relaxed font-light ${isLongText ? 'line-clamp-4' : ''} transition-all select-none" id="text-${post.post_url}">
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
        if (post.images && post.images.length > 0) {
            // Use Image Proxy to bypass CORS/CORP issues specially for Instagram/Threads CDN
            const originalUrl = post.images[0];
            let imgUrl = `https://images.weserv.nl/?url=${encodeURIComponent(originalUrl)}&output=webp`;
            
            // LinkedIn images (licdn.com) often work better directly without proxy
            if (originalUrl.includes('licdn.com')) {
                imgUrl = originalUrl;
            }
            
            const moreCount = post.images.length - 1;
            
            const imageDiv = document.createElement('div');
            imageDiv.className = 'rounded-xl overflow-hidden relative group/image mt-2 border border-white/5 bg-black/20';
            imageDiv.innerHTML = `
                <div class="w-full h-48 bg-cover bg-center cursor-zoom-in transition-transform duration-500 group-hover/image:scale-105"
                     style="background-image: url('${imgUrl}'); background-color: #222;"
                     data-src="${imgUrl}"
                     data-original="${originalUrl}"
                     data-caption="${post.username}: ${post.full_text?.slice(0,50)}..."></div>
                ${moreCount > 0 ? `
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-xs text-white flex items-center gap-1 pointer-events-none">
                    <span class="material-symbols-outlined text-[12px]">filter</span>
                    +${moreCount}
                </div>` : ''}
            `;
            
            // Image click handler
            imageDiv.querySelector('div').addEventListener('click', (e) => {
                showModal(e.target.dataset.src, e.target.dataset.caption);
            });
            
            article.appendChild(header);
            article.appendChild(content);
            article.appendChild(imageDiv);
        } else {
            article.appendChild(header);
            article.appendChild(content);
        }

        // --- Footer (Actions) ---
        const footer = document.createElement('div');
        footer.className = 'flex items-center gap-4 pt-3 mt-auto border-t border-white/5 text-gray-500 text-xs';
        footer.innerHTML = `
            <a href="${post.post_url || '#'}" target="_blank" class="flex items-center gap-1 hover:text-primary transition-colors ml-auto">
                <span>View Original</span>
                <span class="material-symbols-outlined text-[16px]">open_in_new</span>
            </a>
        `;
        article.appendChild(footer);

        return article;
    }

    // Modal Logic
    function showModal(src, caption) {
        modalImage.src = src;
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
});
