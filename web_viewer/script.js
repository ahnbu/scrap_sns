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
    let currentSort = localStorage.getItem('sns_sort_order') || 'date'; // Persist sort order

    // Load states from localStorage
    const favorites = new Set(JSON.parse(localStorage.getItem('sns_favorites') || '[]'));
    const foldedPosts = new Set(JSON.parse(localStorage.getItem('sns_folded_posts') || '[]'));
    const postTags = JSON.parse(localStorage.getItem('sns_tags') || '{}');
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
                (currentFilter === 'favorites' ? favorites.has(post.post_url) : (post.sns_platform || '').toLowerCase() === currentFilter);

            const matchesTag = !currentTag || (postTags[post.post_url] || []).includes(currentTag);

            return matchesSearch && matchesFilter && matchesTag;
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
                const aFav = favorites.has(a.post_url);
                const bFav = favorites.has(b.post_url);
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

        const isFavorited = favorites.has(post.post_url);
        const isFolded = foldedPosts.has(post.post_url) && !searchQuery; // Show content if searching

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
                <button class="fold-btn p-1.5 rounded-lg hover:bg-white/10 text-gray-400" data-url="${post.post_url}" title="${isFolded ? 'Unfold card' : 'Fold card'}">
                    <span class="material-symbols-outlined text-[20px]">
                        ${isFolded ? 'expand_more' : 'expand_less'}
                    </span>
                </button>
                <button class="favorite-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors group/fav" data-url="${post.post_url}">
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

        // --- Content Text ---
        const content = document.createElement('div');
        if (isFolded) content.classList.add('hidden-content');
        
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
                         onclick="window.open('${post.post_url}', '_blank')">
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
                input.className = 'tag-input';
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
        renderTags(tagContainer, post.post_url);
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
            <a href="${post.post_url || '#'}" target="_blank" class="flex items-center gap-1 hover:text-primary transition-colors ml-auto">
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

        container.innerHTML = '<span class="global-tag-label">Tags:</span>';
        
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
});
