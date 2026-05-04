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

function isSafeHttpUrl(url) {
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
        return false;
    }
}

function splitUrlTrailingPunctuation(url) {
    let cleanUrl = url;
    let trailing = '';

    while (/[.,!?;:\])}]$/.test(cleanUrl)) {
        trailing = cleanUrl.slice(-1) + trailing;
        cleanUrl = cleanUrl.slice(0, -1);
    }

    return { cleanUrl, trailing };
}

function linkifyText(str, options = {}) {
    if (str == null) return '';

    const text = String(str);
    const isTruncated = Boolean(options.isTruncated);
    const urlPattern = /https?:\/\/[^\s<>"']+/gi;
    let html = '';
    let lastIndex = 0;
    let match;

    while ((match = urlPattern.exec(text)) !== null) {
        const rawUrl = match[0];
        const start = match.index;
        const { cleanUrl, trailing } = splitUrlTrailingPunctuation(rawUrl);
        const rawEnd = start + rawUrl.length;
        const urlTouchesTruncatedTail = isTruncated && rawEnd === text.length;

        html += escapeHtml(text.slice(lastIndex, start));

        if (!cleanUrl || urlTouchesTruncatedTail || !isSafeHttpUrl(cleanUrl)) {
            html += escapeHtml(cleanUrl);
        } else {
            const escapedUrl = escapeHtml(cleanUrl);
            html += `<a href="${escapedUrl}" target="_blank" rel="noopener noreferrer" class="inline-post-link">${escapedUrl}</a>`;
        }

        html += escapeHtml(trailing);
        lastIndex = rawEnd;
    }

    html += escapeHtml(text.slice(lastIndex));
    return html.replace(/\n/g, '<br>');
}

function createScrapRunId() {
    const randomPart = window.crypto?.getRandomValues
        ? Array.from(window.crypto.getRandomValues(new Uint32Array(2)))
            .map(value => value.toString(36))
            .join('')
        : Math.random().toString(36).slice(2);
    return `scrap-${Date.now().toString(36)}-${randomPart}`.slice(0, 64);
}

function isScrapProgressEventLoggable(event) {
    return Boolean(event && String(event.message || '').trim());
}

function buildScrapProgressConsoleMessage(event) {
    return `[SNS Scrap] ${String(event.message || '').trim()}`;
}

document.addEventListener('DOMContentLoaded', () => {
    // const feedJsonPath = 'output_total/total_full_20260201.json'; // ❌ 삭제됨 (동적 로딩으로 변경)
    const masonryGrid = document.getElementById('masonryGrid');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const noResults = document.getElementById('noResults');
    const totalPostsCount = document.getElementById('totalPostsCount');
    const searchInput = document.getElementById('searchInput');
    const filterContainer = document.getElementById('filterContainer');

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
    const scrapResultModal = document.getElementById('scrapResultModal');
    const scrapResultTitle = document.getElementById('scrapResultTitle');
    const scrapResultSubtitle = document.getElementById('scrapResultSubtitle');
    const scrapResultBody = document.getElementById('scrapResultBody');
    const closeScrapResultModalBtn = document.getElementById('closeScrapResultModal');
    const confirmScrapResultModalBtn = document.getElementById('confirmScrapResultModal');
    const copyAuthRenewalPromptBtn = document.getElementById('copyAuthRenewalPromptBtn');
    const bulkActionBar = document.getElementById('bulkActionBar');
    const bulkSelectedCount = document.getElementById('bulkSelectedCount');
    const bulkHideBtn = document.getElementById('bulkHideBtn');
    const bulkFavoriteBtn = document.getElementById('bulkFavoriteBtn');
    const bulkCopyBtn = document.getElementById('bulkCopyBtn');
    const bulkClearBtn = document.getElementById('bulkClearBtn');

    let allPosts = [];
    let searchResults = null;
    let currentFilter = 'all';
    let searchQuery = '';
    const selectedPosts = new Set();
    let _searchTimer = null;
    let _searchAbortController = null;
    let _pendingPosts = [];
    let _ioObserver = null;
    let _ioSentinel = null;
    let columns = [];
    let currentAuthRenewalPrompt = '';
    let currentSort = localStorage.getItem('sns_sort_order') || 'date'; // Persist sort order
    const _postDetailCache = new Map();
    const _inFlightDetails = new Set();

    // Load states from localStorage
    const favorites = new Set(JSON.parse(localStorage.getItem('sns_favorites') || '[]'));
    const invisiblePosts = new Set(JSON.parse(localStorage.getItem('sns_invisible_posts') || '[]'));
    const foldedPosts = new Set(JSON.parse(localStorage.getItem('sns_folded_posts') || '[]'));
    const postTags = JSON.parse(localStorage.getItem('sns_tags') || '{}');
    const tagTypes = JSON.parse(localStorage.getItem('sns_tag_types') || '{}');
    // Legacy TODO state is kept for URL migration/backward compatibility.
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
        clearSelection();
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

        clearSelection();
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
            clearSelection();
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

    if (bulkClearBtn) {
        bulkClearBtn.addEventListener('click', () => {
            clearSelection();
        });
    }

    if (bulkFavoriteBtn) {
        bulkFavoriteBtn.addEventListener('click', () => {
            const selected = getCurrentSelectedPosts();
            if (selected.length === 0) {
                clearSelection();
                return;
            }

            addSelectedUrlsToSet(favorites, getPostUrls(selected));
            localStorage.setItem('sns_favorites', JSON.stringify([...favorites]));
            updateGlobalTags();
            renderPosts();
        });
    }

    if (bulkHideBtn) {
        bulkHideBtn.addEventListener('click', () => {
            const selected = getCurrentSelectedPosts();
            if (selected.length === 0) {
                clearSelection();
                return;
            }

            if (!confirm(`선택한 ${selected.length}개 게시글을 피드에서 숨기시겠습니까?`)) {
                return;
            }

            addSelectedUrlsToSet(invisiblePosts, getPostUrls(selected));
            localStorage.setItem('sns_invisible_posts', JSON.stringify([...invisiblePosts]));
            clearSelection();
            renderPosts();
        });
    }

    if (bulkCopyBtn) {
        bulkCopyBtn.addEventListener('click', async () => {
            const selected = getCurrentSelectedPosts();
            if (selected.length === 0) {
                clearSelection();
                return;
            }

            const label = bulkCopyBtn.querySelector('span:last-child');
            const originalLabel = label ? label.textContent : '';
            try {
                const detailedPosts = await Promise.all(selected.map((post) => ensurePostDetail(post)));
                await navigator.clipboard.writeText(buildBulkCopyText(detailedPosts));
                if (label) label.textContent = '복사됨';
                setTimeout(() => {
                    if (label) label.textContent = originalLabel || '복사';
                }, 2000);
            } catch (err) {
                console.error('Failed to copy selected posts: ', err);
                alert('선택한 게시글 복사에 실패했습니다.');
                if (label) label.textContent = originalLabel || '복사';
            }
        });
    }

    // Run Scraper functionality
    const runScrapBtn = document.getElementById('runScrapBtn');
    const runFullScrapBtn = document.getElementById('runFullScrapBtn');
    let scrapRunInProgress = false;
    let scrapProgressTimer = null;
    let scrapProgressLastSeq = 0;
    let currentScrapRunId = '';
    let authRequiredPanel = null;
    const authRenewalState = {};
    const authStatusTimers = new Map();
    const AUTH_STATUS_POLL_INTERVAL_MS = 1500;
    const AUTH_STATUS_MAX_POLLS = 40;

    const authPlatformLabels = {
        linkedin: 'LinkedIn',
        threads: 'Threads',
        x: 'X'
    };

    function normalizeAuthPlatform(platform) {
        const value = String(platform || '').toLowerCase().trim();
        if (value === 'twitter' || value === 'tweet' || value === 'x/twitter' || value === 'x_twitter') return 'x';
        if (value === 'linkedin' || value === 'threads' || value === 'x') return value;
        return '';
    }

    function getAuthRequiredPlatforms(result) {
        const platforms = new Set();
        const authRequired = result?.auth_required;

        if (Array.isArray(authRequired)) {
            authRequired.forEach(platform => {
                const normalized = normalizeAuthPlatform(platform);
                if (normalized) platforms.add(normalized);
            });
        } else if (authRequired && typeof authRequired === 'object') {
            Object.entries(authRequired).forEach(([platform, required]) => {
                const normalized = normalizeAuthPlatform(platform);
                if (normalized && required) platforms.add(normalized);
            });
        } else if (typeof authRequired === 'string') {
            const normalized = normalizeAuthPlatform(authRequired);
            if (normalized) platforms.add(normalized);
        }

        Object.entries(result?.platform_results || {}).forEach(([platform, platformResult]) => {
            const normalized = normalizeAuthPlatform(platform);
            const status = String(platformResult?.status || platformResult?.result || '').toLowerCase();
            if (normalized && (platformResult?.auth_required || status.includes('auth'))) {
                platforms.add(normalized);
            }
        });

        return [...platforms].filter(platform => Object.prototype.hasOwnProperty.call(authPlatformLabels, platform));
    }

    function getFailedPlatforms(result) {
        const platforms = new Set();

        Object.entries(result?.platform_results || {}).forEach(([platform, platformResult]) => {
            const normalized = normalizeAuthPlatform(platform);
            const status = String(platformResult?.status || platformResult?.result || '').toLowerCase();
            if (normalized && status === 'failed') {
                platforms.add(normalized);
            }
        });

        return [...platforms].filter(platform => Object.prototype.hasOwnProperty.call(authPlatformLabels, platform));
    }

    function getScrapStats(result) {
        return {
            total: Number(result?.stats?.total || 0),
            threads: Number(result?.stats?.threads || 0),
            linkedin: Number(result?.stats?.linkedin || 0),
            twitter: Number(result?.stats?.twitter || 0),
            total_count: Number(result?.stats?.total_count || 0),
            threads_count: Number(result?.stats?.threads_count || 0),
            linkedin_count: Number(result?.stats?.linkedin_count || 0),
            twitter_count: Number(result?.stats?.twitter_count || 0)
        };
    }

    function buildAuthRenewalPrompt(platforms) {
        const labels = platforms
            .map(platform => authPlatformLabels[platform] || platform)
            .filter(Boolean)
            .join(', ');

        return [
            `D:\\vibe-coding\\scrap_sns 프로젝트에서 ${labels} 인증 세션을 수동 갱신하려고 합니다.`,
            '앱의 로그인 열기 버튼이나 자동화 브라우저 로그인은 사용하지 마세요.',
            '먼저 README.md의 인증 갱신 섹션과 utils/auth_paths.py, scripts/auth_runtime/renew.py의 현재 인증 경로를 확인한 뒤,',
            '현재 구조에 맞는 수동 갱신 절차를 안내하고 완료 후 세션 유효성 검증까지 진행해 주세요.'
        ].join('\n');
    }

    function buildScrapResultViewModel(result, mode) {
        const stats = getScrapStats(result);
        const authPlatforms = getAuthRequiredPlatforms(result);
        const failedPlatforms = getFailedPlatforms(result)
            .filter(platform => !authPlatforms.includes(platform));
        const consistencyCheck = result?.consistency_check || null;
        const consistencyStatus = consistencyCheck?.status || '';
        const shouldShowConsistency = ['failed', 'warning', 'timeout'].includes(consistencyStatus);
        const consistencyRows = shouldShowConsistency && Array.isArray(consistencyCheck?.steps)
            ? consistencyCheck.steps.map(step => ({
                label: step.label || step.key || '',
                status: step.status || 'skipped',
                detail: step.detail || ''
            }))
            : [];
        const needsConsistencyReview = shouldShowConsistency;

        const rows = mode === 'all'
            ? [
                { label: 'Threads', delta: `${stats.threads_count}건`, total: '전체 재수집' },
                { label: 'LinkedIn', delta: `${stats.linkedin_count}건`, total: '전체 재수집' },
                { label: 'X', delta: `${stats.twitter_count}건`, total: '전체 재수집' }
            ]
            : [
                { label: 'Threads', delta: `${stats.threads}건 추가`, total: `전체 ${stats.threads_count}건` },
                { label: 'LinkedIn', delta: `${stats.linkedin}건 추가`, total: `전체 ${stats.linkedin_count}건` },
                { label: 'X', delta: `${stats.twitter}건 추가`, total: `전체 ${stats.twitter_count}건` }
            ];

        return {
            title: needsConsistencyReview
                ? (mode === 'all' ? '전체 재수집 확인 필요' : '업데이트 확인 필요')
                : (mode === 'all' ? '전체 재수집 완료' : '업데이트 완료'),
            totalLine: mode === 'all'
                ? `전체 ${stats.total_count}건`
                : `총 ${stats.total}건 신규 추가 · 전체 ${stats.total_count}건`,
            rows,
            authPlatforms,
            authLabels: authPlatforms.map(platform => authPlatformLabels[platform] || platform),
            failedLabels: failedPlatforms.map(platform => authPlatformLabels[platform] || platform),
            authPrompt: authPlatforms.length > 0 ? buildAuthRenewalPrompt(authPlatforms) : '',
            consistencyTitle: consistencyRows.length > 0 ? '정합성 확인' : '',
            consistencyStatus,
            consistencyRows
        };
    }

    function hideScrapResultModal() {
        if (!scrapResultModal) return;
        scrapResultModal.classList.remove('show');
        document.body.classList.remove('modal-open');
        window.setTimeout(() => {
            scrapResultModal.classList.add('hidden');
            currentAuthRenewalPrompt = '';
        }, 300);
    }

    function renderScrapResultModal(model) {
        if (!scrapResultTitle || !scrapResultSubtitle || !scrapResultBody) return;

        scrapResultTitle.textContent = model.title;
        scrapResultSubtitle.textContent = model.totalLine;
        currentAuthRenewalPrompt = model.authPrompt;

        const rowsHtml = model.rows.map(row => `
            <div class="scrap-result-row">
                <span class="text-sm font-semibold text-white">${escapeHtml(row.label)}</span>
                <span class="text-sm text-gray-200">${escapeHtml(row.delta)}</span>
                <span class="text-xs text-gray-500">${escapeHtml(row.total)}</span>
            </div>
        `).join('');

        const failedHtml = model.failedLabels.length > 0
            ? `
                <div class="mt-5 rounded-lg border border-red-400/20 bg-red-400/5 px-4 py-3">
                    <p class="text-sm font-semibold text-red-200">수집 실패</p>
                    <p class="text-xs text-gray-400 mt-1">${escapeHtml(model.failedLabels.join(', '))} 수집은 실패해 최신 보유 데이터 기준으로 유지되었을 수 있습니다.</p>
                </div>
            `
            : '';

        const consistencyHtml = model.consistencyRows.length > 0
            ? `
                <section class="mt-5">
                    <div class="flex items-center justify-between mb-2">
                        <p class="text-sm font-semibold text-white">${escapeHtml(model.consistencyTitle)}</p>
                        <span class="text-xs text-gray-400">${escapeHtml(model.consistencyStatus || '확인')}</span>
                    </div>
                    <div class="rounded-lg border border-white/10 bg-black/15 px-4 py-2">
                        ${model.consistencyRows.map(row => {
                            const statusLabel = row.status === 'passed'
                                ? '통과'
                                : (row.status === 'failed' ? '실패' : (row.status === 'warning' ? '확인 필요' : '건너뜀'));
                            const statusClass = row.status === 'passed'
                                ? 'text-green-400'
                                : (row.status === 'failed' ? 'text-red-300' : 'text-amber-200');
                            return `
                                <div class="scrap-result-row">
                                    <span class="text-sm font-semibold text-white">${escapeHtml(row.label)}</span>
                                    <span class="text-xs ${statusClass}">${escapeHtml(statusLabel)}</span>
                                    <span class="text-xs text-gray-500">${escapeHtml(row.detail)}</span>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </section>
            `
            : '';

        const authHtml = model.authLabels.length > 0
            ? `
                <div class="mt-5 rounded-lg border border-amber-400/20 bg-amber-400/5 px-4 py-3">
                    <p class="text-sm font-semibold text-amber-100">인증 갱신 필요</p>
                    <p class="text-xs text-gray-300 mt-2 leading-relaxed">
                        ${escapeHtml(model.authLabels.join(', '))} 로그인 세션이 만료된 것으로 보입니다.
                        앱에서 여는 로그인 창은 자동화 브라우저로 감지되어 로그인에 실패할 수 있습니다.
                    </p>
                    <p class="text-xs text-gray-400 mt-3">아래 프롬프트를 입력하고 갱신하세요.</p>
                    <pre class="scrap-auth-prompt mt-3 rounded-lg border border-white/10 bg-black/30 px-3 py-3 text-xs text-gray-200 leading-relaxed">${escapeHtml(model.authPrompt)}</pre>
                </div>
            `
            : '';

        scrapResultBody.innerHTML = `
            <section>
                <div class="rounded-lg border border-white/10 bg-black/15 px-4 py-2">
                    ${rowsHtml}
                </div>
            </section>
            ${consistencyHtml}
            ${failedHtml}
            ${authHtml}
        `;

        if (copyAuthRenewalPromptBtn) {
            copyAuthRenewalPromptBtn.classList.toggle('hidden', model.authLabels.length === 0);
        }
    }

    function showScrapResultModal(result, mode) {
        if (!scrapResultModal) return;
        const model = buildScrapResultViewModel(result, mode);
        renderScrapResultModal(model);
        scrapResultModal.classList.remove('hidden');
        window.setTimeout(() => {
            scrapResultModal.classList.add('show');
            document.body.classList.add('modal-open');
        }, 10);
    }

    function isLocalAuthPanelVerifyAllowed() {
        const host = window.location.hostname;
        return host === '127.0.0.1' || host === 'localhost' || host === '::1' || host === '';
    }

    function getAuthPanelVerifyPlatforms() {
        if (!isLocalAuthPanelVerifyAllowed()) return [];

        const raw = new URLSearchParams(window.location.search).get('verify_auth_panel');
        if (!raw) return [];
        if (raw === '1' || raw.toLowerCase() === 'true') return ['linkedin'];

        return raw
            .split(/[,\s]+/)
            .map(normalizeAuthPlatform)
            .filter(platform => Object.prototype.hasOwnProperty.call(authPlatformLabels, platform));
    }

    function ensureAuthRequiredPanel() {
        if (authRequiredPanel) return authRequiredPanel;

        authRequiredPanel = document.createElement('div');
        authRequiredPanel.id = 'authRequiredPanel';
        authRequiredPanel.className = [
            'hidden w-full border-t border-amber-400/20 bg-[#141417]/95',
            'shadow-lg shadow-black/10'
        ].join(' ');

        const header = document.querySelector('header');
        if (header) {
            header.appendChild(authRequiredPanel);
        }

        return authRequiredPanel;
    }

    function clearAuthStatusTimer(platform) {
        const timer = authStatusTimers.get(platform);
        if (timer) {
            window.clearTimeout(timer);
            authStatusTimers.delete(platform);
        }
    }

    function resetAuthRenewalState() {
        Object.keys(authRenewalState).forEach(platform => {
            clearAuthStatusTimer(platform);
            delete authRenewalState[platform];
        });
    }

    function hideAuthRequiredPanel() {
        if (!authRequiredPanel) return;
        resetAuthRenewalState();
        authRequiredPanel.classList.add('hidden');
        authRequiredPanel.innerHTML = '';
    }

    function removeAuthPlatform(platform) {
        clearAuthStatusTimer(platform);
        delete authRenewalState[platform];
        renderAuthRequiredPanel();
    }

    function updateAuthPlatformState(platform, patch) {
        authRenewalState[platform] = {
            status: 'required',
            sessionId: '',
            message: '인증 갱신이 필요합니다.',
            pollCount: 0,
            ...(authRenewalState[platform] || {}),
            ...patch
        };
        renderAuthRequiredPanel();
    }

    function jobFromAuthResult(result) {
        return result?.job || {};
    }

    function authStatusMessage(platform, state) {
        if (state.message) return state.message;
        if (state.status === 'starting') return '로그인 창을 여는 중입니다.';
        if (state.status === 'waiting') return '브라우저에서 로그인한 뒤 완료 확인을 누르세요.';
        if (state.status === 'complete_requested') return '인증 저장 여부를 확인하는 중입니다.';
        if (state.status === 'failed') return '확인에 실패했습니다. 다시 시도하세요.';
        return `${authPlatformLabels[platform]} 인증이 필요합니다.`;
    }

    function renderAuthRequiredPanel() {
        const platforms = Object.keys(authRenewalState);
        if (!authRequiredPanel || platforms.length === 0) {
            if (authRequiredPanel) {
                authRequiredPanel.classList.add('hidden');
                authRequiredPanel.innerHTML = '';
            }
            return;
        }

        const panel = ensureAuthRequiredPanel();
        panel.innerHTML = `
            <div class="max-w-[1800px] mx-auto px-6 py-3">
                <div class="rounded-xl border border-amber-400/20 bg-amber-400/5 px-4 py-3">
                    <div class="flex items-start justify-between gap-3 mb-3">
                        <div class="flex items-start gap-3 min-w-0">
                            <span class="material-symbols-outlined text-[20px] text-amber-300 shrink-0">lock</span>
                            <div class="min-w-0">
                                <p class="text-sm font-semibold text-white leading-tight">로그인이 필요합니다</p>
                                <p class="text-xs text-gray-400 mt-1 leading-snug">플랫폼 인증을 갱신하면 자동으로 완료 여부를 확인합니다.</p>
                            </div>
                        </div>
                        <button
                            type="button"
                            class="auth-panel-close shrink-0 size-8 rounded-lg border border-white/10 bg-white/5 text-gray-300 hover:text-white hover:bg-white/10"
                            data-auth-action="close-panel"
                            title="닫기"
                        >
                            <span class="material-symbols-outlined text-[18px]">close</span>
                        </button>
                    </div>
                    <div class="flex flex-col gap-2">
                        ${platforms.map(platform => {
                            const state = authRenewalState[platform];
                            const startDisabled = ['starting', 'waiting', 'complete_requested'].includes(state.status);
                            const completeDisabled = !state.sessionId || ['starting', 'complete_requested'].includes(state.status);
                            const startLabel = state.status === 'starting' ? '여는 중' : '로그인 열기';
                            const completeLabel = state.status === 'complete_requested' ? '확인 중' : '완료 확인';
                            const rowTone = state.status === 'failed' ? 'border-red-400/30 bg-red-400/5' : 'border-white/10 bg-black/15';
                            return `
                                <div class="flex flex-col md:flex-row md:items-center gap-3 rounded-lg border ${rowTone} px-3 py-2" data-auth-platform="${platform}">
                                    <div class="min-w-0 flex-1">
                                        <p class="text-sm font-semibold text-white leading-tight">${authPlatformLabels[platform]}</p>
                                        <p class="text-xs text-gray-400 leading-snug mt-1">${authStatusMessage(platform, state)}</p>
                                    </div>
                                    <div class="flex items-center gap-2 shrink-0">
                                        <button
                                            type="button"
                                            class="auth-action-btn px-3 py-2 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-xs text-white whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
                                            data-auth-action="start"
                                            data-platform="${platform}"
                                            ${startDisabled ? 'disabled' : ''}
                                        >${startLabel}</button>
                                        <button
                                            type="button"
                                            class="auth-action-btn px-3 py-2 rounded-lg bg-primary hover:bg-primary-hover text-xs text-white whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
                                            data-auth-action="complete"
                                            data-platform="${platform}"
                                            ${completeDisabled ? 'disabled' : ''}
                                        >${completeLabel}</button>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            </div>
        `;
        panel.classList.remove('hidden');
    }

    async function pollAuthStatus(platform) {
        const state = authRenewalState[platform];
        if (!state?.sessionId) return;

        try {
            const response = await fetch(`/api/auth/status?session_id=${encodeURIComponent(state.sessionId)}`);
            const result = await response.json().catch(() => ({}));
            const job = jobFromAuthResult(result);

            if (response.ok && job.status === 'completed' && job.return_code === 0) {
                removeAuthPlatform(platform);
                return;
            }

            if (!response.ok || job.status === 'failed' || job.status === 'not_found') {
                updateAuthPlatformState(platform, {
                    status: 'failed',
                    message: '인증 저장 확인에 실패했습니다. 다시 시도하세요.'
                });
                return;
            }

            const nextCount = (state.pollCount || 0) + 1;
            if (nextCount >= AUTH_STATUS_MAX_POLLS) {
                updateAuthPlatformState(platform, {
                    status: 'failed',
                    message: '확인 시간이 초과되었습니다. 다시 완료 확인을 눌러주세요.',
                    pollCount: nextCount
                });
                return;
            }

            authRenewalState[platform] = {
                ...state,
                pollCount: nextCount
            };
            clearAuthStatusTimer(platform);
            authStatusTimers.set(platform, window.setTimeout(() => {
                void pollAuthStatus(platform);
            }, AUTH_STATUS_POLL_INTERVAL_MS));
        } catch (error) {
            console.error('Auth Status Error:', error);
            updateAuthPlatformState(platform, {
                status: 'failed',
                message: '인증 상태 확인 중 통신 오류가 발생했습니다.'
            });
        }
    }

    async function postAuthAction(platform, action) {
        const endpoint = action === 'start' ? '/api/auth/start' : '/api/auth/complete';
        const current = authRenewalState[platform] || {};
        const payload = { platform };
        if (current.sessionId) {
            payload.session_id = current.sessionId;
        }

        updateAuthPlatformState(platform, {
            status: action === 'start' ? 'starting' : 'complete_requested',
            message: action === 'start' ? '로그인 창을 여는 중입니다.' : '인증 저장 여부를 확인하는 중입니다.'
        });

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json().catch(() => ({}));

            if ((!response.ok || result.status === 'error') && response.status !== 409) {
                updateAuthPlatformState(platform, {
                    status: 'failed',
                    message: result.message || '인증 요청에 실패했습니다.'
                });
                return;
            }

            const job = jobFromAuthResult(result);
            const sessionId = job.session_id || current.sessionId || '';

            if (action === 'start') {
                updateAuthPlatformState(platform, {
                    status: 'waiting',
                    sessionId,
                    message: '브라우저에서 로그인한 뒤 완료 확인을 누르세요.'
                });
                return;
            }

            updateAuthPlatformState(platform, {
                status: 'complete_requested',
                sessionId,
                message: '인증 저장 여부를 확인하는 중입니다.',
                pollCount: 0
            });
            clearAuthStatusTimer(platform);
            void pollAuthStatus(platform);
        } catch (error) {
            console.error('Auth Error:', error);
            updateAuthPlatformState(platform, {
                status: 'failed',
                message: '인증 서버와 통신 중 오류가 발생했습니다.'
            });
        }
    }

    function handleVerifyAuthAction(platform, action) {
        const sessionId = `verify-${platform}`;
        if (action === 'start') {
            updateAuthPlatformState(platform, {
                status: 'waiting',
                sessionId,
                message: 'UI 검증 모드입니다. 실제 로그인 창은 열지 않습니다.'
            });
            return;
        }

        updateAuthPlatformState(platform, {
            status: 'complete_requested',
            sessionId,
            message: 'UI 검증 모드에서 완료 처리를 확인하는 중입니다.'
        });
        window.setTimeout(() => {
            removeAuthPlatform(platform);
        }, 300);
    }

    function showAuthRequiredPanel(platforms, options = {}) {
        if (platforms.length === 0) {
            hideAuthRequiredPanel();
            return;
        }

        platforms.forEach(platform => {
            if (!authRenewalState[platform]) {
                updateAuthPlatformState(platform, {
                    status: 'required',
                    message: options.verifyMode
                        ? 'UI 검증 모드입니다. 실제 스크랩/API 호출은 실행하지 않습니다.'
                        : `${authPlatformLabels[platform]} 인증이 필요합니다.`,
                    verifyMode: Boolean(options.verifyMode)
                });
            }
        });
        renderAuthRequiredPanel();
    }

    if (runScrapBtn) {
        ensureAuthRequiredPanel();

        authRequiredPanel.addEventListener('click', (e) => {
            e.stopPropagation();
            const actionBtn = e.target.closest('[data-auth-action]');
            if (!actionBtn) return;

            const action = actionBtn.dataset.authAction;
            const platform = actionBtn.dataset.platform;
            if (action === 'close-panel') {
                hideAuthRequiredPanel();
                return;
            }
            if (action === 'start' || action === 'complete') {
                if (authRenewalState[platform]?.verifyMode) {
                    handleVerifyAuthAction(platform, action);
                    return;
                }
                void postAuthAction(platform, action);
            }
        });

        const verifyPlatforms = getAuthPanelVerifyPlatforms();
        if (verifyPlatforms.length > 0) {
            showAuthRequiredPanel(verifyPlatforms, { verifyMode: true });
        }

        const setScrapButtonsDisabled = (disabled) => {
            [runScrapBtn, runFullScrapBtn].forEach(btn => {
                if (!btn) return;
                btn.disabled = disabled;
                btn.classList.toggle('opacity-50', disabled);
                btn.classList.toggle('cursor-not-allowed', disabled);
            });
        };

        async function pollScrapProgressOnce() {
            if (!currentScrapRunId) return;

            const params = new URLSearchParams({
                run_id: currentScrapRunId,
                after: String(scrapProgressLastSeq)
            });
            const response = await fetch(`/api/scrap-progress?${params.toString()}`, {
                cache: 'no-store'
            }).catch(() => null);
            if (!response || !response.ok) return;

            const payload = await response.json().catch(() => null);
            if (!payload || payload.run_id !== currentScrapRunId) return;

            (payload.events || [])
                .filter(isScrapProgressEventLoggable)
                .forEach(event => {
                    scrapProgressLastSeq = Math.max(scrapProgressLastSeq, Number(event.seq || 0));
                    console.info(buildScrapProgressConsoleMessage(event));
                });
        }

        function startScrapProgressPolling(runId) {
            currentScrapRunId = runId;
            scrapProgressLastSeq = 0;
            if (scrapProgressTimer) {
                clearInterval(scrapProgressTimer);
            }
            window.setTimeout(() => {
                void pollScrapProgressOnce();
            }, 300);
            scrapProgressTimer = window.setInterval(() => {
                void pollScrapProgressOnce();
            }, 1500);
        }

        async function stopScrapProgressPolling() {
            if (scrapProgressTimer) {
                clearInterval(scrapProgressTimer);
                scrapProgressTimer = null;
            }
            await pollScrapProgressOnce();
            currentScrapRunId = '';
        }

        async function executeScrap(mode, triggerBtn) {
            if (scrapRunInProgress) {
                alert('이미 스크랩이 실행 중입니다.');
                return;
            }

            const modeLabel = mode === 'all' ? '전체 크롤링' : '최근 업데이트';
            if (!confirm(`${modeLabel}을 시작하시겠습니까? (이 작업은 수 분이 소요될 수 있습니다)`)) return;

            hideAuthRequiredPanel();
            scrapRunInProgress = true;

            const originalContent = triggerBtn ? triggerBtn.innerHTML : null;
            setScrapButtonsDisabled(true);
            if (triggerBtn) {
                triggerBtn.innerHTML = `
                    <span class="material-symbols-outlined text-[20px] animate-spin text-primary">sync</span>
                    <span class="font-medium text-xs whitespace-nowrap">Running...</span>
                `;
            }

            try {
                const statusCheck = await fetch('/api/status').catch(() => null);
                if (!statusCheck || !statusCheck.ok) {
                    alert('Flask 서버가 실행되고 있지 않습니다. 터미널에서 "python server.py"를 실행해주세요.');
                    return;
                }

                const runId = createScrapRunId();
                startScrapProgressPolling(runId);
                const response = await fetch('/api/run-scrap', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode, run_id: runId })
                });
                const result = await response.json().catch(() => ({}));
                await pollScrapProgressOnce();

                if (result.status === 'success') {
                    showScrapResultModal(result, mode);
                    const dataState = await fetchData();
                    const consistencyCheck = await verifyScrapConsistencyWithTimeout(result.consistency_probe, dataState, 3000);
                    showScrapResultModal({
                        ...result,
                        consistency_check: consistencyCheck
                    }, mode);
                } else {
                    alert(`에러 발생: ${result.message}`);
                }
            } catch (error) {
                console.error('Scraping Error:', error);
                alert('서버와 통신 중 오류가 발생했습니다.');
            } finally {
                await stopScrapProgressPolling();
                scrapRunInProgress = false;
                setScrapButtonsDisabled(false);
                if (triggerBtn && originalContent !== null) {
                    triggerBtn.innerHTML = originalContent;
                }
            }
        }

        runScrapBtn.addEventListener('click', () => {
            executeScrap('update', runScrapBtn);
        });

        if (runFullScrapBtn) {
            runFullScrapBtn.addEventListener('click', () => {
                executeScrap('all', runFullScrapBtn);
            });
        }
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

    if (closeScrapResultModalBtn) {
        closeScrapResultModalBtn.addEventListener('click', hideScrapResultModal);
    }

    if (confirmScrapResultModalBtn) {
        confirmScrapResultModalBtn.addEventListener('click', hideScrapResultModal);
    }

    if (copyAuthRenewalPromptBtn) {
        copyAuthRenewalPromptBtn.addEventListener('click', async () => {
            if (!currentAuthRenewalPrompt) return;
            try {
                await navigator.clipboard.writeText(currentAuthRenewalPrompt);
                const originalText = copyAuthRenewalPromptBtn.textContent;
                copyAuthRenewalPromptBtn.textContent = '복사됨';
                window.setTimeout(() => {
                    copyAuthRenewalPromptBtn.textContent = originalText;
                }, 1200);
            } catch (error) {
                alert('프롬프트 복사에 실패했습니다.');
            }
        });
    }

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

    function deriveConsistencyStatus(steps) {
        if (steps.some(step => step.status === 'failed')) return 'failed';
        if (steps.some(step => step.status === 'warning')) return 'warning';
        return 'passed';
    }

    function normalizeConsistencyPlatform(platform) {
        const value = String(platform || '').toLowerCase();
        if (value === 'x') return 'twitter';
        if (value === 'thread') return 'threads';
        return value;
    }

    function getConsistencyPostKey(post) {
        if (!post) return '';
        const platform = normalizeConsistencyPlatform(post.sns_platform);
        const postId = String(post.platform_id || post.code || '').trim();
        if (platform && postId) return `${platform}:id:${postId}`;

        const postUrl = resolvePostUrl(post);
        if (platform && postUrl) return `${platform}:url:${postUrl}`;
        return '';
    }

    async function verifyScrapConsistency(consistencyProbe, dataState) {
        const loadedPosts = Array.isArray(dataState?.posts) ? dataState.posts : allPosts;

        if (dataState?.ok === false) {
            return {
                status: 'failed',
                steps: [{
                    key: 'api_posts',
                    label: '서버 API',
                    status: 'failed',
                    detail: '데이터 재조회 실패'
                }]
            };
        }

        if (!consistencyProbe) {
            return {
                status: 'skipped',
                steps: []
            };
        }

        const samplesByPlatform = consistencyProbe.new_samples || {};
        const loadedKeys = new Set(loadedPosts.map(getConsistencyPostKey).filter(Boolean));
        const steps = ['linkedin', 'threads', 'twitter']
            .map(platform => {
                const samples = Array.isArray(samplesByPlatform[platform]) ? samplesByPlatform[platform] : [];
                if (samples.length === 0) return null;

                const missing = samples.filter(sample => !loadedKeys.has(getConsistencyPostKey({
                    ...sample,
                    sns_platform: sample.sns_platform || platform,
                })));
                const label = platform === 'linkedin' ? 'LinkedIn 신규 샘플' : (platform === 'threads' ? 'Threads 신규 샘플' : 'X 신규 샘플');
                return {
                    key: `new_samples_${platform}`,
                    label,
                    status: missing.length === 0 ? 'passed' : 'failed',
                    detail: missing.length === 0 ? `${samples.length}개 확인` : `${missing.length}/${samples.length}개 누락`
                };
            })
            .filter(Boolean);

        return {
            status: steps.length === 0 ? 'passed' : deriveConsistencyStatus(steps),
            steps
        };
    }

    async function verifyScrapConsistencyWithTimeout(consistencyProbe, dataState, timeoutMs = 3000) {
        let timeoutId;
        const timeoutResult = new Promise(resolve => {
            timeoutId = window.setTimeout(() => {
                resolve({
                    status: 'timeout',
                    steps: [{
                        key: 'new_samples_timeout',
                        label: '신규 샘플',
                        status: 'warning',
                        detail: '3초 안에 확인하지 못했습니다.'
                    }]
                });
            }, timeoutMs);
        });

        try {
            return await Promise.race([
                Promise.resolve().then(() => verifyScrapConsistency(consistencyProbe, dataState)),
                timeoutResult
            ]);
        } finally {
            window.clearTimeout(timeoutId);
        }
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
        clearSelection();

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
            return { ok: true, posts: allPosts };
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
            return { ok: false, posts: allPosts, error: String(error?.message || error) };
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

    function getVisibleSelectedPosts(posts, selectedUrls) {
        if (!Array.isArray(posts) || !selectedUrls) return [];
        return posts.filter((post) => selectedUrls.has(resolvePostUrl(post)));
    }

    function buildBulkCopyText(posts) {
        if (!Array.isArray(posts) || posts.length === 0) return '';
        return posts.map((post) => buildCopyText(post)).join('\n\n---\n\n');
    }

    function addSelectedUrlsToSet(targetSet, selectedUrls) {
        if (!targetSet || !selectedUrls) return targetSet;
        selectedUrls.forEach((url) => {
            if (url) targetSet.add(url);
        });
        return targetSet;
    }

    function getCurrentOrderedPosts() {
        return sortPosts(getFilteredPosts());
    }

    function getCurrentSelectedPosts() {
        return getVisibleSelectedPosts(getCurrentOrderedPosts(), selectedPosts);
    }

    function getPostUrls(posts) {
        return posts.map((post) => resolvePostUrl(post)).filter(Boolean);
    }

    function setSelectionButtonState(button, article, isSelected) {
        if (!button) return;
        const icon = button.querySelector('span');
        button.classList.toggle('selected', isSelected);
        button.classList.toggle('text-primary', isSelected);
        button.classList.toggle('text-gray-500', !isSelected);
        button.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        if (icon) {
            icon.textContent = isSelected ? 'check_circle' : 'radio_button_unchecked';
            icon.classList.toggle('fill-1', isSelected);
        }
        if (article) {
            article.classList.toggle('selected', isSelected);
        }
    }

    function updateBulkActionBar() {
        if (!bulkActionBar) return;
        const selectedCount = selectedPosts.size;
        bulkActionBar.classList.toggle('hidden', selectedCount === 0);
        if (bulkSelectedCount) {
            bulkSelectedCount.textContent = `${selectedCount}개 선택됨`;
        }
    }

    function clearSelection() {
        selectedPosts.clear();
        document.querySelectorAll('.select-btn').forEach((button) => {
            setSelectionButtonState(button, button.closest('article'), false);
        });
        updateBulkActionBar();
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
        const sentinelHost = masonryGrid.parentElement || masonryGrid;
        sentinelHost.appendChild(_ioSentinel);
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
        if (_ioSentinel) {
            _ioSentinel.remove();
        }
        _ioSentinel = null;
        _pendingPosts = [];

        if (filtered.length === 0) {
            noResults.classList.remove('hidden');
            masonryGrid.innerHTML = '';
            updateBulkActionBar();
            return;
        }

        noResults.classList.add('hidden');
        masonryGrid.innerHTML = '';
        buildMasonryColumns();

        const firstBatch = filtered.slice(0, 60);
        _pendingPosts = filtered.slice(60);
        appendCards(firstBatch);
        ensureSentinel();
        updateBulkActionBar();
    }

    function createCard(post) {
        const article = document.createElement('article');
        article.className = 'glass-card rounded-2xl p-4 flex flex-col gap-3 group break-inside-avoid relative overflow-hidden transition-all duration-300';
        
        // --- URL Definition (Critical for event handlers) ---
        const postUrl = resolvePostUrl(post);
        const isFavorited = favorites.has(postUrl);
        const isFolded = foldedPosts.has(postUrl);
        const isSelected = selectedPosts.has(postUrl);
        if (isFolded) article.classList.add('minimized');
        if (isSelected) article.classList.add('selected');

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
                <button class="select-btn p-1.5 rounded-lg hover:bg-white/10 transition-colors ${isSelected ? 'selected text-primary' : 'text-gray-500'}" data-url="${escapeHtml(postUrl)}" title="게시글 선택" aria-pressed="${isSelected ? 'true' : 'false'}">
                    <span class="material-symbols-outlined text-[20px] ${isSelected ? 'fill-1' : ''}">
                        ${isSelected ? 'check_circle' : 'radio_button_unchecked'}
                    </span>
                </button>
            </div>
        `;


        const selectBtn = header.querySelector('.select-btn');
        selectBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const url = postUrl;
            const nextSelected = !selectedPosts.has(url);

            if (nextSelected) {
                selectedPosts.add(url);
            } else {
                selectedPosts.delete(url);
            }

            setSelectionButtonState(selectBtn, article, nextSelected);
            updateBulkActionBar();
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
        const isLongText = getPostTextLength(post) > 150 || getPostTextLength(post) > previewText.length;
        const cleanText = linkifyText(previewText, { isTruncated: getPostTextLength(post) > previewText.length });

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
                    if (post.sequence_id) {
                        const detailedPost = await ensurePostDetail(post);
                        const detailedText = linkifyText(getPostPreviewText(detailedPost));
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
