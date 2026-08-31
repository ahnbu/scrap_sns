---
title: 유튜브 외부 요약(Lilys·LiveWiki) 링크 뷰어 연동과 수집 중복실행 가드 계획
created: 2026-08-28 (KST)
updated: 2026-08-28 (KST)
session_id: 8b4aba7b-6afe-4a84-a957-1013186633dc
session_path: C:/Users/ahnbu/.claude/projects/D--vibe-coding-scrap-sns/8b4aba7b-6afe-4a84-a957-1013186633dc.jsonl
ai: claude
---

# 유튜브 외부 요약(Lilys·LiveWiki) 링크 뷰어 연동과 수집 중복실행 가드 계획

- 작성일: 2026-08-28 (KST)
- 한 줄 요약: 유튜브 카드에 **내가 이미 만들어 둔 Lilys·LiveWiki 요약으로 가는 아이콘**을 붙인다. 매핑이 있는 카드에만 붙인다.
- 선행 작업 (이 세션에서 이미 완료, 3장에서 검증)
  - `scripts/lilys_library.mjs` — Lilys 라이브러리 수집기 (신규)
  - `scripts/livewiki_library.mjs` — LiveWiki 라이브러리 수집기 (신규)
  - `docs/architecture.md` — X producer 인증 방식 실측 기록 추가
- 참조 문서
  - `docs/20260505_02_LinkedIn_인증접근방식_테스트계획.md` — LinkedIn storage_state 채택 근거
  - `docs/20260505_01_X-인증갱신-정본화-수행계획.md` — X `user_data` 정본 원칙
  - `C:/Users/ahnbu/.claude/skills/_shared/Playwright-로그인-인증-가이드.md` — 인증 생성자/실행자 분리 원칙

---

## 1. 상황 (Situation)

### 1.1 발단 — 사용자 요청 두 가지

1. 카드 푸터의 `View Original` 문구가 불필요하다. 아이콘만 남기면 된다.
2. 유튜브 영상 중 이미 Lilys·LiveWiki에 정리해 둔 것이 있다. 원본 링크 왼쪽에 그 링크로 가는 아이콘을 붙이고 싶다.
   최종 형태는 `(Lilys) (LiveWiki) (원본보기)` 아이콘 3개.

### 1.2 현재 카드 푸터

`web_viewer/script.js:3218-3231`

```html
<button class="note-open-btn">+note</button>
<a href="{postUrl}" class="... ml-auto">
  <span>View Original</span>
  <span class="material-symbols-outlined text-[16px]">open_in_new</span>
</a>
```

전 플랫폼 2,558개 카드에 같은 영어 라벨이 반복되고, 옆의 `open_in_new` 아이콘이 이미 같은 뜻을 말한다.

### 1.3 실측 — 유튜브 카드는 이미 요약을 갖고 있다

`output_total/total_full_20260827.json` (2,558건) 기준.

| 플랫폼 | 건수 |
|---|---|
| threads | 1,304 |
| linkedin | 699 |
| **youtube** | **460** |
| x | 95 |

유튜브 460건의 `summary_status` 분포: `ok` 449 / `no_transcript` 11.
즉 **97.6%가 이미 카드 본문에 `[요약] [상세] [설명] [타임라인]`을 갖고 있다.** `youtube_scrap.py`가 자막을 받아 agy CLI로 요약을 만들어 `full_text`에 넣기 때문이다.

이 사실이 이 기능의 가치를 깎는다. "요약을 읽으려고" 밖으로 나갈 이유는 거의 없다.
남는 가치는 Lilys·LiveWiki가 주는 **다른 층**이다 — 타임라인 클릭 시 영상 위치 점프, 원문 스크립트 대조, 하이라이트, AI 채팅. 자체 요약이 대체하지 못한다.

### 1.4 실측 — 매핑 가능 건수

두 수집기를 실제로 돌려 얻은 결과다.

| | 라이브러리 | 영상 ID 보유 | scrap_sns 460건과 겹침 |
|---|---|---|---|
| Lilys | 218 세션 (유튜브 161, 고유 영상 156) | 100% | **72건** |
| LiveWiki | 742 콘텐츠 (전부 YOUTUBE) | 100% (742/742) | **63건** |
| **합집합** | | | **130건 / 460 = 28.3%** |

내역: Lilys만 67 · LiveWiki만 58 · 양쪽 5.

**나머지 71.7%는 아이콘이 붙지 않는다.** 매핑이 있을 때만 렌더하므로 죽은 아이콘은 생기지 않는다.

### 1.5 실측 — 두 서비스의 API와 인증

| | Lilys | LiveWiki |
|---|---|---|
| 목록 API | `api.lilys.ai/backend/digest-sessions?provider=google&page=N&limit=20&inboxStatus=inbox` | `api.livewiki.com/content/list/last/summarize?page=N&size=20` |
| 영상 ID 위치 | `resources[].sourceId` | `source.youtubeVideo.v` |
| URL 생성 | `https://lilys.ai/digest/11132480` — 세션 id 하나면 되고 하위 노트 id는 자동 리다이렉트로 붙는 것을 실측 확인 | `https://livewiki.com/ko/content/8900bc8e-053d-4214-9a42-051fb59f5a60` — 응답의 `slug` 값을 그대로 붙인다 |
| API 토큰 | Firebase id_token, **수명 1시간** | 자체 JWT, **수명 30일** |
| 장기 자격증명 | `refresh_token` 평문, **회전 없음** | `corelyAToken`/`corelyRToken`이 **CryptoJS AES 암호문** (`U2Fs…` = `Salted__`) |
| 자동 갱신 | `securetoken.googleapis.com/v1/token` REST 한 번 | 복호화 키가 프런트 번들 안에 있어 재현 필요 |
| 필요 헤더 | `authorization` + `lilys-provider` | **`authorization` 하나면 통과** (실측) |
| 사람 개입 주기 | 최초 1회 (사실상 무기한) | **30일에 1회** |

### 1.6 곁가지로 확인된 것 — X producer 인증

조사 중 "LinkedIn/Threads는 `storage_state`, X는 persistent profile"인 이유를 확인했다.

- X의 `launch_persistent_context`는 최초 X 커밋 `0e8ec80`(2026-02-12)에 들어간 뒤 **한 번도 재검토되지 않았다.** LinkedIn은 `docs/20260505_02`에서 persistent profile까지 비교한 결과 `storage_state`를 택했다.
- 비파괴 A/B probe 결과 **두 방식이 동일했다.** 레포 기준(`classify_producer_probe`의 `bookmark_response`) 통과, 실제 북마크 entry 40건 동일. 4개월 지난 `x/storage_state.json`(2026-05-04) 스냅샷으로도 통과했다.
- profile 용량 2,805MB vs `storage_state` 4KB.

이 사실은 `docs/architecture.md`에 이미 기록했다. **전환은 하지 않는다** (3.1 기각 8번).

---

## 2. 문제 (Complication)

### 2.1 P1 — 수집 산출물이 뷰어에 닿지 않는다

`scripts/lilys_library.mjs`, `scripts/livewiki_library.mjs`가 `output_external/*.json`을 만들지만, 뷰어가 읽는 경로가 없다. 두 파일을 합쳐 영상 ID 하나에 두 링크를 매다는 단계가 비어 있다.

### 2.2 P2 — 푸터가 아이콘 3개를 받을 구조가 아니다

현재 푸터는 `<a>` 하나에 `ml-auto`로 우측 정렬돼 있다. 아이콘이 1~3개로 카드마다 달라지므로 개수 변화를 견디는 배치가 필요하다. 라벨을 지우면 클릭 타깃이 16px 아이콘 하나로 줄어드는 문제도 같이 온다.

### 2.3 P3 — 매핑이 낡는다

새 요약을 만들면 매핑에 없다. 수집기를 언제 돌릴지, 실패하면 어떻게 되는지가 정해져 있지 않다. 비공식 내부 API 의존이라 스키마가 바뀌면 조용히 깨진다.

### 2.4 P4 — `/api/run-scrap`에 중복 실행 가드가 없다

`scrap_sns_server.py:1107` `run_scrap()`은 `_reset_scrap_progress()`로 진행 상태를 **덮어쓸 뿐** 409를 반환하지 않는다. `total_scrap.py:367` `run_scrapers_in_parallel()`이 4개 플랫폼을 동시 subprocess로 띄우므로, 두 벌이 돌면 다음이 겹친다.

| 겹치는 자원 | 결과 |
|---|---|
| `*_py_full_YYYYMMDD.json` (4개 플랫폼, 같은 날짜 파일) | 나중에 쓴 쪽이 이김 |
| `output_total/total_full_YYYYMMDD.json` 병합 | 두 병합이 동시 수행 |
| `logs/youtube_summary_ledger.jsonl` | 동시 append |
| 서버 전역 `SCRAP_PROGRESS` | 덮어써져 진행률 UI가 두 실행을 뒤섞어 표시 |
| YouTube 요약 (agy CLI) | 중복 실행 = 중복 비용 |
| `AUTH_HOME/x/user_data` | X만 해당. 프로필 경합 |

**인증 경합은 X만의 문제지만, 출력 파일 경합은 인증 방식과 무관하다.** 전역 규칙의 "공유 캐시·동일 출력 경로를 쓰는 작업은 병렬 실행하지 않는다"에 걸린다.

프런트엔드에는 이미 가드가 있다 — `web_viewer/script.js:1306` `scrapRunInProgress` 플래그 + `setScrapButtonsDisabled(true)`. 한 탭에서 두 번 누르는 것은 막힌다.
남는 구멍은 **탭 단위 JS 변수**라는 점이다. 두 번째 탭, 실행 중 새로고침 후 재클릭, 직접 API 호출은 통과한다.

발생 조건이 좁아 긴급하지는 않다. 다만 "조용히 데이터가 섞이는" 종류라 방치하면 원인 추적이 어렵다.

---

## 3. 해결 방안 (Resolution)

### 3.1 검토한 옵션과 기각 근거

| # | 옵션 | 판정 | 근거 |
|---|---|---|---|
| 1 | 메모 필드에 URL 붙여넣고 자동 링크화 | ❌ 기각 | 사용자가 명시적으로 기각. "일일이 입력하는 것은 안 하는 것과 같다" |
| 2 | 매핑 없이 모든 유튜브 카드에 아이콘 상시 노출 | ❌ 기각 | 71.7%가 죽은 아이콘이 된다 |
| 3 | 아이콘을 요약 **생성** 트리거로 사용 | ❌ 기각 | LiveWiki는 홈 입력창 타이핑 + 로그인 + 최대 8분 대기, Lilys API는 유료. 클릭 한 번으로 끝나지 않는다 |
| 4 | LiveWiki를 **제목 정규화**로 매칭 | ❌ 기각 | 표본 22건 전수 검증에서 오탐은 0이었으나 **9건을 놓쳤다**(54 vs 63). `content/list/last/summarize`가 영상 ID를 직접 준다 |
| 5 | Lilys를 `storage_state` 방식으로 (LinkedIn/Threads와 동일) | ❌ 기각 | Firebase 인증 정본이 IndexedDB(`firebaseLocalStorageDb`)에 있고 `storageState()`는 `origin`+`localStorage`만 담는다. access_token 무효화 후 재현 시도 → 자동 재발급 실패 실측 |
| 6 | Lilys 수집을 브라우저 프로필 경유로 (매 실행 headless 기동) | ❌ 기각 | 40초 소요, 프로필 잠금 필요, `total_scrap` 병렬과 충돌. `refresh_token`이 회전하지 않아 REST로 대체 가능함을 실측 |
| 7 | LiveWiki AES 복호화를 재현해 무기한 자동 갱신 | ❌ 기각 | 복호화 키가 프런트 번들에 있어 배포마다 바뀌면 조용히 깨진다. 얻는 것이 30일에 1분뿐 |
| 8 | X producer를 `storage_state`로 전환 | ❌ 기각 | A/B 동일. 지금 깨지고 있지 않고, X는 이 레포에서 인증 사고 이력이 가장 많다(`4f9dca9`, `a64f9d4`, `docs/20260425_01`). 1회 probe 통과가 120페이지 페이지네이션 장시간 실행의 봇 탐지까지 보장하지 않는다 |
| 9 | 동시 실행을 X 인증 방식 변경으로 해결 | ❌ 기각 | 출력 파일 경합은 인증 방식과 무관. 올바른 해결 위치는 `/api/run-scrap` 가드다 |
| **10** | **수집기 2개 → 매핑 파일 1개 → 매핑 있는 카드에만 아이콘** | ✅ **채택** | 영상 ID 정확 일치, 죽은 아이콘 없음, 기존 `sns_tags.json`·`sns_user_metadata.json`과 같은 층 |

> 정렬 기준: "자동으로 데이터를 확보할 수 있는가"가 1차 관문이고, 그다음이 "안 되는 카드에 아이콘이 남는가"다. 인증 관련 기각(5~8)은 실측 없이 판단하면 반복해서 틀린다.

### 3.2 파일 역할 분담

| 파일 | 성격 | git |
|---|---|---|
| `output_external/lilys_library.json` | 수집 중간 산출물 (40초면 재생성) | 무시 (`output_*` 규칙) |
| `output_external/livewiki_library.json` | 위와 동일 (6초면 재생성) | 무시 |
| `web_viewer/sns_external_summaries.json` | **뷰어가 읽는 최종 매핑** | ✅ 추적 |

> 정렬 기준: "다시 만들 수 있는가"가 추적 여부를 가른다. `linkedin_py_full_*.json` 같은 정본은 게시글이 사라지면 못 만들지만, 이 둘은 계정에서 언제든 다시 받는다.

### 3.3 상세 변경 계획

#### T1. 매핑 병합 스크립트 — `scripts/build_external_summaries.mjs` (신규)

- 입력: `output_external/lilys_library.json`, `output_external/livewiki_library.json`
- 출력: `web_viewer/sns_external_summaries.json`

```json
{
  "generated_at_kst": "...",
  "sources": { "lilys": { "collected_at_kst": "...", "count": 156 },
               "livewiki": { "collected_at_kst": "...", "count": 742 } },
  "items": {
    "fPgZhHMJc_I": { "lilys": "https://lilys.ai/digest/11132480", "livewiki": null },
    "bA2Rg0JE7xA": { "lilys": null, "livewiki": "https://livewiki.com/ko/content/8900bc8e-053d-4214-9a42-051fb59f5a60" }
  }
}
```

- 두 입력 중 **하나만 있어도 진행**하고, 없는 쪽은 `null`로 둔다. 한쪽 수집이 실패해도 다른 쪽 아이콘은 살아야 한다.
- 입력 파일이 둘 다 없으면 **기존 출력을 건드리지 않고** 종료한다 (마지막 성공본 보존).
- `--dry-run`을 기본이 아닌 옵션으로 두되, 변경 건수(추가/삭제/유지)를 항상 stdout에 남긴다.

#### T2. 푸터 렌더 변경 — `web_viewer/script.js:3218-3231`

- `View Original` 텍스트 제거. `open_in_new` 아이콘만 남기고 `title="원본 보기"` + `aria-label` 부여.
- 클릭 타깃을 최소 24px로 확보 (패딩).
- 유튜브 카드이고 `sns_external_summaries.json`에 `platform_id`가 있을 때만 Lilys·LiveWiki 아이콘을 **원본 아이콘 왼쪽에** 추가. 각각 `title`로 서비스명 표시.
- 아이콘 그룹 전체를 `ml-auto` 컨테이너로 감싸 개수가 1~3개로 바뀌어도 우측 정렬이 유지되게 한다.
- 아이콘 소스는 외부 요청 없이 인라인 SVG 또는 `material-symbols-outlined`로 한다. 뷰어는 로컬 자산만 쓴다.
- headless 판정을 위해 외부 요약 앵커에 `data-external-summary` 속성을 붙인다. 값은 Lilys 앵커면 `"lilys"`, LiveWiki 앵커면 `"livewiki"` 두 가지뿐이다. 4.4.1의 V2~V4·V6이 이 속성으로 개수를 센다. 이 속성이 없으면 자동 판정이 DOM 구조 추측에 의존하게 된다.

#### T3. 데이터 로드 경로 — `/api/get-external-summaries` 신설 (확정)

코드 확인 결과 후보 3개 중 (c)로 확정했다.

| 후보 | 판정 | 근거 |
|---|---|---|
| (a) `web_viewer/data.js`에 인라인 | ❌ **불가능** | `data.js` 파일이 존재하지 않고 `utils/build_data_js` 모듈도 없다. `CHANGELOG.md:206`(2026-04-19)에 "자동태그 서버 위임과 **data.js 파이프라인 제거**"로 기록돼 있다 |
| (b) 정적 `fetch('/web_viewer/sns_external_summaries.json')` | ⚠️ 가능하나 미채택 | `scrap_sns_server.py:1576` `@app.route('/<path:path>')` → `_send_web_viewer_asset()`이 `web_viewer/` 접두 경로를 서빙하므로 동작은 한다. 다만 파일이 없으면 404라 프런트에 예외 처리가 흩어진다 |
| **(c) `/api/get-external-summaries` 엔드포인트 신설** | ✅ **채택** | 기존 3개 JSON이 전부 이 패턴이다 |

**채택 근거**

- `web_viewer/script.js:2121-2123`이 `/api/get-tags`, `/api/get-tag-catalog`, `/api/get-user-metadata`를 `Promise.all`로 한 번에 받는다. 여기에 한 줄만 추가하면 된다.
- 서버 쪽 `get_user_metadata()`(`scrap_sns_server.py:911`)는 **파일이 없으면 `{}`를 반환**한다. 수집기를 한 번도 돌리지 않은 상태에서도 뷰어가 정상 동작한다. 정적 fetch로는 이 방어를 프런트가 떠안아야 한다.
- 매핑 갱신이 서버 재시작과 무관해진다.

**구현 내용**

- `scrap_sns_server.py`에 `GET /api/get-external-summaries` 추가. `WEB_VIEWER_DIR/sns_external_summaries.json`을 읽고, 파일이 없거나 형태가 다르면 `{}` 반환. `get_user_metadata()`를 그대로 본뜬다.
- 쓰기 엔드포인트는 만들지 않는다. 이 파일은 뷰어가 아니라 `scripts/build_external_summaries.mjs`가 만든다. 사용자 상태가 아니므로 `/api/save-*`가 필요 없다.
- `web_viewer/script.js:2121`의 `Promise.all`에 추가하고, 응답을 모듈 스코프 변수에 담아 T2의 푸터 렌더가 참조한다. `localStorage` 캐시는 두지 않는다 — 사용자 상태가 아니라 파생 데이터다.

#### T4. `/api/run-scrap` 중복 실행 가드 — `scrap_sns_server.py`

- `run_scrap()` 진입부에서 `SCRAP_PROGRESS["running"]`이 참이면 **409**와 함께 실행 중인 `run_id`·`started_at`을 반환한다.
- 판정과 상태 갱신은 `SCRAP_PROGRESS_LOCK` 안에서 원자적으로 한다. 검사와 `_reset_scrap_progress()` 사이에 틈이 생기면 가드가 무의미하다.
- 기존 `/api/renew-auth`의 409 패턴(`scrap_sns_server.py:1258`)을 따른다.
- 뷰어 쪽은 409 응답을 받으면 "이미 실행 중" 안내를 띄운다. 현재 `alert('이미 스크랩이 실행 중입니다.')` 문구를 재사용한다.

**stale 임계값 = 10800초 (3시간). 확정값이다.**

비정상 종료로 `running`이 참인 채 남으면 서버 재시작 전까지 영구히 막힌다. 이를 막기 위해 `started_monotonic` 기준 경과가 임계값을 넘긴 실행은 죽은 것으로 보고 새 실행을 허용한다.

값 근거 (실측):

| 근거 | 값 |
|---|---|
| `logs/scrap_progress.log`의 `--mode update` 완료 경과 | 1분 20초 ~ 5분 38초 (최근 10회) |
| 같은 로그의 관측 최대 경과 | **13분 05초** |
| 기존 선례 — auth job stale 판정 (`scrap_sns_server.py:490`) | 3600초 |

관측 최대의 약 13배 여유를 둔다. auth job의 1시간보다 길게 잡는 이유는 `--mode all` + `youtube_scrap.py --max-summaries 15`가 update보다 훨씬 오래 걸리기 때문이다. 상수는 `SCRAP_STALE_SECONDS = 10800`으로 모듈 상단에 둔다.

**가드는 가볍게 유지한다.** 검사는 이미 존재하는 `SCRAP_PROGRESS` 딕셔너리 조회 하나이고, 새 lock·파일·프로세스를 만들지 않는다. 스크래퍼 파이프라인 자체를 멈추는 장치를 도입하지 않는다.

#### T5. `AGENTS.md`의 죽은 지시 제거 (곁가지, 이번에 같이 처리)

T3을 확정하는 과정에서 발견했다. `AGENTS.md`가 존재하지 않는 파이프라인을 지시하고 있다.

| 위치 | 현재 문구 | 실제 |
|---|---|---|
| `AGENTS.md:32` | "`python -m utils.build_data_js` — 뷰어용 정적 데이터(`web_viewer/data.js`) 재생성. **파서·스키마를 고친 뒤 뷰어 검증 전에 돌린다**" | 모듈 없음 (`ModuleNotFoundError`) |
| `AGENTS.md:61` | "뷰어 정적 데이터: `web_viewer/data.js` — `python -m utils.build_data_js` 산출물이며 손으로 고치지 않는다" | 파일 없음 |

2026-04-19에 파이프라인이 제거됐는데(`CHANGELOG.md:206`) 규칙 문서만 남았다. 지시를 따르려는 사람이 실패하고 원인을 찾는 데 시간을 쓴다. 두 항목을 삭제한다.

이 변경은 코드 동작에 영향이 없고 문서만 바꾼다.

### 3.4 이번 범위에서 명시적으로 빼는 것

- Lilys·LiveWiki 수집기를 `total_scrap.py`에 편입하지 않는다. 수동 실행으로 시작하고, 갱신 주기는 실사용 뒤 정한다.
- LiveWiki 자동 토큰 갱신(AES 복호화)을 만들지 않는다.
- X 인증 방식을 바꾸지 않는다.
- 유튜브 외 플랫폼에는 외부 요약 아이콘을 붙이지 않는다.
- Lilys 항목의 빈 `channel` 값(156건 중 47건)을 보강하지 않는다. 매칭은 영상 ID로 하므로 기능 영향이 없다.

---

## 4. 검증 계획

### 4.1 선행 작업 검증 (계획 실행 전에 먼저 한다)

이 세션에서 이미 만든 것들이 실제로 도는지 다시 확인한다.

| 대상 | 확인 방법 | 기대 |
|---|---|---|
| `scripts/lilys_library.mjs check-auth` | 실행 | `AUTH_OK` + 계정 표시 |
| `scripts/lilys_library.mjs list` | 실행 | 세션 218 / 고유 영상 156 |
| `scripts/livewiki_library.mjs check-auth` | 실행 | `AUTH_OK` + 만료일 표시 |
| `scripts/livewiki_library.mjs list` | 실행 | 콘텐츠 742 / 고유 영상 742 |
| 비밀값 미유출 | `status`/출력 JSON 검사 | 토큰 문자열 0건 |
| 동시 실행 | 3개 병렬 실행 | 전부 성공, 잠금 파일 미생성 |
| 기존 스킬 자산 보존 | `AUTH_HOME/livewiki/status.json`, `storage_state.json` | 타임스탬프 미변경 |
| `docs/architecture.md` | 문서 확인 | X 인증 실측 단락 존재 |

### 4.2 신설할 테스트

| # | 파일 | 검증 내용 |
|---|---|---|
| U1 | `tests/unit/test_build_external_summaries.mjs` | 두 입력 병합 시 영상 ID 하나에 두 링크가 매달린다 |
| U2 | 위와 동일 | 한쪽 입력만 있으면 없는 쪽이 `null`이고 실패하지 않는다 |
| U3 | 위와 동일 | 입력이 둘 다 없으면 기존 출력을 덮어쓰지 않는다 |
| U4 | `tests/integration/test_run_scrap_guard.py` | `running=True`일 때 `/api/run-scrap`이 409를 반환하고 새 프로세스를 띄우지 않는다 |
| U5 | 위와 동일 | stale 임계값(10800초)이 지나면 새 실행을 허용한다 |
| U6 | `tests/integration/test_external_summaries_api.py` | 매핑 파일이 없을 때 `/api/get-external-summaries`가 `{}`를 200으로 반환한다 |
| U7 | 위와 동일 | 매핑 파일이 있으면 그 내용을 그대로 반환한다 |

> 서버 API 테스트는 `tests/unit/`이 아니라 `tests/integration/`에 둔다. 기존 선례가 그렇다 — `tests/integration/test_user_metadata_api.py`, `test_posts_api.py`, `test_run_scrap_stats.py`.
| E1~E6 | `scripts/verify_external_summary_icons.mjs` (신규) | 4.4.1의 V1~V6. headless, 종료코드로 판정 |

### 4.3 기존 테스트 영향

- `pytest tests/unit` — `scrap_sns_server` 변경이 있으므로 전체를 돌린다.
- `pytest tests/integration/test_run_scrap_stats.py` — `run_scrap()` 직접 변경. 반드시 통과 확인.
- `pytest tests/unit/test_total_scrap_orchestration.py` — 오케스트레이션 회귀 확인.
- 뷰어 변경이므로 `node scripts/verify_youtube_viewer_headless.mjs`로 유튜브 카드 렌더 회귀를 확인한다.

### 4.4 뷰어 검증 — headless 자동 판정이 1차, 사람 눈이 2차

뷰어 UX가 바뀌므로 API/CLI 결과만으로 완료 판단하지 않는다.
다만 **판정 주체는 사람 눈이 아니라 headless 스크립트의 종료코드**다. 사람 눈 확인은 `AGENTS.md:93`이 별도로 요구하는 절차이므로 그 위에 얹는다.

#### 4.4.1 (1차) headless 자동 판정 — `scripts/verify_external_summary_icons.mjs` (신규)

`scripts/verify_youtube_viewer_headless.mjs`와 같은 형식으로 만든다. **창을 띄우지 않는다** — 창이 뜨면 사용자 포커스를 빼앗아 병행 작업이 끊긴다. 이 검증에 창이 필요한 이유가 없다.

| 검사 | 통과 조건 |
|---|---|
| V1 | 푸터 어디에도 문자열 `View Original`이 없다 |
| V2 | 매핑에 있는 유튜브 카드에 외부 요약 앵커가 렌더된다. `href`가 `lilys.ai/digest/` 또는 `livewiki.com/ko/content/`로 시작한다 |
| V3 | 매핑에 없는 유튜브 카드에는 외부 요약 앵커가 0개다 |
| V4 | 유튜브 외 플랫폼 카드에는 외부 요약 앵커가 0개다 |
| V5 | 원본 보기 앵커가 모든 카드에 1개씩 있고 `title` 또는 `aria-label`을 갖는다 |
| V6 | 렌더된 외부 앵커 수가 `sns_external_summaries.json`의 매핑 건수와 화면 표시 건수의 교집합과 일치한다 |

- 대상 `video_id`는 하드코딩하지 않고 `web_viewer/sns_external_summaries.json`에서 런타임에 읽는다.
- 검사별 `✅/❌`를 stdout에 남기고, 하나라도 실패하면 **종료코드 1**로 끝낸다. done-check는 이 종료코드로 판정한다.
- 실패 시에만 `--shot` 경로에 스크린샷을 남겨 원인 추적을 돕는다.

#### 4.4.2 (2차) 사람 눈 확인 — `AGENTS.md:93` 요구

1차가 통과한 뒤에만 수행한다.

1. `wscript sns_hub.vbs` 또는 `npm run view`로 5000번 서버를 **재시작**한다.
2. `http://localhost:5000/`에서 유튜브 필터를 켠다.
3. 매핑 있는 카드에서 아이콘 3개를 확인하고 각각 클릭해 올바른 페이지가 열리는지 본다.
4. 매핑 없는 유튜브 카드, 유튜브 외 플랫폼 카드에 원본 아이콘만 있는지 본다.
5. 화면 캡처를 `_docs/evidence/20260828_02/`에 남긴다.

#### 4.4.3 evidence 산출물의 git 처리 — 커밋 포함으로 확정

`_docs/evidence/20260825_03/*.png`가 이미 git에 추적되고 있다(`git ls-files` 확인). 반면 `_docs/evidence/20260828_01/`은 `.git/info/exclude`에 로컬 제외돼 있어 실태가 갈린다.

**이번 산출물은 추적(커밋 포함)으로 확정한다.** 근거는 다음과 같다.

- 뷰어 UX 변경의 근거 자료이고, 나중에 회귀가 났을 때 "그때는 이렇게 보였다"를 확인할 수 있어야 한다.
- 다수 선례가 추적 쪽이다.
- `.gitignore`에 `_docs/evidence` 관련 규칙이 없어 별도 조치 없이 추적된다.

캡처는 4.4.2에서 얻은 것만 넣는다. 1차 headless 실패 스크린샷은 디버그용이므로 커밋하지 않는다.

### 4.5 중복 실행 가드 검증

- 실행 중 상태를 만든 뒤 두 번째 `POST /api/run-scrap`이 409를 받는지 확인한다.
- 두 번째 요청이 `total_scrap.py` 프로세스를 띄우지 않았는지 확인한다.
- 정상 종료 후 다음 실행이 다시 허용되는지 확인한다.

---

## 5. 남은 리스크

| 리스크 | 완화 |
|---|---|
| 비공식 내부 API 2개 의존. 스키마 변경 시 조용히 깨짐 | 수집 실패 시 **마지막 성공 매핑 파일을 유지**하고 아이콘만 갱신되지 않게 한다. 뷰어는 절대 죽지 않아야 한다 |
| LiveWiki 토큰 30일 만료 | `list`가 만료 7일 전부터 경고, 만료 후에는 명확한 안내와 함께 실패한다. 이미 구현됨 |
| Lilys "나만보기" 링크가 다른 브라우저에서 안 열릴 가능성 | 공유 링크는 로그아웃 상태에서도 열리는 것을 확인했으나 나만보기 링크는 미검증. 뷰어를 같은 브라우저에서 쓰므로 실사용 영향은 낮을 것으로 본다 |
| 아이콘 개수가 카드마다 달라 푸터가 들쭉날쭉 | 우측 정렬이라 오른쪽 끝은 고정된다. 시각 확인은 4.4에서 한다 |
| 매핑 28.3%가 낮게 느껴질 수 있음 | 나머지는 아이콘이 없을 뿐 기존 동작과 같다. 손해가 없다 |
| 409 가드의 stale 임계값이 실제 최장 수집 시간보다 짧으면 정상 실행 중 중복을 허용 | 3.3 T4에서 10800초로 확정. 관측 최대 13분 05초의 약 13배 여유다. `--mode all`이 3시간을 넘기면 그때 상수를 올린다 |

---

## 6. 실행 순서

**이 계획은 단일 세션 순차 실행이다. 병렬 실행하지 않으며 exec-plan을 쓰지 않는다.**
`T1 → T3 → T2`는 데이터 생산자 → 서빙 → 소비자 순서라 뒤집을 수 없다. `T4`·`T5`는 앞 단계와 파일이 겹치지 않지만, 검증을 한 번에 몰아 받기 위해 순차로 둔다.

1. **4.1 선행 작업 검증** — 이미 만든 수집기 2개와 문서가 정상인지 확인
2. T1 매핑 병합 스크립트 + U1~U3
3. T3 `/api/get-external-summaries` 엔드포인트 + U6~U7
4. T2 푸터 렌더 변경
5. T4 중복 실행 가드 + U4~U5
6. T5 `AGENTS.md` 죽은 지시 제거
7. 4.3 기존 테스트 전량
8. **4.4.1 headless 자동 판정** (`scripts/verify_external_summary_icons.mjs`, 종료코드 0)
9. 4.4.2 사람 눈 확인 + 캡처 (`_docs/evidence/20260828_02/`, 커밋 포함)
10. 4.5 가드 검증

---

## 7. 실행 결과 (2026-08-28 KST)

### 7.1 구현한 것

| 작업 | 파일 | 내용 |
|---|---|---|
| 선행 | `scripts/lilys_library.mjs` | Lilys 라이브러리 수집기. login / check-auth / list |
| 선행 | `scripts/livewiki_library.mjs` | LiveWiki 라이브러리 수집기. 같은 3-명령 구조 |
| T1 | `scripts/build_external_summaries.mjs` | 두 산출물 병합 → `web_viewer/sns_external_summaries.json` |
| T2 | `web_viewer/script.js` | `View Original` 제거, 아이콘화, `buildExternalSummaryLinks()` 추가, 카드에 `data-platform-id` 부여, 409 응답 처리 |
| T2 | `web_viewer/style.css` | `.footer-link-btn` 최소 24px 히트영역·focus outline |
| T3 | `scrap_sns_server.py` | `GET /api/get-external-summaries` 신설 (쓰기 짝 없음) |
| T3 | `web_viewer/script.js` | 초기 로드 `Promise.all`에 편입 |
| T4 | `scrap_sns_server.py` | `SCRAP_STALE_SECONDS=10800`, `_active_scrap_run()`, `_reset_scrap_progress()` 원자적 검사, `/api/run-scrap` 409 |
| T5 | `AGENTS.md` | 죽은 `build_data_js` 지시 2곳 제거, 신규 명령·산출물로 교체 |
| 부수 | `docs/architecture.md` | X producer 인증 실측 기록, 신규 라우트·409 동작 문서화 |
| 부수 | `.gitignore` | 신규 스크립트 4개 allowlist |
| 검증 | `scripts/verify_external_summary_icons.mjs` | headless V1~V6 |

### 7.2 테스트

| 대상 | 결과 |
|---|---|
| `node --test tests/unit/test_build_external_summaries.mjs` | ✅ 6/6 |
| `pytest tests/integration/test_external_summaries_api.py` | ✅ 4/4 |
| `pytest tests/integration/test_run_scrap_guard.py` | ✅ 5/5 |
| `pytest tests/unit tests/contract tests/integration` | 508 passed / **5 failed (전부 사전 실패)** |
| `node scripts/verify_external_summary_icons.mjs` | ✅ 6/6, 종료코드 0 |
| `node scripts/verify_youtube_viewer_headless.mjs` | 8/9 (S7 사전 실패) |

**사전 실패 5건은 이번 변경과 무관함을 stash 대조로 확인했다.**

| 실패 | 확인 방법 |
|---|---|
| `test_schemas.py::test_latest_total_links_existing_local_image_files` | `output_total`·`web_viewer/images` 미변경(`git diff --stat` 공백). 이미지 파일 mtime 2026-02-18 |
| `test_run_scrap_stats.py` 3건 | `scrap_sns_server.py` stash 후에도 동일 실패. 원인은 `youtube` 키가 stats 에 추가된 기존 변경 |
| `test_tag_management_ui.py::...browser_prompts` | `web_viewer/script.js` stash 후에도 동일 실패 |
| `verify_youtube_viewer_headless.mjs` S7 | `script.js`·`style.css` stash 후에도 동일 실패 (화면 2487 / 파일 2558) |

계약 테스트 2건(`test_all_code_routes_documented`, `test_route_count_is_pinned`)은 새 라우트 때문에 실패했고, `docs/architecture.md` 등록과 `EXPECTED_ROUTE_COUNT 17→18` 로 해소했다.

### 7.3 검증 결과

**매핑**: 영상 878건 (Lilys 156 · LiveWiki 742). `output_youtube` 460건과의 교집합 130건(28.3%).

**headless 판정 (4.4.1)** — 전부 통과.

```
대상 영상: XgGWUXVJzdg
✅ V1 푸터에 View Original 문자열이 없다
✅ V2 외부 요약 앵커의 href 가 올바른 도메인이다 — 앵커 18개, 잘못된 href 0개
✅ V4 유튜브 외 플랫폼 카드에는 외부 앵커가 없다 — 위반 0건
✅ V5 원본 보기 앵커가 카드마다 1개이고 라벨을 갖는다 — 카드 60개 중 위반 0건
✅ V6 외부 앵커가 붙은 카드 수가 매핑 교집합과 일치한다 — 화면 유튜브 60 / 매핑 교집합 18 / 앵커 카드 18
✅ V3 매핑에 없는 유튜브 카드에는 외부 앵커가 없다 — 매핑 없는 화면 유튜브 42건
✅ 6/6 검사 통과
```

**화면 캡처 (4.4.2)** — `_docs/evidence/20260828_02/`, 전부 headless 로 생성해 사용자 포커스를 빼앗지 않았다.

| 파일 | 내용 |
|---|---|
| `v1_기본화면_원본아이콘만.png` | 유튜브 외 플랫폼 카드에 원본 아이콘만 |
| `v2_유튜브필터_아이콘혼재.png` | 유튜브 필터에서 아이콘 있는/없는 카드 혼재 |
| `v3_매핑카드_아이콘상세.png` | Lilys + 원본 (`b9gFAGY_oMM`) |
| `v4_매핑없는카드_원본만.png` | 매핑 없는 유튜브 카드 (`sozxBiyc3qQ`, 외부 앵커 0) |
| `v5_아이콘3개_양쪽매핑.png` | **Lilys + LiveWiki + 원본** (`bWPXADZylm0`) |

`v5` 실측 앵커:

```json
[{"service":"lilys","href":"https://lilys.ai/digest/10719103","title":"Lilys 요약"},
 {"service":"livewiki","href":"https://livewiki.com/ko/content/312352b8-8d1d-4d91-84f8-1c0abcd29aaf","title":"LiveWiki 요약"},
 {"service":"original","href":"https://www.youtube.com/watch?v=bWPXADZylm0","title":"원본 보기"}]
```

**중복 실행 가드 (4.5)**: `tests/integration/test_run_scrap_guard.py` 5건이 실제 Flask 앱으로 검증했다 — 409 응답과 본문 필드, `Popen` 미호출, 진행 상태 미덮어씀, stale 회수, 임계값이 관측 최대의 10배 초과. 서버 재시작 후 새 엔드포인트가 응답하는 것으로 새 코드가 로드된 것도 확인했다.

실서버에서 중복 클릭을 재현하는 검증은 하지 않았다. `running=True` 를 만들려면 실제 수집을 몇 분간 돌려 output JSON 을 써야 하는데, 가드 자체는 위 테스트가 실제 앱으로 덮고 있어 비용이 이득을 넘는다.

### 7.4 계획과 달라진 것

| 항목 | 계획 | 실제 | 이유 |
|---|---|---|---|
| 카드 식별자 | 명시 없음 | `article[data-platform-id]` 추가 | headless 판정이 DOM 구조를 추측하지 않게 하려면 필요했다 |
| 검증 스크립트 동작 | 화면 로드 후 검사 | 유튜브 필터 + 스크롤로 매핑 카드를 화면에 올린 뒤 검사 | 첫 60건은 최신순이라 매핑 교집합이 0이었다. V2 가 무의미해진다 |
| 계약 테스트 | 언급 없음 | `EXPECTED_ROUTE_COUNT` 갱신 | 라우트 추가 시 필수 |

### 7.5 남은 리스크

- 비공식 내부 API 2개 의존. 수집 실패 시 마지막 성공 매핑을 유지하는 장치는 `build_external_summaries.mjs`에 들어갔다(입력 둘 다 없으면 기존 출력 미변경). 단 **API 응답 형태가 바뀌어 items 가 비는 경우**는 정상 수집으로 판정되어 매핑이 비워진다. 아이콘만 사라지고 뷰어는 살지만 원인 추적은 필요하다.
- LiveWiki 토큰 만료 2026-09-27. 그 전에 `login → check-auth` 재실행이 필요하다.
- 사전 실패 5건은 이번 범위 밖이라 손대지 않았다.
