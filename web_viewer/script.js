// XSS escape utility
function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

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
    let searchResults = null;
    let currentFilter = 'all';
    let searchQuery = '';
    let _searchTimer = null;
    let _searchAbortController = null;
    let _pendingPosts = [];
    let _ioObserver = null;
    let _ioSentinel = null;
    let columns = [];
    let currentSort = localStorage.getItem('sns_sort_order') || 'date'; // Persist sort order
    const _postDetailCache = new Map();
    const _inFlightDetails = new Set();

    // Load states from localStorage
    const favorites = new Set(JSON.parse(localStorage.getItem('sns_favorites') || '[]'));
    const invisiblePosts = new Set(JSON.parse(localStorage.getItem('sns_invisible_posts') || '[]'));
    const foldedPosts = new Set(JSON.parse(localStorage.getItem('sns_folded_posts') || '[]'));
    const postTags = JSON.parse(localStorage.getItem('sns_tags') || '{}');
    const tagTypes = JSON.parse(localStorage.getItem('sns_tag_types') || '{}');
    const todos = JSON.parse(localStorage.getItem('sns_todos') || '{}');
    
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
        const nextQuery = (e.target.value || '').trim();
        searchQuery = nextQuery;
        clearTimeout(_searchTimer);
        if (_searchAbortController) {
            _searchAbortController.abort();
        }
        if (!nextQuery) {
            searchResults = null;
            renderPosts();
            return;
        }
        _searchTimer = setTimeout(() => {
            void runServerSearch(nextQuery);
        }, 200);
    });

    // Filters
    filterContainer.addEventListener('click', (e) => {
        const btn = e.target.closest('.filter-chip');
        if (!btn) return;

        // Update active visual state
        document.querySelectorAll('.filter-chip').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        currentFilter = btn.dataset.filter;
        if (searchQuery) {
            void runServerSearch(searchQuery);
            return;
        }
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

            if (searchQuery) {
                void runServerSearch(searchQuery);
                return;
            }
            renderPosts();
        });
    });

    refreshBtn.addEventListener('click', fetchData);

    // Run Scraper functionality
    const runScrapBtn = document.getElementById('runScrapBtn');
    const scrapDropdown = document.getElementById('scrapDropdown');

    if (runScrapBtn && scrapDropdown) {
        runScrapBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            scrapDropdown.classList.toggle('hidden');
        });

        document.addEventListener('click', (e) => {
            if (!runScrapBtn.contains(e.target) && !scrapDropdown.contains(e.target)) {
                scrapDropdown.classList.add('hidden');
            }
        });

        document.querySelectorAll('[data-mode]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const mode = e.currentTarget.dataset.mode;
                const modeLabel = mode === 'all' ? '전체 크롤링' : '최근 업데이트';
                
                if (!confirm(`${modeLabel}을 시작하시겠습니까? (이 작업은 수 분이 소요될 수 있습니다)`)) return;

                scrapDropdown.classList.add('hidden');

                // UI State: Loading
                const originalContent = runScrapBtn.innerHTML;
                runScrapBtn.disabled = true;
                runScrapBtn.classList.add('opacity-50', 'cursor-not-allowed');
                runScrapBtn.innerHTML = `
                    <span class="material-symbols-outlined text-[20px] animate-spin text-primary">sync</span>
                    <span class="font-medium text-xs whitespace-nowrap">Running...</span>
                `;

                try {
                    // First, check if server is running
                    const statusCheck = await fetch('/api/status').catch(() => null);
                    if (!statusCheck || !statusCheck.ok) {
                        alert('Flask 서버가 실행되고 있지 않습니다. 터미널에서 "python server.py"를 실행해주세요.');
                        return;
                    }

                    const response = await fetch('/api/run-scrap', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ mode: mode })
                    });
                    const result = await response.json();

                    if (result.status === 'success') {
                        const stats = result.stats || {
                            total: 0,
                            threads: 0,
                            linkedin: 0,
                            twitter: 0,
                            total_count: 0,
                            threads_count: 0,
                            linkedin_count: 0,
                            twitter_count: 0
                        };
                        let msg;
                        if (mode === 'all') {
                            msg = `전체 재수집 완료! (전체 ${stats.total_count}건)\n\n`
                                + `쓰레드 — ${stats.threads_count}건\n`
                                + `링크드인 — ${stats.linkedin_count}건\n`
                                + `X — ${stats.twitter_count}건\n\n`
                                + `데이터를 새로고침합니다.`;
                        } else {
                            msg = `스크래핑 완료! 총 ${stats.total}건 신규 추가 (전체 ${stats.total_count}건)\n\n`
                                + `쓰레드 — ${stats.threads}건 추가 (전체 ${stats.threads_count}건)\n`
                                + `링크드인 — ${stats.linkedin}건 추가 (전체 ${stats.linkedin_count}건)\n`
                                + `X — ${stats.twitter}건 추가 (전체 ${stats.twitter_count}건)\n\n`
                                + `데이터를 새로고침합니다.`;
                        }
                        alert(msg);
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
        });
    }

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
                author: post.display_name || post.username,
                date: dateObj.toISOString().slice(0, 10), // yyyy-mm-dd
                body: post.full_text,
                link: resolvePostUrl(post),
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
    function mergeAutoTags(urlToAutoTags) {
        Object.entries(urlToAutoTags || {}).forEach(([url, tags]) => {
            const merged = new Set(postTags[url] || []);
            (tags || []).forEach((tag) => {
                if (tag && String(tag).trim()) {
                    merged.add(tag);
                }
            });
            if (merged.size > 0) {
                postTags[url] = [...merged];
            }
        });
    }

    async function applyAutoTagRules() {
        const rules = JSON.parse(localStorage.getItem('sns_auto_tag_rules') || '[]');
        if (rules.length === 0) {
            renderPosts();
            return { matchedPostCount: 0, ruleCount: 0 };
        }

        const response = await fetch('/api/auto-tag/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rules: rules.map((rule) => ({
                    ...rule,
                    match_field: 'all',
                })),
            }),
        });

        if (!response.ok) {
            throw new Error(`Failed to apply auto tag rules: ${response.status}`);
        }

        const payload = await response.json();
        mergeAutoTags(payload.url_to_auto_tags || {});
        localStorage.setItem('sns_tags', JSON.stringify(postTags));

        const saveResponse = await fetch('/api/save-tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(postTags),
        });
        if (!saveResponse.ok) {
            throw new Error(`Failed to save tags: ${saveResponse.status}`);
        }

        updateGlobalTags();
        renderPosts();
        return {
            matchedPostCount: Number(payload.matched_post_count || 0),
            ruleCount: Number(payload.rule_count || rules.length),
        };
    }

    function migrateLegacyTagKeys(posts) {
        const normalizeThreadsUrl = (url) => {
            if (!url || typeof url !== 'string') return '';
            return url
                .replace(/^https?:\/\/www\.threads\.net\//, 'https://www.threads.com/')
                .replace(/^https?:\/\/threads\.net\//, 'https://www.threads.com/')
                .replace(/^https?:\/\/threads\.com\//, 'https://www.threads.com/');
        };

        const extractThreadsCode = (value) => {
            if (!value || typeof value !== 'string') return '';
            const postMatch = value.match(/\/post\/([A-Za-z0-9_-]+)/);
            if (postMatch) return postMatch[1];
            const tMatch = value.match(/\/t\/([A-Za-z0-9_-]+)/);
            if (tMatch) return tMatch[1];
            if (!value.includes('://')) return value;
            return '';
        };

        const canonicalByCode = new Map();
        const aliasToCanonical = new Map();
        const registerAlias = (alias, canonical) => {
            if (!alias || !canonical) return;
            aliasToCanonical.set(alias, canonical);
            const normalized = normalizeThreadsUrl(alias);
            if (normalized) aliasToCanonical.set(normalized, canonical);
        };

        posts.forEach(post => {
            const canonical = resolvePostUrl(post);
            const code = post.platform_id || post.code || extractThreadsCode(post.url || post.post_url || '');
            if (!canonical || !code) return;

            canonicalByCode.set(code, canonical);
            registerAlias(canonical, canonical);
            registerAlias(canonical.replace('https://www.threads.com/', 'https://www.threads.net/'), canonical);
            registerAlias(`https://www.threads.net/t/${code}`, canonical);
            registerAlias(`https://www.threads.com/t/${code}`, canonical);
        });

        const resolveLegacyKey = (key) => {
            if (!key || key === 'undefined') return '';

            const direct = aliasToCanonical.get(key) || aliasToCanonical.get(normalizeThreadsUrl(key));
            if (direct) return direct;

            const code = extractThreadsCode(key);
            if (code && canonicalByCode.has(code)) {
                return canonicalByCode.get(code);
            }

            if (key.includes('threads.net/') || key.includes('threads.com/')) {
                return normalizeThreadsUrl(key) || key;
            }

            return key;
        };

        const cleanTagList = (tags) =>
            Array.from(new Set((tags || []).filter(tag => tag && tag.trim().length > 0)));

        let migrated = 0;
        Object.keys(postTags).forEach(key => {
            if (key === 'undefined') {
                delete postTags[key];
                migrated += 1;
                return;
            }

            const target = resolveLegacyKey(key);
            if (!target || target === key) {
                if (key !== target && !target) {
                    delete postTags[key];
                    migrated += 1;
                }
                return;
            }

            const cleaned = cleanTagList([
                ...(postTags[target] || []),
                ...(postTags[key] || []),
            ]);

            if (cleaned.length > 0) {
                postTags[target] = cleaned;
            }

            delete postTags[key];
            migrated += 1;
        });

        const migrateArrayState = (storageKey) => {
            const raw = localStorage.getItem(storageKey);
            if (!raw) return 0;

            let values;
            try {
                values = JSON.parse(raw);
            } catch (error) {
                return 0;
            }
            if (!Array.isArray(values)) return 0;

            let touched = 0;
            const nextValues = [];
            values.forEach(value => {
                const target = resolveLegacyKey(value);
                if (target && target !== value) touched += 1;
                nextValues.push(target || value);
            });

            const deduped = Array.from(new Set(nextValues.filter(Boolean)));
            if (touched > 0) {
                localStorage.setItem(storageKey, JSON.stringify(deduped));
            }
            return touched;
        };

        const todoPriority = { completed: 2, pending: 1 };
        const migrateTodoState = () => {
            const raw = localStorage.getItem('sns_todos');
            if (!raw) return 0;

            let values;
            try {
                values = JSON.parse(raw);
            } catch (error) {
                return 0;
            }
            if (!values || typeof values !== 'object' || Array.isArray(values)) return 0;

            let touched = 0;
            const nextValues = {};
            Object.entries(values).forEach(([key, value]) => {
                const target = resolveLegacyKey(key) || key;
                if (target !== key) touched += 1;

                const existing = nextValues[target];
                if (!existing || (todoPriority[value] || 0) >= (todoPriority[existing] || 0)) {
                    nextValues[target] = value;
                }
            });

            if (touched > 0) {
                localStorage.setItem('sns_todos', JSON.stringify(nextValues));
            }
            return touched;
        };

        const favoritesMigrated = migrateArrayState('sns_favorites');
        const invisibleMigrated = migrateArrayState('sns_invisible_posts');
        const foldedMigrated = migrateArrayState('sns_folded_posts');
        const todosMigrated = migrateTodoState();

        if (migrated > 0) {
            localStorage.setItem('sns_tags', JSON.stringify(postTags));
            syncTagsToServer();
        }

        const totalStateMigrations = favoritesMigrated + invisibleMigrated + foldedMigrated + todosMigrated;
        if (migrated > 0 || totalStateMigrations > 0) {
            console.log(
                `🔧 Migrated legacy URL states: tags=${migrated}, favorites=${favoritesMigrated}, hidden=${invisibleMigrated}, folded=${foldedMigrated}, todos=${todosMigrated}`
            );
        }

        return migrated;
    }

    function decoratePosts(posts) {
        return (posts || []).map((post) => {
            let dateStr = post.timestamp || post.created_at || post.date || post.crawled_at;
            if (dateStr && typeof dateStr === 'string' && dateStr.includes(' ') && !dateStr.includes('T')) {
                dateStr = dateStr.replace(' ', 'T');
            }
            post._dateObj = dateStr ? new Date(dateStr) : new Date(0);
            post._seqId = post.sequence_id || 0;
            return post;
        });
    }

    function getServerPlatformFilter(filter) {
        if (filter === 'x') return 'twitter';
        return ['threads', 'linkedin', 'twitter'].includes(filter) ? filter : '';
    }

    function getServerSortParam() {
        return currentSort === 'saved' ? 'sequence' : 'newest';
    }

    function getPostPreviewText(post) {
        return String(post.full_text || post.full_text_preview || '');
    }

    function getPostTextLength(post) {
        const preview = getPostPreviewText(post);
        return Number(post.full_text_length || preview.length || 0);
    }

    function getPostMediaCount(post) {
        if (Array.isArray(post.media) && post.media.length > 0) {
            return post.media.length;
        }
        return Number(post.media_count || 0);
    }

    function getBestImageSource(post, preferDetail = false) {
        const localImages = Array.isArray(post.local_images) ? post.local_images : [];
        const mediaList = Array.isArray(post.media) ? post.media : [];
        const thumbnail = post.thumbnail || '';
        const originalUrl = localImages[0] || mediaList[0] || thumbnail || '';

        if (!preferDetail && thumbnail) {
            return thumbnail;
        }
        if (!originalUrl) {
            return '';
        }
        if (localImages.length > 0) {
            return localImages[0];
        }
        if (originalUrl.includes('wsrv.nl') || originalUrl.includes('licdn.com')) {
            return originalUrl;
        }
        return `https://wsrv.nl/?url=${encodeURIComponent(originalUrl)}&output=webp`;
    }

    function mergeDetailIntoCollections(detail) {
        const collections = [allPosts, searchResults];
        collections.forEach((posts) => {
            if (!Array.isArray(posts)) return;
            const target = posts.find((post) => post.sequence_id === detail.sequence_id);
            if (target) {
                Object.assign(target, detail);
                decoratePosts([target]);
            }
        });
    }

    async function prefetchDetail(sequenceId) {
        if (!sequenceId || _postDetailCache.has(sequenceId) || _inFlightDetails.has(sequenceId)) {
            return;
        }
        _inFlightDetails.add(sequenceId);
        try {
            const response = await fetch(`/api/post/${sequenceId}`);
            if (!response.ok) {
                return;
            }
            const detail = await response.json();
            _postDetailCache.set(sequenceId, detail);
            mergeDetailIntoCollections(detail);
        } catch (error) {
            console.error('Failed to prefetch post detail:', error);
        } finally {
            _inFlightDetails.delete(sequenceId);
        }
    }

    async function ensurePostDetail(post) {
        if (!post || !post.sequence_id) {
            return post;
        }
        const cached = _postDetailCache.get(post.sequence_id);
        if (cached) {
            Object.assign(post, cached);
            decoratePosts([post]);
            return post;
        }
        await prefetchDetail(post.sequence_id);
        const detail = _postDetailCache.get(post.sequence_id);
        if (detail) {
            Object.assign(post, detail);
            decoratePosts([post]);
        }
        return post;
    }

    // --- Data Loading ---
    async function fetchData() {
        if (loadingIndicator) loadingIndicator.classList.remove('hidden');
        if (noResults) noResults.classList.add('hidden');
        if (masonryGrid) masonryGrid.innerHTML = '';

        clearTimeout(_searchTimer);
        if (_searchAbortController) {
            _searchAbortController.abort();
        }

        try {
            const params = new URLSearchParams({ sort: getServerSortParam() });
            const [postsRes, tagsRes] = await Promise.all([
                fetch(`/api/posts?${params.toString()}`),
                fetch('/api/get-tags'),
            ]);

            if (!postsRes.ok) {
                throw new Error('Failed to load /api/posts');
            }

            const data = await postsRes.json();
            const serverTags = tagsRes.ok ? await tagsRes.json() : {};

            Object.assign(postTags, serverTags);
            Object.keys(postTags).forEach((url) => {
                postTags[url] = (postTags[url] || []).filter((tag) => tag && tag.trim().length > 0);
                if (postTags[url].length === 0) {
                    delete postTags[url];
                }
            });
            localStorage.setItem('sns_tags', JSON.stringify(postTags));

            allPosts = decoratePosts(Array.isArray(data) ? data : (data.posts || []));
            searchResults = null;
            _postDetailCache.clear();
            _inFlightDetails.clear();

            migrateLegacyTagKeys(allPosts);

            if (totalPostsCount) {
                totalPostsCount.textContent = `${allPosts.length} 건`;
            }

            const activeQuery = (searchInput.value || '').trim();
            if (activeQuery) {
                searchQuery = activeQuery;
                await runServerSearch(activeQuery);
            } else {
                searchQuery = '';
                renderPosts();
            }
        } catch (error) {
            console.error('❌ Data load failed:', error);
            if (noResults) {
                noResults.innerHTML = `
                    <div class="text-center p-12">
                        <span class="material-symbols-outlined text-gray-500 text-6xl mb-4">cloud_off</span>
                        <p class="text-xl text-gray-300">데이터를 불러올 수 없습니다.</p>
                        <p class="text-sm text-gray-500 mt-2">서버가 실행 중인지 확인하세요.</p>
                    </div>
                `;
                noResults.classList.remove('hidden');
            }
        } finally {
            if (loadingIndicator) loadingIndicator.classList.add('hidden');
        }
    }

    async function runServerSearch(query) {
        const nextQuery = (query || '').trim();
        searchQuery = nextQuery;

        if (!nextQuery) {
            searchResults = null;
            renderPosts();
            return;
        }

        if (_searchAbortController) {
            _searchAbortController.abort();
        }

        const controller = new AbortController();
        _searchAbortController = controller;

        try {
            const params = new URLSearchParams({
                q: nextQuery,
                platform: getServerPlatformFilter(currentFilter),
                sort: getServerSortParam(),
                limit: '500',
            });
            const response = await fetch(`/api/search?${params.toString()}`, {
                signal: controller.signal,
            });
            if (!response.ok) {
                throw new Error(`Search request failed: ${response.status}`);
            }
            const data = await response.json();
            searchResults = decoratePosts(Array.isArray(data.posts) ? data.posts : []);
            searchResults.forEach((post) => {
                const cached = _postDetailCache.get(post.sequence_id);
                if (cached) {
                    Object.assign(post, cached);
                }
            });
            renderPosts();
        } catch (error) {
            if (error.name === 'AbortError') {
                return;
            }
            console.error('Search failed:', error);
            searchResults = [];
            renderPosts();
        } finally {
            if (_searchAbortController === controller) {
                _searchAbortController = null;
            }
        }
    }

    function getFilteredPosts() {
        const sourcePosts = searchResults ?? allPosts;
        return sourcePosts.filter((post) => {
            const postUrl = resolvePostUrl(post);
            const matchesFilter =
                currentFilter === 'all' ||
                (currentFilter === 'favorites' ? favorites.has(postUrl) :
                 currentFilter === 'todos' ? !!todos[postUrl] :
                 (post.sns_platform || '').toLowerCase() === currentFilter ||
                 (currentFilter === 'x' && (post.sns_platform === 'twitter' || post.sns_platform === 'x')));

            const matchesTag = !currentTag || (postTags[postUrl] || []).includes(currentTag);
            const matchesVisibility = !invisiblePosts.has(postUrl);

            return matchesFilter && matchesTag && matchesVisibility;
        });
    }

    function resolvePostUrl(post) {
        const normalizeThreadsUrl = (url) => {
            if (!url || typeof url !== 'string') return '';
            return url
                .replace(/^https?:\/\/www\.threads\.net\//, 'https://www.threads.com/')
                .replace(/^https?:\/\/threads\.net\//, 'https://www.threads.com/')
                .replace(/^https?:\/\/threads\.com\//, 'https://www.threads.com/');
        };

        if (post.canonical_url) {
            return normalizeThreadsUrl(post.canonical_url) || post.canonical_url;
        }
        if (post.url) {
            return normalizeThreadsUrl(post.url) || post.url;
        }
        const platform = (post.sns_platform || '').toLowerCase();
        if (platform.includes('thread')) {
            const user = post.username || post.user;
            const code = post.platform_id || post.code;
            if (user && code) return `https://www.threads.com/@${user}/post/${code}`;
            return normalizeThreadsUrl(post.post_url || post.source_url || '');
        }
        return post.post_url || post.source_url || '';
    }

    function buildCopyText(post) {
        const fullText = post.full_text || post.full_text_preview || '';
        const postUrl = resolvePostUrl(post);
        const author = post.display_name || post.username || post.user || '';
        const createdAt = (post.created_at || '').slice(0, 10);
        const platform = post.sns_platform || '';
        return `${fullText}\n\n*출처: ${postUrl}\n*${author} / ${createdAt} / ${platform}`;
    }

    function getReadMoreIndicatorHtml(isExpanded) {
        return isExpanded
            ? `<span>Show less</span><span class="material-symbols-outlined text-[14px]">expand_less</span>`
            : `<span>Read more</span><span class="material-symbols-outlined text-[14px]">expand_more</span>`;
    }

    function toggleExpandableText(paragraph, indicator) {
        if (!paragraph || !indicator) return;

        const isCollapsed = paragraph.classList.contains('line-clamp-4');
        if (isCollapsed) {
            paragraph.classList.remove('line-clamp-4');
            indicator.innerHTML = getReadMoreIndicatorHtml(true);
        } else {
            paragraph.classList.add('line-clamp-4');
            indicator.innerHTML = getReadMoreIndicatorHtml(false);
        }
    }

    function sortPosts(posts) {
        const filtered = [...posts];
        if (currentSort === 'date') {
            filtered.sort((a, b) => b._dateObj - a._dateObj);
        } else if (currentSort === 'saved') {
            filtered.sort((a, b) => b._seqId - a._seqId);
        } else if (currentSort === 'favorites') {
            filtered.sort((a, b) => {
                const aFav = favorites.has(resolvePostUrl(a));
                const bFav = favorites.has(resolvePostUrl(b));
                if (aFav && !bFav) return -1;
                if (!aFav && bFav) return 1;
                return b._dateObj - a._dateObj;
            });
        }
        return filtered;
    }

    function buildMasonryColumns() {
        columns = [];
        let colCount = 1;
        const width = window.innerWidth;
        if (width >= 1536) colCount = 4;
        else if (width >= 1024) colCount = 3;
        else if (width >= 768) colCount = 2;

        for (let i = 0; i < colCount; i += 1) {
            const colDiv = document.createElement('div');
            colDiv.className = 'masonry-col flex-1 flex flex-col gap-6 min-w-0';
            masonryGrid.appendChild(colDiv);
            columns.push(colDiv);
        }
    }

    function appendCards(batch) {
        batch.forEach((post) => {
            const card = createCard(post);
            const targetColumn = columns.reduce((best, column) => {
                if (!best) return column;
                return column.childElementCount < best.childElementCount ? column : best;
            }, null);
            if (targetColumn) {
                targetColumn.appendChild(card);
            }
        });
    }

    function ensureSentinel() {
        if (_pendingPosts.length === 0) {
            return;
        }
        if (!_ioSentinel) {
            _ioSentinel = document.createElement('div');
            _ioSentinel.className = 'load-sentinel';
            _ioSentinel.style.cssText = 'width:100%;height:1px;';
        }
        masonryGrid.appendChild(_ioSentinel);
        if (!_ioObserver) {
            _ioObserver = new IntersectionObserver((entries) => {
                if (!entries[0].isIntersecting || _pendingPosts.length === 0) {
                    return;
                }
                appendCards(_pendingPosts.splice(0, 60));
                if (_pendingPosts.length === 0 && _ioSentinel) {
                    _ioObserver.unobserve(_ioSentinel);
                    _ioSentinel.remove();
                }
            }, { rootMargin: '800px' });
        }
        _ioObserver.observe(_ioSentinel);
    }

    function renderPosts() {
        updateGlobalTags();

        const filtered = sortPosts(getFilteredPosts());

        if (_ioObserver) {
            _ioObserver.disconnect();
        }
        _ioSentinel = null;
        _pendingPosts = [];

        if (filtered.length === 0) {
            noResults.classList.remove('hidden');
            masonryGrid.innerHTML = '';
            return;
        }

        noResults.classList.add('hidden');
        masonryGrid.innerHTML = '';
        buildMasonryColumns();

        const firstBatch = filtered.slice(0, 60);
        _pendingPosts = filtered.slice(60);
        appendCards(firstBatch);
        ensureSentinel();
    }

    function createCard(post) {
        const article = document.createElement('article');
        article.className = 'glass-card rounded-2xl p-4 flex flex-col gap-3 group break-inside-avoid relative overflow-hidden transition-all duration-300';
        
        // --- URL Definition (Critical for event handlers) ---
        const postUrl = resolvePostUrl(post);
        const isFavorited = favorites.has(postUrl);
        const isFolded = foldedPosts.has(postUrl);
        if (isFolded) article.classList.add('minimized');

        // --- Platform Config ---
        const platform = (post.sns_platform || 'other').toLowerCase();
        let platformConfig = { icon: 'link', color: '#888', name: platform };
        
        if (platform.includes('thread')) {
            platformConfig = { icon: 'alternate_email', color: '#fff', name: 'Threads' };
        } else if (platform.includes('linkedin')) {
            platformConfig = { icon: 'work', color: '#0A66C2', name: 'LinkedIn' };
        } else if (platform.includes('twitter') || platform === 'x') {
            platformConfig = { icon: 'close', color: '#fff', name: 'X' }; // 'close' 아이콘을 X 대용으로 사용하거나 텍스트 처리
        }
        article.dataset.platform = platform;

        // Date Logic
        const dateObj = post._dateObj;
        const options = { year: 'numeric', month: 'numeric', day: 'numeric' };
        
        let dateLabel;
        if (post.timestamp || post.created_at) {
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
            iconHtml = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#0A66C2"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>`;
        } else if (platform.includes('twitter') || platform === 'x') {
            iconHtml = `<div class="size-5 flex items-center justify-center bg-white/10 rounded-md"><span class="text-[11px] font-black text-white">X</span></div>`;
        } else {
            iconHtml = `<span class="material-symbols-outlined text-[20px]" style="color: ${platformConfig.color}">${platformConfig.icon}</span>`;
        }

        header.innerHTML = `
            <div class="flex items-center gap-3">
                ${iconHtml}
                <div class="min-w-0">
                    <h3 class="text-sm font-semibold text-white truncate max-w-[150px]">${escapeHtml(post.display_name || post.username || post.user || 'Unknown')}</h3>
                    <p class="text-xs text-gray-400 truncate" title="${escapeHtml(post.created_at || post.crawled_at)}">
                        ${escapeHtml(dateLabel)}
                    </p>
                </div>
            </div>
            <div class="flex items-center gap-1">
                <button class="fold-btn p-1.5 rounded-lg hover:bg-white/10 text-gray-400" data-url="${escapeHtml(postUrl)}" title="${isFolded ? 'Unfold card' : 'Fold card'}">
                    <span class="material-symbols-outlined text-[20px]">
                        ${isFolded ? 'expand_more' : 'expand_less'}
                    </span>
                </button>
                <button class="invisible-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-400 hover:text-red-400" data-url="${escapeHtml(postUrl)}" title="Hide post">
                    <span class="material-symbols-outlined text-[20px]">visibility</span>
                </button>
                <button class="copy-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-400 hover:text-primary" data-url="${escapeHtml(postUrl)}" title="Copy text">
                    <span class="material-symbols-outlined text-[20px]">content_copy</span>
                </button>
                <button class="favorite-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors group/fav" data-url="${escapeHtml(postUrl)}" data-action="favorite">
                    <span class="material-symbols-outlined text-[20px] ${isFavorited ? 'text-yellow-400 fill-1' : 'text-gray-500 group-hover/fav:text-yellow-400'} transition-all">
                        ${isFavorited ? 'star' : 'star'}
                    </span>
                </button>
                <button class="todo-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors group/todo ${todos[postUrl] ? escapeHtml(todos[postUrl]) : ''}" data-url="${escapeHtml(postUrl)}" title="TODO 상태 관리">
                    <span class="material-symbols-outlined text-[20px]">
                        ${todos[postUrl] === 'pending' ? 'pending' : (todos[postUrl] === 'completed' ? 'task_alt' : 'radio_button_unchecked')}
                    </span>
                </button>
            </div>
        `;


        const todoBtn = header.querySelector('.todo-btn');
        todoBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const url = postUrl;
            const icon = todoBtn.querySelector('span');
            const currentState = todos[url];

            if (!currentState) {
                todos[url] = 'pending';
                todoBtn.classList.add('pending');
                icon.textContent = 'pending';
            } else if (currentState === 'pending') {
                todos[url] = 'completed';
                todoBtn.classList.remove('pending');
                todoBtn.classList.add('completed');
                icon.textContent = 'task_alt';
            } else {
                delete todos[url];
                todoBtn.classList.remove('completed');
                icon.textContent = 'radio_button_unchecked';
            }

            localStorage.setItem('sns_todos', JSON.stringify(todos));

            if (currentFilter === 'todos' && !todos[url]) {
                article.style.opacity = '0';
                article.style.transform = 'scale(0.9)';
                setTimeout(() => renderPosts(), 200);
            }
        });

        const favBtn = header.querySelector('.favorite-btn');
        favBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const url = postUrl;
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
            const icon = copyBtn.querySelector('span');

            try {
                const detailedPost = await ensurePostDetail(post);
                const textToCopy = buildCopyText(detailedPost);
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

        const previewText = getPostPreviewText(post);
        const cleanText = escapeHtml(previewText).replace(/\n/g, '<br>');
        const isLongText = getPostTextLength(post) > 150 || getPostTextLength(post) > previewText.length;

        content.innerHTML = `
            <div class="relative">
                <p class="text-sm text-gray-200 leading-relaxed font-light ${isLongText ? 'line-clamp-4' : ''} transition-all" id="text-${escapeHtml(postUrl)}">
                    ${cleanText}
                </p>
                ${isLongText ? `
                <div class="mt-2 text-xs font-medium text-gray-500 transition-colors flex items-center gap-1 read-more-indicator cursor-pointer">
                    ${getReadMoreIndicatorHtml(false)}
                </div>` : ''}
            </div>
        `;

        if (isLongText) {
            const paragraph = content.querySelector('p');
            const indicator = content.querySelector('.read-more-indicator');
            if (indicator) {
                indicator.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (!post.full_text && post.sequence_id) {
                        const detailedPost = await ensurePostDetail(post);
                        const detailedText = escapeHtml(getPostPreviewText(detailedPost)).replace(/\n/g, '<br>');
                        paragraph.innerHTML = detailedText;
                    }
                    toggleExpandableText(paragraph, indicator);
                });
            }
        }

        // --- Images ---
        let imageDiv = null;
        const previewImgUrl = getBestImageSource(post);
        const mediaCount = getPostMediaCount(post);
        if (previewImgUrl) {
            const isVideo = previewImgUrl.toLowerCase().includes('.mp4');
            const moreCount = Math.max(0, mediaCount - 1);

            imageDiv = document.createElement('div');
            imageDiv.className = 'rounded-xl overflow-hidden relative group/image mt-2 border border-white/5 bg-black/20';
            if (isFolded) imageDiv.classList.add('hidden-content');
            
            if (isVideo) {
                // Placeholder for video posts
                imageDiv.innerHTML = `
                    <div class="video-placeholder w-full min-h-[200px] flex flex-col items-center justify-center bg-black/40 cursor-pointer py-10">
                        <span class="material-symbols-outlined text-4xl text-white/50 mb-2">play_circle</span>
                        <span class="text-xs text-white/40">Video Post (Click to view)</span>
                    </div>
                `;
                imageDiv.querySelector('.video-placeholder').addEventListener('click', () => {
                    window.open(postUrl, '_blank');
                });
            } else {
                const placeholderImg = "https://placehold.co/400x300/222/555?text=Image+Unavailable";
                imageDiv.innerHTML = `
                    <img class="w-full h-auto max-h-[600px] object-contain cursor-zoom-in transition-transform duration-500 group-hover/image:scale-105"
                         alt="SNS Post Image">
                    ${moreCount > 0 ? `
                    <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-xs text-white flex items-center gap-1 pointer-events-none">
                        <span class="material-symbols-outlined text-[12px]">filter</span>
                        +${moreCount}
                    </div>` : ''}
                `;

                // Set img attributes safely via DOM API (avoid inline onerror/XSS)
                const imgEl = imageDiv.querySelector('img');
                if (imgEl) {
                    imgEl.loading = 'lazy';
                    imgEl.decoding = 'async';
                    imgEl.src = previewImgUrl;
                    imgEl.dataset.src = previewImgUrl;
                    imgEl.dataset.original = previewImgUrl;
                    imgEl.dataset.caption = `${post.display_name || post.username || 'Unknown'}: ${getPostPreviewText(post).slice(0, 50)}...`;

                    // onerror fallback chain via addEventListener
                    const handleImgError = function() {
                        if (this.src !== this.dataset.original) {
                            this.src = this.dataset.original;
                        } else {
                            this.src = placeholderImg;
                            this.removeEventListener('error', handleImgError);
                        }
                    };
                    imgEl.addEventListener('error', handleImgError);

                    // Image click handler (only for actual images)
                    imgEl.addEventListener('click', async (e) => {
                        const detailedPost = await ensurePostDetail(post);
                        const modalSrc = getBestImageSource(detailedPost, true) || e.target.dataset.src;
                        e.target.dataset.src = modalSrc;
                        e.target.dataset.original = modalSrc;
                        e.target.dataset.caption = `${post.display_name || post.username || 'Unknown'}: ${getPostPreviewText(detailedPost).slice(0, 50)}...`;
                        showModal(modalSrc, e.target.dataset.caption);
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
                const isPrimary = tagTypes[tag] === 'primary';
                tagChip.className = `tag-chip ${isPrimary ? 'primary' : ''}`;
                tagChip.innerHTML = `
                    <span>${escapeHtml(tag)}</span>
                    <span class="tag-remove material-symbols-outlined text-[12px]" data-tag="${escapeHtml(tag)}">close</span>
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
            <a href="${escapeHtml(postUrl || '#')}" target="_blank" class="flex items-center gap-1 hover:text-primary transition-colors ml-auto">
                <span>View Original</span>
                <span class="material-symbols-outlined text-[16px]">open_in_new</span>
            </a>
        `;
        article.appendChild(footer);

        // *** Fold Toggle Handler ***
        const foldBtn = header.querySelector('.fold-btn');
        foldBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const url = postUrl;
            
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

        article.addEventListener('mouseenter', () => {
            void prefetchDetail(post.sequence_id);
        }, { once: true });

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
            const isPrimary = tagTypes[tag] === 'primary';
            tagBtn.className = `global-tag-chip ${currentTag === tag ? 'active' : ''} ${isPrimary ? 'primary' : ''}`;
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
            const response = await fetch('/api/save-tags', {
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
        renderTagManagementList();
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
        if (targetId === 'tabTags') {
            renderTagManagementList();
        }
    }

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.target));
    });

    const tagSearchInput = document.getElementById('tagSearchInput');
    if (tagSearchInput) {
        tagSearchInput.addEventListener('input', () => renderTagManagementList());
    }

    function renderTagManagementList() {
        const listContainer = document.getElementById('tagManagementList');
        const noTagsFound = document.getElementById('noTagsFound');
        const query = (document.getElementById('tagSearchInput')?.value || '').toLowerCase();
        
        if (!listContainer) return;
        
        // Get all unique tags from system
        const allUniqueTags = new Set();
        Object.values(postTags).forEach(tags => tags.forEach(tag => allUniqueTags.add(tag)));
        
        const filteredTags = Array.from(allUniqueTags)
            .filter(tag => tag.toLowerCase().includes(query))
            .sort();

        listContainer.innerHTML = '';
        
        if (filteredTags.length === 0) {
            noTagsFound.classList.remove('hidden');
            return;
        }
        
        noTagsFound.classList.add('hidden');

        filteredTags.forEach(tag => {
            const isPrimary = tagTypes[tag] === 'primary';
            const item = document.createElement('div');
            item.className = 'tag-manage-item';
            
            item.innerHTML = `
                <div class="flex items-center gap-3">
                    <span class="text-sm font-medium text-white">${escapeHtml(tag)}</span>
                    ${isPrimary ? `<span class="px-2 py-0.5 rounded bg-primary/20 text-primary text-[10px] font-bold border border-primary/20 uppercase">Primary</span>` : ''}
                </div>
                <div class="flex items-center gap-3">
                    <span class="text-[11px] text-gray-500">${isPrimary ? '강조 해제' : '강조 표시'}</span>
                    <label class="toggle-switch">
                        <input type="checkbox" ${isPrimary ? 'checked' : ''} data-tag="${escapeHtml(tag)}">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            `;
            
            const checkbox = item.querySelector('input');
            checkbox.addEventListener('change', (e) => {
                const tagName = e.target.dataset.tag;
                if (e.target.checked) {
                    tagTypes[tagName] = 'primary';
                } else {
                    delete tagTypes[tagName];
                }
                localStorage.setItem('sns_tag_types', JSON.stringify(tagTypes));
                
                // Real-time update
                renderTagManagementList();
                renderPosts();
            });
            
            listContainer.appendChild(item);
        });
    }

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

        const hiddenItems = allPosts.filter(post => invisiblePosts.has(resolvePostUrl(post)));
        hiddenItems.forEach(post => {
            const resolvedUrl = resolvePostUrl(post);
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
                    <h4 class="truncate">${escapeHtml(post.display_name || post.username || post.user || 'Unknown')}</h4>
                    <p class="truncate text-xs opacity-60">${escapeHtml((getPostPreviewText(post) || 'No content').slice(0, 100))}</p>
                </div>
                <button class="restore-btn hover:scale-105 active:scale-95 transition-all shrink-0" data-url="${escapeHtml(resolvedUrl)}">
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
                    <span class="text-sm font-medium text-white">${escapeHtml(rule.keyword)}</span>

                    ${isManual ? `
                    <span class="material-symbols-outlined text-gray-600 text-sm">arrow_forward</span>
                    <div class="px-2 py-0.5 rounded bg-green-900/30 text-green-400 text-[10px] font-bold border border-green-500/20">Tag</div>
                    <span class="text-sm font-medium text-white">${escapeHtml(rule.tag)}</span>
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
                div.querySelector('.delete-rule-btn').addEventListener('click', async () => {
                    manualRules.splice(rule.index, 1);
                    localStorage.setItem('sns_auto_tag_rules', JSON.stringify(manualRules));
                    renderAutoTagRules();
                    await applyAutoTagRules();
                });
            }
            container.appendChild(div);
        });
    }

    // Add Rule
    document.getElementById('addAutoTagRuleBtn').addEventListener('click', async () => {
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
        await applyAutoTagRules();
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
        
        try {
            const { matchedPostCount, ruleCount } = await applyAutoTagRules();

            progressBar.style.width = '100%';
            progressPercent.textContent = '100%';

            resultMessage.textContent = matchedPostCount > 0
                ? `완료! ${matchedPostCount}개 게시물에 자동 태그를 적용했습니다. (규칙: ${ruleCount})`
                : `완료! 새로 적용된 자동 태그가 없습니다. (규칙: ${ruleCount})`;
            resultMessage.classList.remove('hidden');
        } catch (error) {
            console.error('Failed to run batch auto tag:', error);
            resultMessage.textContent = '자동 태그 적용 중 오류가 발생했습니다.';
            resultMessage.classList.remove('hidden');
        } finally {
            setTimeout(() => {
                btn.disabled = false;
            }, 500);
        }
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
