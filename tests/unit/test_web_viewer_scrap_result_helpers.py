import json
import subprocess
import textwrap


def run_node_json(node_script: str):
    completed = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=".",
    )

    assert completed.returncode == 0, completed.stderr
    stdout = completed.stdout.strip()
    return json.loads(stdout.splitlines()[-1])


def test_get_failed_platforms_returns_only_known_failed_platforms():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const patterns = [`async function ${name}(`, `function ${name}(`];
          let start = -1;
          for (const pattern of patterns) {
            start = src.indexOf(pattern);
            if (start !== -1) break;
          }
          if (start === -1) {
            console.error(`${name} missing`);
            process.exit(1);
          }

          let depth = 0;
          let end = -1;
          for (let i = start; i < src.length; i += 1) {
            const ch = src[i];
            if (ch === '{') depth += 1;
            if (ch === '}') {
              depth -= 1;
              if (depth === 0) {
                end = i + 1;
                break;
              }
            }
          }

          if (end === -1) {
            console.error(`${name} parse failure`);
            process.exit(1);
          }

          return src.slice(start, end);
        }

        global.authPlatformLabels = {
          linkedin: 'LinkedIn',
          threads: 'Threads',
          x: 'X'
        };

        eval(extractFunction('normalizeAuthPlatform'));
        eval(extractFunction('getFailedPlatforms'));

        const result = getFailedPlatforms({
          platform_results: {
            x: { status: 'failed' },
            linkedin: { status: 'ok' },
            threads: { status: 'failed' },
            unknown: { status: 'failed' }
          }
        });

        console.log(JSON.stringify(result));
        """
    )

    assert run_node_json(node_script) == ["x", "threads"]


def test_build_auth_renewal_prompt_warns_against_automated_login():
    node_script = textwrap.dedent(
        r"""
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const patterns = [`async function ${name}(`, `function ${name}(`];
          let start = -1;
          for (const pattern of patterns) {
            start = src.indexOf(pattern);
            if (start !== -1) break;
          }
          if (start === -1) {
            console.error(`${name} missing`);
            process.exit(1);
          }
          let depth = 0;
          let end = -1;
          for (let i = start; i < src.length; i += 1) {
            const ch = src[i];
            if (ch === '{') depth += 1;
            if (ch === '}') {
              depth -= 1;
              if (depth === 0) {
                end = i + 1;
                break;
              }
            }
          }
          if (end === -1) {
            console.error(`${name} parse failure`);
            process.exit(1);
          }
          return src.slice(start, end);
        }

        global.authPlatformLabels = { linkedin: 'LinkedIn', threads: 'Threads', x: 'X' };
        eval(extractFunction('buildAuthRenewalPrompt'));

        const prompt = buildAuthRenewalPrompt(['x', 'threads']);
        console.log(JSON.stringify({
          includesProject: prompt.includes('D:\\vibe-coding\\scrap_sns'),
          includesPlatforms: prompt.includes('X, Threads'),
          blocksAutomatedLogin: prompt.includes('자동화 브라우저 로그인은 사용하지 마세요'),
          includesReadme: prompt.includes('README.md의 인증 갱신 섹션'),
          includesVerification: prompt.includes('세션 유효성 검증')
        }));
        """
    )

    assert run_node_json(node_script) == {
        "includesProject": True,
        "includesPlatforms": True,
        "blocksAutomatedLogin": True,
        "includesReadme": True,
        "includesVerification": True,
    }


def test_build_scrap_result_view_model_includes_stats_and_auth_notice():
    node_script = textwrap.dedent(
        r"""
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const patterns = [`async function ${name}(`, `function ${name}(`];
          let start = -1;
          for (const pattern of patterns) {
            start = src.indexOf(pattern);
            if (start !== -1) break;
          }
          if (start === -1) {
            console.error(`${name} missing`);
            process.exit(1);
          }
          let depth = 0;
          let end = -1;
          for (let i = start; i < src.length; i += 1) {
            const ch = src[i];
            if (ch === '{') depth += 1;
            if (ch === '}') {
              depth -= 1;
              if (depth === 0) {
                end = i + 1;
                break;
              }
            }
          }
          if (end === -1) {
            console.error(`${name} parse failure`);
            process.exit(1);
          }
          return src.slice(start, end);
        }

        global.authPlatformLabels = { linkedin: 'LinkedIn', threads: 'Threads', x: 'X' };
        eval(extractFunction('normalizeAuthPlatform'));
        eval(extractFunction('getAuthRequiredPlatforms'));
        eval(extractFunction('getFailedPlatforms'));
        eval(extractFunction('getScrapStats'));
        eval(extractFunction('buildAuthRenewalPrompt'));
        eval(extractFunction('buildScrapResultViewModel'));

        const model = buildScrapResultViewModel({
          status: 'success',
          auth_required: ['x', 'threads'],
          platform_results: {
            x: { status: 'auth_required' },
            threads: { status: 'auth_required' },
            linkedin: { status: 'ok' }
          },
          stats: {
            total: 12,
            threads: 5,
            linkedin: 7,
            twitter: 0,
            total_count: 1248,
            threads_count: 520,
            linkedin_count: 410,
            twitter_count: 318
          }
        }, 'update');

        console.log(JSON.stringify({
          title: model.title,
          totalLine: model.totalLine,
          rows: model.rows,
          authLabels: model.authLabels,
          hasPrompt: model.authPrompt.includes('X, Threads')
        }));
        """
    )

    assert run_node_json(node_script) == {
        "title": "업데이트 완료",
        "totalLine": "총 12건 신규 추가 · 전체 1248건",
        "rows": [
            {"label": "Threads", "delta": "5건 추가", "total": "전체 520건"},
            {"label": "LinkedIn", "delta": "7건 추가", "total": "전체 410건"},
            {"label": "X", "delta": "0건 추가", "total": "전체 318건"},
        ],
        "authLabels": ["X", "Threads"],
        "hasPrompt": True,
    }


def test_build_scrap_result_view_model_includes_consistency_steps():
    node_script = textwrap.dedent(
        r"""
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const patterns = [`async function ${name}(`, `function ${name}(`];
          let start = -1;
          for (const pattern of patterns) {
            start = src.indexOf(pattern);
            if (start !== -1) break;
          }
          if (start === -1) {
            console.error(`${name} missing`);
            process.exit(1);
          }
          let depth = 0;
          let end = -1;
          for (let i = start; i < src.length; i += 1) {
            const ch = src[i];
            if (ch === '{') depth += 1;
            if (ch === '}') {
              depth -= 1;
              if (depth === 0) {
                end = i + 1;
                break;
              }
            }
          }
          if (end === -1) {
            console.error(`${name} parse failure`);
            process.exit(1);
          }
          return src.slice(start, end);
        }

        global.authPlatformLabels = { linkedin: 'LinkedIn', threads: 'Threads', x: 'X' };
        eval(extractFunction('normalizeAuthPlatform'));
        eval(extractFunction('getAuthRequiredPlatforms'));
        eval(extractFunction('getFailedPlatforms'));
        eval(extractFunction('getScrapStats'));
        eval(extractFunction('buildAuthRenewalPrompt'));
        eval(extractFunction('buildScrapResultViewModel'));

        const model = buildScrapResultViewModel({
          status: 'success',
          stats: {
            total: 1,
            threads: 0,
            linkedin: 1,
            twitter: 0,
            total_count: 1222,
            threads_count: 844,
            linkedin_count: 312,
            twitter_count: 66
          },
          consistency_check: {
            status: 'failed',
            steps: [
              { key: 'total_file', label: '통합 파일', status: 'passed', detail: '1222건' },
              { key: 'screen', label: '화면 표시', status: 'failed', detail: '필터에 가려짐' }
            ]
          }
        }, 'update');

        console.log(JSON.stringify({
          resultTitle: model.title,
          title: model.consistencyTitle,
          status: model.consistencyStatus,
          rows: model.consistencyRows
        }));
        """
    )

    assert run_node_json(node_script) == {
        "resultTitle": "업데이트 확인 필요",
        "title": "정합성 확인",
        "status": "failed",
        "rows": [
            {"label": "통합 파일", "status": "passed", "detail": "1222건"},
            {"label": "화면 표시", "status": "failed", "detail": "필터에 가려짐"},
        ],
    }


def test_build_scrap_result_view_model_hides_passed_consistency_steps():
    node_script = textwrap.dedent(
        r"""
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const patterns = [`async function ${name}(`, `function ${name}(`];
          let start = -1;
          for (const pattern of patterns) {
            start = src.indexOf(pattern);
            if (start !== -1) break;
          }
          if (start === -1) {
            console.error(`${name} missing`);
            process.exit(1);
          }
          let depth = 0;
          let end = -1;
          for (let i = start; i < src.length; i += 1) {
            const ch = src[i];
            if (ch === '{') depth += 1;
            if (ch === '}') {
              depth -= 1;
              if (depth === 0) {
                end = i + 1;
                break;
              }
            }
          }
          return src.slice(start, end);
        }

        global.authPlatformLabels = { linkedin: 'LinkedIn', threads: 'Threads', x: 'X' };
        eval(extractFunction('normalizeAuthPlatform'));
        eval(extractFunction('getAuthRequiredPlatforms'));
        eval(extractFunction('getFailedPlatforms'));
        eval(extractFunction('getScrapStats'));
        eval(extractFunction('buildAuthRenewalPrompt'));
        eval(extractFunction('buildScrapResultViewModel'));

        const model = buildScrapResultViewModel({
          status: 'success',
          stats: {
            total: 2,
            threads: 1,
            linkedin: 1,
            twitter: 0,
            total_count: 1222,
            threads_count: 844,
            linkedin_count: 312,
            twitter_count: 66
          },
          consistency_check: {
            status: 'passed',
            steps: [
              { key: 'new_samples', label: '신규 샘플', status: 'passed', detail: '3개 확인' }
            ]
          }
        }, 'update');

        console.log(JSON.stringify({
          resultTitle: model.title,
          title: model.consistencyTitle,
          status: model.consistencyStatus,
          rowCount: model.consistencyRows.length
        }));
        """
    )

    assert run_node_json(node_script) == {
        "resultTitle": "업데이트 완료",
        "title": "",
        "status": "passed",
        "rowCount": 0,
    }


def test_verify_scrap_consistency_reports_missing_new_sample():
    node_script = textwrap.dedent(
        r"""
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const patterns = [`async function ${name}(`, `function ${name}(`];
          let start = -1;
          for (const pattern of patterns) {
            start = src.indexOf(pattern);
            if (start !== -1) break;
          }
          if (start === -1) {
            console.error(`${name} missing`);
            process.exit(1);
          }
          let depth = 0;
          let end = -1;
          for (let i = start; i < src.length; i += 1) {
            const ch = src[i];
            if (ch === '{') depth += 1;
            if (ch === '}') {
              depth -= 1;
              if (depth === 0) {
                end = i + 1;
                break;
              }
            }
          }
          return src.slice(start, end);
        }

        eval(extractFunction('resolvePostUrl'));
        eval(extractFunction('deriveConsistencyStatus'));
        eval(extractFunction('normalizeConsistencyPlatform'));
        eval(extractFunction('getConsistencyPostKey'));
        eval(extractFunction('verifyScrapConsistency'));

        (async () => {
          const result = await verifyScrapConsistency({
            new_samples: {
              linkedin: [
                {
                  platform_id: 'li-new-1',
                  sns_platform: 'linkedin',
                  url: 'https://www.linkedin.com/feed/update/urn:li:activity:1'
                }
              ],
              threads: [],
              twitter: []
            }
          }, {
            ok: true,
            posts: []
          });
          console.log(JSON.stringify(result));
        })();
        """
    )

    assert run_node_json(node_script) == {
        "status": "failed",
        "steps": [
            {
                "key": "new_samples_linkedin",
                "label": "LinkedIn 신규 샘플",
                "status": "failed",
                "detail": "1/1개 누락",
            }
        ],
    }


def test_scrap_progress_console_message_helpers_filter_and_format_events():
    node_script = textwrap.dedent(
        r"""
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const patterns = [`async function ${name}(`, `function ${name}(`];
          let start = -1;
          for (const pattern of patterns) {
            start = src.indexOf(pattern);
            if (start !== -1) break;
          }
          if (start === -1) {
            console.error(`${name} missing`);
            process.exit(1);
          }
          let depth = 0;
          let end = -1;
          for (let i = start; i < src.length; i += 1) {
            const ch = src[i];
            if (ch === '{') depth += 1;
            if (ch === '}') {
              depth -= 1;
              if (depth === 0) {
                end = i + 1;
                break;
              }
            }
          }
          if (end === -1) {
            console.error(`${name} parse failure`);
            process.exit(1);
          }
          return src.slice(start, end);
        }

        eval(extractFunction('isScrapProgressEventLoggable'));
        eval(extractFunction('buildScrapProgressConsoleMessage'));

        const events = [
          { seq: 1, message: '최근 업데이트 스크랩 시작' },
          { seq: 2, message: '' },
          { seq: 3, message: 'LinkedIn 목록 수집 완료' },
          { seq: 4, message: null }
        ];

        const messages = events
          .filter(isScrapProgressEventLoggable)
          .map(buildScrapProgressConsoleMessage);

        console.log(JSON.stringify(messages));
        """
    )

    assert run_node_json(node_script) == [
        "[SNS Scrap] 최근 업데이트 스크랩 시작",
        "[SNS Scrap] LinkedIn 목록 수집 완료",
    ]
