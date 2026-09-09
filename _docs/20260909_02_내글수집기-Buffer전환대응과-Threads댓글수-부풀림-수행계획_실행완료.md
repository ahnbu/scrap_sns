---
title: 내 글 수집기 Buffer 전환 대응과 Threads 댓글수 부풀림 — 수행계획
created: 2026-09-09 13:20
session_id: 3e97a45d-e56a-4b50-a34d-01431958a1be
session_path: C:/Users/ahnbu/.claude/projects/D--vibe-coding-scrap-sns/3e97a45d-e56a-4b50-a34d-01431958a1be.jsonl
ai: claude
---

# 내 글 수집기 Buffer 전환 대응과 Threads 댓글수 부풀림 — 수행계획

- 작성일: 2026-09-09 (KST)
- 세션 ID: `3e97a45d-e56a-4b50-a34d-01431958a1be`
- 상태: **실행 완료** (2026-09-09) — 선행 [[20260909_01_LinkedIn진입점통합과-뷰어표시결함-수행계획_실행완료]]이 커밋 `94a96e9`(14:29)로 W1~W6 완료·푸쉬된 뒤 착수. 실행 결과는 §7
- 대상 레포: `D:\vibe-coding\scrap_sns`
- 연관 외부 레포: `D:\vibe-coding\sns_insight_update` (수정 대상 아님)

---

## 1. 상황 (Situation)

### 1.1 무슨 일이 있었나

`sns_insight_update` 레포가 2026-09-05 커밋 `7f9ca30`으로 SNS 성과 수집을 **Playwright DOM 스크래핑·Threads MCP → Buffer 공식 API**로 전면 교체했다. 옛 수집기는 `_archive/playwright_mcp_collectors/`로 이관됐고 폴백은 두지 않았다(그 레포의 판단이며 근거는 `_archive/playwright_mcp_collectors/README.md`에 있다 — 데이터 오염 방지).

`scrap_sns`는 그 레포의 수집기를 **import해서** 쓴다. 옛 모듈명·옛 인자를 그대로 부르고 있어 다음 실행부터 죽었다.

### 1.2 현재 상태 — 두 수집기가 동시에 사망

| 수집기 | 마지막 정상 | 실패 횟수 | 오류 | 로그 |
|---|---|---|---|---|
| MyPosts (LinkedIn 내 글) | 2026-09-05, 37건 | 4회 (9/6·9/8×2·9/9) | `No module named 'sns_insight_update.collectors.linkedin'` | `logs/myposts.log:139,161,183,205` |
| MyThreads (Threads 내 글) | 2026-09-05, 33건 | 4회 (동일 일자) | `No module named 'sns_insight_update.collectors.threads'` | `logs/mythreads.log:203,225,247,269` |

최초 보고는 MyPosts만이었다. 조사 중 MyThreads도 **같은 원인·같은 날짜·같은 횟수**로 죽어 있는 것을 확인했다.

### 1.3 왜 3일간 몰랐나

**뷰어 화면에는 정상으로 보이기 때문이다.** `merge_results()`가 "가장 최신 own 파일"을 읽는데, 9/5 파일이 남아 있어 오늘(9/9) 통합본에도 내 글 70건(LinkedIn 37 + Threads 33)이 그대로 들어간다. 건수가 줄지 않으니 눈으로 탐지할 수 없다. 지표만 9/5에 얼어붙어 있다.

콘솔에는 `❌ MyPosts ... 종료 (반환 코드: 1)`이 찍히지만([total_scrap.py](../total_scrap.py):539) 아무도 보지 않는다.

**확인 근거**: `output_total/total_full_20260909.json` — 총 2,880건 중 `is_own_post` 70건, source는 `my_insight_recent_activity` 37 / `my_insight_threads_api` 33.

---

## 2. 문제 (Complication)

### 2.1 함정 A — import만 고치면 데이터가 두 배가 된다 (LinkedIn만 해당)

Buffer 실행 후 기존 스냅샷과 비교한 결과다.

| 항목 | 옛 경로 | Buffer 경로 | ID 겹침 |
|---|---|---|---|
| LinkedIn | `urn:li:activity:7501590948603420672` | `urn:li:share:7501590947680591872`, `urn:li:ugcPost:...` | **0 / 37** |
| Threads | `Dc3LOziG3JK` (shortcode) | `Dc3LOziG3JK` (shortcode) | **33 / 33** |

LinkedIn은 식별자 체계가 통째로 바뀌었다(activity URN ↔ share/ugcPost URN은 같은 글의 서로 다른 번호이며 산술 변환 불가). `merge_own_post()`가 `platform_id`로 병합하므로 기존 37 + 신규 37 = **74건**이 되고, 회귀 가드 `check_regression()`은 *감소*만 막고 *증가*는 막지 않는다([my_posts_scrap.py](../my_posts_scrap.py):89-102). 뷰어에 내 글이 전부 중복 표시된다.

Threads는 이 문제가 없다.

### 2.2 함정 B — 지표 갱신이 조용히 두 번째로 죽는다 (LinkedIn만 해당)

내 글 URL이 `activity:` → `share:`로 바뀌면:

- [utils/linkedin_metrics.py](../utils/linkedin_metrics.py):43 `_ACTIVITY_ID_RE = re.compile(r"activity:(\d+)")` 매칭 실패
- [linkedin_metric_single.py](../linkedin_metric_single.py):131-132 `if not activity_id: continue` → **내 글 전건이 지표 대상에서 제외**

오류도, 실패 이력도 남지 않는다. ID 이관을 하지 않으면 여기서 두 번째로 조용히 죽는다.

### 2.3 함정 C — Threads 타래글이 댓글수로 세진다 (신규 발견, Buffer 무관)

Buffer `replies`와 기존 `comment_count`를 33건 전건 비교한 결과 **차이 0**. 즉 옛 Graph API 경로도 똑같이 셌다. 둘 다 Threads API의 `replies_count`를 그대로 받는데, 그 값이 **내가 쓴 타래글(자기 답글)을 포함**한다.

| 게시일 | 본문 이어붙인 타래글 | 기존 `comment_count` | Buffer `replies` |
|---|---|---|---|
| 2026-07-03 | 1개 | 1 | 1 |
| 2026-03-03 | 1개 | 1 | 1 |
| 2026-02-19 | 1개 | 1 | 1 |
| 2026-01-18 | 1개 | 1 | 1 |
| 2026-01-12 | 1개 | 1 | 1 |
| 2025-12-26 | 1개 | 1 | 1 |

위 6건은 **외부 댓글이 0인데 화면에 "댓글 1"로 표시된다.**

- 부풀림 규모: 최소 22건 (9/5 기준 타래글이 있던 글 수, `logs/mythreads.log:156-177`)
- 실제로는 더 클 수 있다 — 본문 이어붙이기는 *원글 후 30분 이내* 자기 답글만 고르지만([utils/my_threads_adapter.py](../utils/my_threads_adapter.py):100-138), 30분 뒤에 쓴 자기 답글도 `replies_count`에는 들어간다
- **LinkedIn은 반대 방향**이다. Buffer 댓글수가 비로그인 경로보다 *낮다*(76↔78, 176↔178, 12↔15 — 대댓글 미포함 추정). 플랫폼별로 셈법이 달라 하나의 규칙으로 못 묶는다

이것은 이번 사고와 **무관한 선행 결함**이다. 복구(원래대로)와 정정(원래도 틀렸던 것)을 한 단계에 섞으면 복구 성공 판정 기준이 흐려지므로 분리한다.

### 2.4 그런데 급하지 않다 — 지연 비용 실측

| 질문 | 답 | 근거 |
|---|---|---|
| 데이터가 영구히 사라지나? | **아니다** | Buffer가 2025-12부터 전 기간 누적 지표를 지금도 전건 제공(LinkedIn 37/37, Threads 34/34 실측) |
| 무엇이 손실되나? | 9/6~복구일 사이 **일별 스냅샷 파일** | 누적 지표라 곡선의 중간 점만 비고 시작·끝은 남는다 |
| 지금 고치면 무엇이 위험한가? | ~~`total_scrap.py` 동시 편집~~ **해소됨** | 01 계획이 2026-09-09 14:29 커밋 `94a96e9`로 W1~W6 전부 완료·푸쉬했다. 착수 조건 충족 |

---

## 3. 해결 (Resolution)

### 3.0 착수 조건

**[[20260909_01_LinkedIn진입점통합과-뷰어표시결함-수행계획_실행완료]](6웨이브)이 종료된 뒤 착수한다.**

그 계획 §10이 이미 이 결함을 「이번 범위 밖으로 둔 발견」으로 기록해 뒀다(MyPosts·MyThreads 두 슬롯, 원인, 이번 계획에 넣지 않는 이유 3가지). **동결 사실이 이미 문서화돼 있으므로 별도 조치가 필요 없다.** 다만 그 §10 마지막 줄 *"감시 설계를 넓힐지는 W5 완료 후 별건으로 판단한다"*에 본 문서를 이어 붙이면 추적이 끊기지 않는다.

W5(감시) 설계 시 **이번 사망 유형을 감시 대상에 넣을지 판단한다** — *외부 레포의 모듈이 사라져 import가 실패하고, 낡은 스냅샷이 계속 병합되어 화면상 정상으로 보이는 상태*. 01 계획의 `SNS_TOOL_UNAVAILABLE` 신호(W5 T5-a)와 성격이 같지만 발신 지점이 다르다 — 저쪽은 외부 도구 미기동, 이쪽은 외부 모듈 소멸이다.

### 3.1 작업 단위

우선순위 순이다. P1까지가 "복구", P2가 "정정"이다.

| # | 우선 | 대상 | 작업 | 규모 |
|---|---|---|---|---|
| T1 | P0 | [my_posts_scrap.py](../my_posts_scrap.py):117-124 | import를 `collectors.buffer_cli`로 교체. `scrolls`·`headed` 인자 제거, `AuthRequired` → `BufferAuthRequired`. `--scrolls` CLI 인자도 함께 제거 | ~20줄 |
| T2 | P0 | [my_threads_scrap.py](../my_threads_scrap.py):120-124 | 동일. `ThreadsAuthRequired` → `BufferAuthRequired` | ~15줄 |
| T3 | P0 | 신규 `scripts/migrate_own_linkedin_ids.py` | 9/5 스냅샷 37건의 `platform_id`·`code`·`url`을 신규 share/ugcPost URN으로 이관. 조인 키는 **게시 시각(분 단위)** — 실측 37/37 매칭, 중복 분 0건. 사용자 메타데이터 충돌 0건 확인함 | ~50줄 |
| T4 | P0 | [utils/linkedin_metrics.py](../utils/linkedin_metrics.py):41-43 | `_ACTIVITY_ID_RE`가 share·ugcPost URN도 받도록 확장, `POST_URL_TEMPLATE` 분기. **또는** 내 글을 지표 대상에서 제외(T6 결정에 종속) | ~10줄 |
| T5 | **P0** | [utils/my_threads_adapter.py](../utils/my_threads_adapter.py):216-232 | 🔴 **기존 합본 보존.** `full_text`·`is_merged_thread`를 보존 필드로 지정해 Buffer의 짧은 본문이 덮지 못하게 한다. LinkedIn 쪽 `NON_LOGIN_PATH_METRIC_FIELDS`와 같은 패턴 | ~15줄 |
| T5-b | P1 | [my_threads_scrap.py](../my_threads_scrap.py):136-190 | `collect_continuations()`·`fetch_replies()` 제거 (archive된 `threads_mcp_runner` 의존). 신규 글의 타래글은 §4.3 결정대로 **당분간 수집하지 않는다** | ~40줄 삭제 |
| T6 | P1 | [total_scrap.py](../total_scrap.py):480-482 | `&& linkedin_metric_single.py --only own` 유지 여부 결정 (§4.2). **결론: 유지** | 주석만 |
| T7 | P1 | [utils/my_posts_adapter.py](../utils/my_posts_adapter.py):8-12, [my_posts_scrap.py](../my_posts_scrap.py):8-11 | "이 경로만 노출수를 준다"·"반응수는 상위 몇 건만" 전제가 거짓이 됐다. 주석 정정 | 문서 |
| T8 | P2 | `utils/my_threads_adapter.py` | 댓글수 타래글 부풀림 정정. **이번 범위 밖 — 백로그**(§4.3 재검토 조건에 종속) | 이번엔 0 |
| T9 | P0 | 신규 `scripts/verify_own_posts_headless.mjs` | 뷰어 화면 검증 스크립트 신설. 창을 띄우지 않고 단언 4개를 종료코드 0/1로 판정한다. 요건은 §5 8번 | ~120줄 |

### 3.2 T3 이관 방식 상세

```
기존 37건 (activity URN)          Buffer 37건 (share/ugcPost URN)
  created_at 분 단위 키      ←→      created_at 분 단위 키
```

- 실측: 37/37 매칭, 기존 파일 내 중복 분 0건
- 본문 대조는 쓸 수 없다 — 옛 DOM 카드 본문이 잘려 있어 60자 접두사 일치가 4/37뿐
- `web_viewer/sns_user_metadata.json` 20건 중 내 글 관련 **0건** → 별표·숨김·메모 유실 없음
- 이관 후 `linkedin_own_full_20260905.json`은 원본 보존하고 새 날짜 파일로 저장한다

---

## 4. 검토한 옵션과 기각 근거

### 4.1 옛 Playwright·MCP 수집기를 되살릴 것인가 → **기각**

> 01 계획 §4.1의 `R2`(3번째 wave 되돌리기)와는 **다른 사안**이다. 여기서 다루는 것은 「Buffer 전환 자체를 되돌릴 것인가」다. R2와의 관계는 §4.5에 따로 적었다.

되살리자는 논거는 "내 글 수집이 깨졌다"였다. 그러나 실측 결과 Buffer 경로가 옛 경로보다 **데이터가 더 좋다.**

| 게시일 | 옛 노출수 | Buffer | 옛 반응 | Buffer | 옛 댓글 | Buffer |
|---|---|---|---|---|---|---|
| 2026-05-05 | 41,958 | 41,971 | 350 | 350 | 15 | 12 |
| 2026-04-23 | 11,651 | 11,654 | 130 | 130 | 8 | 8 |
| 2026-03-26 | 6,780 | 6,786 | 65 | 65 | 178 | 176 |
| 2026-07-24 | 6,998 | 7,000 | 60 | 60 | 1 | 1 |

- 노출수·반응수·댓글수 **37/37 전건 채움**. 옛 로그인 카드는 반응수를 5/36만 줬다(그래서 비로그인 경로를 따로 붙였던 것)
- 반응수는 비로그인 경로 값과 **완전 일치**
- 창이 뜨지 않고 세션 만료도 없다(API 키 1개)

깨진 것은 수집 방식이 아니라 **호출부가 외부 레포 변경을 따라가지 못한 것**이다.

> **사실 정정 필요**: "consumer 묶음에서 로그인 브라우저가 안 뜬다"는 서술은 부정확하다. 원래도 뜨지 않았다 — `my_posts_scrap.py:124`가 `headed=False` 고정이었고, 같은 웨이브의 `linkedin_metric_single.py`는 애초에 비로그인 경로다([total_scrap.py](../total_scrap.py):409-411). 정확히는 **"로그인 세션(storage_state)을 쓰는 경로가 consumer 웨이브에서 사라졌다"**이다.

### 4.2 T6 — 내 글 비로그인 지표 수집을 없앨 것인가 → **일단 유지**

Buffer 반응수가 비로그인 경로와 정확히 일치하므로 없앨 수 있다. 하지만:

- 댓글수가 2~3 낮다(대댓글 미포함 추정). 원인을 확인하지 않은 채 없애면 값이 조용히 바뀐다
- 이번 작업은 복구다. 변수를 하나라도 줄이는 편이 낫다

→ 유지하되 T4에서 URN 정규식을 확장한다. 제거는 별건으로 다시 잰다.

### 4.3 Threads 타래글 — **Buffer 단독으로 가고, 기존 합본은 보존한다** (2026-09-09 확정)

**결정: 새 타래글 수집을 당분간 하지 않는다. 대신 이미 저장된 합본을 지키는 것을 P0로 올린다.**

#### 실측으로 확인한 것

| # | 확인 | 결과 |
|---|---|---|
| 1 | Buffer `posts list`의 필드 92개 | 타래글 본문 필드 **없음** |
| 2 | Buffer `posts get`의 필드 183개 | **`metadata.thread.text` 있음** |
| 3 | `via: buffer` 글(타래 3개)에 2번을 적용 | **3조각 전부 반환**(208·414·430자) |
| 4 | `via: network` 글에 2번을 적용 | `thread: []`, `threadCount: 0` — 백엔드에 데이터 자체가 없음 |
| 5 | 내 Threads 글 34건의 발행 경로 | `network` 32건 / `buffer` 2건 |
| 6 | archive된 MCP 실행기 동작 | **10회 호출 10회 성공**, 중앙 0.7초. 프로세스는 안정적 |
| 7 | Threads 토큰 | 현재 유효(HTTP 200). 단 **약 60일 만료 + 수동 갱신**, 자동 갱신 훅 없음 |
| 8 | 9/5 파일 | 타래 합본 **22건 / 16,480자가 이미 저장돼 있음** |

#### 기각한 안

| 안 | 기각 근거 |
|---|---|
| Buffer 웹사이트를 `browser-automate`로 긁는다 | 웹 화면은 API와 **같은 백엔드**를 읽는다. 4번에서 `via: network` 글의 타래 데이터가 백엔드에 없음이 확인됐다 — 로그인해도 나올 게 없다. (API 응답 근거이며 화면 직접 확인은 하지 않았다) |
| archive된 MCP 실행기를 복사해 계속 쓴다 | 6번대로 프로세스는 안정적이지만 7번의 토큰 운영 부담이 그대로 돌아온다. 옆 레포가 Buffer로 옮긴 이유 중 하나가 이것이다. **보류이지 기각은 아니다** — 아래 재검토 조건 참조 |
| Threads Graph API 직접 호출 | 위와 같은 토큰 부담. MCP보다 나을 게 없다 |

#### 그래서 무엇이 남는가

| 대상 | 처리 |
|---|---|
| 과거 22건 | **이미 저장돼 있다.** 다시 가져올 필요 없이 **덮어쓰지만 않으면 된다** → T5 |
| 앞으로 Buffer로 발행하는 글 | `metadata.thread.text`로 자동 수집 가능 (이번 범위 밖, 필요해지면 추가) |
| 앞으로 쓰레드 앱에서 직접 발행하는 글 | **당분간 타래글을 수집하지 않는다.** 필요하면 그때 수동으로 채운다 |

#### 🔴 T5를 P0로 올리는 이유

현재 [`merge_own_post()`](../utils/my_threads_adapter.py):216-232는 **`None`이 아닌 incoming 값이 무조건 이긴다.** Buffer는 타래글 없는 짧은 본문을 주므로, 손대지 않고 복구하면 그 자리에서 합본이 덮인다.

| | |
|---|---|
| 지금 저장된 본문(22건) | 16,480자 |
| Buffer가 주는 본문 | 9,352자 |
| **덮어쓰면 손실** | **7,128자 (43%)** |

「나중에 채운다」는 선택은 **지금 있는 것을 지켜야만** 성립한다. 그래서 이것만 P0다.

#### 재검토 조건

쓰레드 앱 직접 발행이 계속되어 타래글 결손이 쌓이면 다시 본다. 그때의 후보는 둘이다.

1. archive된 MCP 실행기 복사 + **토큰 자동 갱신 훅 추가**(7번이 유일한 약점이므로 그것만 없애면 된다)
2. 레포에 이미 있는 공개 페이지 수집기 재사용 — [thread_scrap_single.py](../thread_scrap_single.py):87-110 `merge_thread_items()`가 타래를 합친다. **토큰이 필요 없다.** 다만 저장글 파일 구조에 묶여 있어 배관 작업이 필요하다

**T8(댓글수 정정)은 P2로 남긴다.** 정정하려면 자기 답글 수를 알아야 하는데 그 경로가 위 재검토와 같다. 정정 방식은 `comment_count = replies_count - (내 답글 수)`이며, 30분 창 밖의 자기 답글도 빼야 하므로 옛 `select_continuations()`의 window 조건과는 다른 집계가 필요하다.

### 4.4 지금 즉시 착수 → **기각**

§2.4대로 데이터 영구 손실이 없고, `total_scrap.py` 충돌 위험이 실재하며, MyThreads 발견으로 범위가 2배가 됐다. 6웨이브 계획에 끼워 넣거나 병행할 크기가 아니다.

### 4.5 🔴 이 계획이 01 계획 §4.1(R2 기각)의 **근거를 무효화한다**

**결론을 뒤집는 것은 아니지만, 근거 문장은 바꿔야 한다.** 01 계획을 마감하기 전에 처리할 것.

01 계획 §4.1(N5)이 R2를 기각한 근거는 이렇다.

> *"통합 후에도 `BenchLinkedIn`은 별도 프로세스이고, consumer wave의 `MyPosts`와 **같은 LinkedIn 로그인 세션**을 쓴다([total_scrap.py:443-451](../total_scrap.py:443)). 같은 wave에 넣으면 같은 계정 세션 2개가 동시에 붙는다."*

**본 계획의 T1이 끝나면 이 문장이 거짓이 된다.** Buffer는 API 경로이므로 `MyPosts`가 LinkedIn 로그인 세션을 쓰지 않는다. 그러면 consumer wave에 LinkedIn 로그인 세션 사용자가 **한 명도 남지 않는다.**

| consumer 슬롯 | 로그인 세션 사용 | 근거 |
|---|---|---|
| `LinkedIn` (`--only saved`) | 아니오 | [total_scrap.py](../total_scrap.py):464 주석이 "로그인하지 않고 공개 페이지에서 읽는다"고 명시 |
| `MyPosts` | **현재 예 → T1 이후 아니오** | [total_scrap.py](../total_scrap.py):468-470 주석의 전제가 Buffer 전환으로 사라진다 |
| `Threads`·`X/Twitter`·`MyThreads` | 해당 없음 | 다른 플랫폼 |

즉 T1 이후 3번째 wave가 분리하는 대상은 「consumer의 MyPosts」가 아니라 **「producer의 `linkedin_scrap.py`」**로 바뀐다. 그 근거로도 3-wave는 여전히 정당하다 — 되돌려서 producer에 합치면 저장글 수집기와 벤치마킹 수집기가 같은 계정으로 동시에 붙는다.

| 처리 | 시점 |
|---|---|
| 01 계획 §4.1의 근거 문장을 「producer의 `linkedin_scrap.py`와의 충돌」로 교체 | **01 계획이 이미 마감돼(커밋 `94a96e9`) 문서 수정 시점을 놓쳤다.** 아래 두 줄의 코드 주석 갱신으로 갈음한다 |
| [total_scrap.py](../total_scrap.py):468-470 주석 갱신 (「producer의 `linkedin_scrap.py`도 로그인 세션을 쓰기 때문」 → Buffer 전환 반영) | 본 계획 T1 |
| [total_scrap.py](../total_scrap.py):499 주석 갱신 (「consumer 의 MyPosts 도 같은 세션을 쓰므로」 → 더 이상 사실이 아님. 3-wave 근거를 producer의 `linkedin_scrap.py`로 다시 쓴다) | 본 계획 T1 |
| `MyPosts`를 consumer에 계속 둘지 재검토 | 본 계획 T6와 함께. **권장: 그대로 둔다** — 옮길 이득이 없고, `linkedin_metric_single.py --only own`과의 직렬화(`&&`)는 여전히 필요하다 |

---

## 5. 완료 판정 기준

프로세스 성공이 아니라 **저장 데이터와 뷰어 반영의 일치**로 판정한다.

1. `pytest tests/unit` 통과 — 특히 `test_linkedin_metric_single_scope.py`, `test_total_scrap_orchestration.py`, `test_total_scrap_redirect_alias.py`
2. `python my_posts_scrap.py` → 저장 건수 **37건** (74건이면 T3 실패)
3. `python my_threads_scrap.py` → 저장 건수 33건 이상, 노출수 보유 전건
3-a. 🔴 **합본 보존 확인** — 실행 후 `is_merged_thread == True`인 22건의 `full_text` 총 길이가 **16,480자 이상**이고, `is_merged_thread`가 `False`로 뒤집힌 글이 **0건** (T5 실패 시 9,352자로 떨어진다)
4. `linkedin_metric_single.py --only own` → 대상 건수 0건이 아님 (0이면 T4 실패)
5. `merge_results()` → `download_images()` → `validate_local_image_links()` 통과
6. 최신 통합본(`output_total/total_full_*.json` 중 파일명 최신)의 `is_own_post` 건수 = **70건 이상 80건 이하** (140건 근처면 T3 실패로 중복된 것)
7. ~~웹 뷰어 상단 총건수와 최신 JSON 게시글 수 일치~~ → **전제가 틀려 기준을 바꿨다(2026-09-09 구현 중 확인).**

   상단 라벨은 총계가 아니라 **지금 화면에 걸린 수**다([web_viewer/script.js](../web_viewer/script.js):342-364, `updateTotalPostsLabel(visibleCount)` — 주석이 "지금 화면에 몇 개가 걸렸는지만 말한다"고 밝히고 계획 `20260827_05` T5 를 근거로 든다). 비활성 벤치마킹 계정 글과 숨김 글이 [`isBenchmarkVisible()`](../web_viewer/script.js):2620 에서 빠지므로 파일보다 작은 것이 **정상**이다. 실측 2026-09-09: 파일 2,882 vs 라벨 2,804(차이 78).

   → 바뀐 기준: **뷰어가 실제로 읽는 `/api/posts` 응답 건수 == 최신 통합본 게시글 수.** 「데이터가 다 실렸는가」를 재는 올바른 지점이다. 8번 스크립트의 단언 C 가 이것을 본다.

   ⚠️ 같은 잘못된 전제 위에 선 기존 스크립트 `scripts/verify_viewer_total_count_headless.mjs` 도 지금 실패한다(파일 2,882 vs 라벨 2,804). **이번 변경이 깨뜨린 것이 아니다** — 벤치마킹 가시성 규칙(`20260906_01` D9)과 ALL 정책(`20260909_01` W3 T3-e)이 들어오면서 전제가 낡았다. 이번 범위 밖이라 고치지 않고 남긴다.
8. **`scripts/verify_own_posts_headless.mjs`를 신설**한다. 이 레포에 내 글 전용 검증 스크립트가 없어 재사용할 대상이 없다(현재 `scripts/verify_*.mjs` 19개 중 own/my 대상 0개)

**8번 스크립트 요건** — 기존 형식을 그대로 따른다(`verify_benchmark_mainview.mjs` 파일 끝 `process.exit(failed.length ? 1 : 0)`).

| 항목 | 요건 |
|---|---|
| 실행 기반 | `C:/Users/ahnbu/.claude/skills/_shared/hidden-browser-verify-runner.mjs` — **창을 띄우지 않는다**. 창이 필요한 예외 없음 |
| 판정 | 항목마다 `record(...)`로 참/거짓을 세고 **종료코드 0/1**로 끝낸다. `done-check`가 사람 눈 없이 종료코드만으로 판정할 수 있어야 한다 |
| 단언 A | 「MY」 필터를 켠 뒤 렌더된 카드의 `platform_id`에 **중복 0건** (T3 실패 시 LinkedIn 글이 2배로 뜬다) |
| 단언 B | MY 카드 수 == 최신 통합본의 `is_own_post` 건수 |
| 단언 C | 뷰어 상단 총건수 == 최신 통합본 게시글 수 (7번) |
| 단언 D | `is_merged_thread == true`인 Threads 내 글 카드의 본문 길이 합 **≥ 16,480자** (3-a를 화면에서 재확인) |
| 캡처 | `_docs/evidence/20260909_02/` **하위**에 저장하고 **커밋에 포함한다.** `.gitignore:199-200`의 `_docs/evidence/*.png`·`*.log`는 최상위만 매칭하므로 하위 폴더는 추적된다(현재 126개 추적 중). 캡처는 증거의 보조이지 판정 근거가 아니다 — 판정은 종료코드다 |
| 실행 전제 | `npm run restart`로 5000번 서버를 새로 띄운 뒤 실행한다 |

---

## 6. 참조

- 외부 레포 전환 커밋: `sns_insight_update` `7f9ca30` (2026-09-05)
- 외부 레포 부활 절차: [[sns_insight_update/_archive/playwright_mcp_collectors/README]]
- Buffer 수집기 정본: `sns_insight_update/src/sns_insight_update/collectors/buffer_cli.py`
- **선행 계획(진행 중)**: [[20260909_01_LinkedIn진입점통합과-뷰어표시결함-수행계획_실행완료]]
  - §10이 본 결함을 「이번 범위 밖으로 둔 발견」으로 기록했다 — 본 문서가 그 후속이다
  - §4.1(R2 기각)의 근거를 본 계획 T1이 무효화한다 → §4.5
  - W5(자막 감시)와 사망 성격이 같다 → §3.0
- 원 설계 계획: [[20260826_03_내-게시물-성과지표-통합-수집-계획_실행완료]], [[20260827_04_내-글-정렬-두-플랫폼-병합-계획_실행완료]]
- 관련 선행 계획: [[20260825_01_LinkedIn-참여지표-비로그인-수집전환-계획_실행완료]], [[20260827_02_내-쓰레드-글-수집-계획_실행완료]]

---

## 7. 실행 결과 (2026-09-09)

### 7.1 무엇이 바뀌었나

| 작업 | 파일 | 한 일 |
|---|---|---|
| T1 | [my_posts_scrap.py](../my_posts_scrap.py) | `collectors.linkedin` → `collectors.buffer_cli`. `scrolls`·`headed` 인자와 `--scrolls` CLI 옵션 제거. `AuthRequired` → `BufferAuthRequired`, 신호 사유 `login_required` → `buffer_api_key_required` |
| T2 | [my_threads_scrap.py](../my_threads_scrap.py) | 동일. `fetch_replies()`·`collect_continuations()`·`REPLY_FIELDS` 제거(T5-b), 진입 로그 「Graph API」→「Buffer API」 |
| T3 | 신규 [scripts/migrate\_own\_linkedin\_ids.py](../scripts/migrate_own_linkedin_ids.py) | 게시 시각(분) 조인으로 activity URN → share/ugcPost URN 이관. dry-run 기본, `--apply` 로 저장. 원본 파일은 지우지 않는다 |
| T4 | [utils/linkedin_metrics.py](../utils/linkedin_metrics.py) | `_ACTIVITY_ID_RE` 가 `share`·`ugcPost` 도 받는다. `build_post_url()` 이 URN 종류를 되돌린다 |
| T5 | [utils/my\_threads\_adapter.py](../utils/my_threads_adapter.py) | `keep_existing_body()` 신설 — 기존이 합본이고 새 본문이 짧으면 본문을 지킨다. `BLANK_GUARDED_FIELDS`(`is_merged_thread`·`media`)는 빈 값이 기존 값을 못 덮게 한다 |
| T6·T7 | [total_scrap.py](../total_scrap.py):468·499, [utils/my\_posts\_adapter.py](../utils/my_posts_adapter.py) | 낡은 전제 주석 정정(§4.5). `&&` 직렬화는 유지 |
| T9 | 신규 [scripts/verify\_own\_posts\_headless.mjs](../scripts/verify_own_posts_headless.mjs) | 창 없이 단언 5건, 종료코드 0/1 |
| — | [.gitignore](../.gitignore):112-114 | `scripts/` 는 명시 허용 목록 방식이라 새 스크립트 2개를 등록 |
| — | `tests/unit/test_my_threads_adapter.py`, `tests/unit/test_linkedin_metrics.py` | 가짜 수집기 모듈명 교체 + **신규 12건**(T5 보존 4건, T4 URN 8건) |

### 7.2 검증 결과

| # | 기준 | 결과 |
|---|---|---|
| 1 | `pytest tests/unit tests/contract` | **547 passed** (착수 전 522) |
| — | `pytest tests/smoke` | **6 passed** |
| 2 | my_posts 저장 건수 37 (74면 T3 실패) | **37건** |
| 3 | my_threads 33건 이상·노출수 전건 | **34건 / 노출수 34건** |
| 3-a | 합본 22건·16,480자 이상·뒤집힘 0 | **22건 / 16,480자 / 뒤집힘 0** |
| 4 | `linkedin_metric_single.py --only own` 대상 0건 아님 | **대상 2건** (T4 이전이면 0건) |
| 5 | `merge_results()`→`download_images()`→`validate_local_image_links()` | 통과. 통합본 2,882건 저장 |
| 6 | 통합본 `is_own_post` 70~80 | **71건** (LinkedIn 37 + Threads 34), 식별자 중복 0 |
| 7 | (기준 변경 — 위 §5-7 참조) `/api/posts` == 통합본 건수 | **2,882 == 2,882** |
| 8 | `node scripts/verify_own_posts_headless.mjs` | **종료코드 0**, 단언 5건 전부 통과 |

캡처: `_docs/evidence/20260909_02/my_posts_no_duplicates.png` (커밋에 포함)

### 7.3 실행 중 드러난 것

**(1) 계획의 완료 기준 7번 전제가 틀렸다.** 뷰어 상단 라벨은 총계가 아니라 화면에 걸린 수다. 기준을 `/api/posts` 대조로 바꿨고 근거를 §5-7 에 남겼다. 같은 전제 위에 선 기존 스크립트 `scripts/verify_viewer_total_count_headless.mjs` 도 실패하지만 **이번 변경이 깨뜨린 것이 아니라** 벤치마킹 가시성 규칙이 들어오며 낡은 것이다. 범위 밖이라 고치지 않았다.

**(2) 내 글 지표 갱신 2건이 `no-metrics-in-dom` 으로 실패한다.** URN 변경 탓이 아니다 — 같은 두 글이 옛 activity URL 로도 **3회씩 실패**했고 마지막이 2026-08-28 이다(`scrap_failures_linkedin.json`). 새 URN 이 정상 동작하는 것은 양성 대조로 확인했다: `share:7501590947680591872` → 8/2, `ugcPost:7497904074101723136` → 21/78, `share:7486376409331019776` → 60/1.

**(3) Threads 리포스트 판정이 무력화됐다.** `is_repost()` 는 `raw.thread.media_type` 을 보는데 Buffer 레코드에는 그 필드가 없어 항상 거짓이다. 실측 34건에 리포스트가 없어 지금은 영향이 없다. 코드에 주석으로 남겼다([my_threads_scrap.py](../my_threads_scrap.py) `main()`).

**(4) 이미지 18건 다운로드 실패.** Threads CDN URL 은 만료 토큰(`oe=...`)을 달고 있어 9/5 수집분이 이미 만료됐다. `validate_local_image_links()` 는 통과했고(선언한 로컬 파일이 다 있다) 이번 변경과 무관하다.

### 7.4 남은 리스크

| 리스크 | 상태 |
|---|---|
| 쓰레드 앱에서 직접 올리는 새 글의 타래글이 안 붙는다 | **의도한 결정**(§4.3). 34건 중 32건이 그 경로라 결손이 쌓인다. 재검토 조건과 후보 2개는 §4.3 에 있다 |
| 내 글 댓글수가 자기 답글만큼 부풀려져 있다 | T8, 백로그. 선행 결함이라 이번 복구와 무관 |
| `verify_viewer_total_count_headless.mjs` 실패 | 선행 결함. 위 (1) |

**(5) 🔴 식별자 이관이 태그 키를 고아로 만들었다 — 완료검수 Advisory 추적 중 발견.** 계획 §3.2 는 사용자 상태 영향을 `web_viewer/sns_user_metadata.json`(별표·숨김·메모)만 확인했다. **태그는 `web_viewer/sns_tags.json` 에 URL 을 키로 따로 저장된다** — 이 파일을 이관 전에 보지 않았다.

| 실측 (2026-09-09) | 값 |
|---|---|
| 옛 activity URL 을 키로 하는 내 글 태그 항목 | 34건 |
| 그중 고아(가리키는 글이 통합본에 없음) | **33건**, 태그 92개 |
| **태그 손실** | **0건** — 옛 URL 에 있던 태그가 새 URL 에 전부 있다(30/30, 부분집합 판정) |

손실이 0인 이유는 이관 로직이 태그를 옮겼기 때문이 **아니다.** 뷰어가 데이터 변경을 감지하면 자동 태그 규칙을 다시 돌리는데([web_viewer/script.js](../web_viewer/script.js):2442 `applyAutoTagRules`), 본문이 같으니 새 URL 에도 같은 태그가 규칙으로 **재생성**됐다. 이번 검증에서 뷰어를 띄운 것이 그 방아쇠였다.

⚠️ **규칙으로 재생성될 수 없는 태그(손으로만 붙인 태그)였다면 옮겨지지 않았을 것이다.** 이번에는 실측상 빠진 것이 없지만, 운이 좋았던 것에 가깝다. 같은 종류의 식별자 이관을 다시 할 때는 `sns_tags.json` 도 이관 대상에 넣어야 한다.

고아 33건은 지금 아무 화면에도 영향을 주지 않는다(가리키는 글이 없다). **사용자 태그 데이터라 임의로 지우지 않았다.** 정리 여부는 사용자 판단으로 남긴다.
