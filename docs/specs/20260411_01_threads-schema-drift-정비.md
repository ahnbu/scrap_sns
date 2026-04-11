---
title: Threads 스키마 drift 정비 + 재발방지 인프라
created: 2026-04-11 17:47

session_id: 54973faf-dfdf-4f72-9cf5-edd416fd5394
session_path: C:/Users/ahnbu/.claude/projects/D--vibe-coding-scrap-sns/54973faf-dfdf-4f72-9cf5-edd416fd5394.jsonl
updated_sessions:
  - 54973faf-dfdf-4f72-9cf5-edd416fd5394
plan: C:/Users/ahnbu/.claude/plans/temporal-weaving-hartmanis.md
ai: claude
---

# Threads 스키마 drift 정비 + 재발방지 인프라

## 목적

웹 뷰어에서 Threads 게시물의 88%가 사용자명 "Unknown" + 원본 링크 깨짐(`href="#"`)으로 표시되고 있다. 표면만 고치면 같은 drift가 계속 재발하므로, 이번 수정을 계기로 데이터 정합성 유지 장치를 함께 심어 재발 고리를 끊는다.

단, 프로젝트는 1인 사용이고 LinkedIn/X/Substack은 건전함이 확인됐으므로, 과대한 리팩터링·리라이트는 배제한다. 정비는 Threads 파이프라인과 공용 스키마 유틸 범위로 한정한다.

### 배경
- 사용자 체감: "프로젝트가 중구난방 스파게티". 고치면 재발 안 되게 정리되기를 원함.
- 1차 진단: 설계 자체는 건전. `STANDARD_FIELD_ORDER`가 CLAUDE.md에 정의되어 있고 신규 Producer 코드는 이를 준수. 다만 (1) 과거 backfill 경로가 레거시 레코드를 양산했고, (2) 마이그레이션이 실행되지 않아 누적됐으며, (3) 뷰어는 레거시 fallback이 없어 "Unknown"으로 노출됨.
- 이 3개 층이 맞물려 체감상 "스파게티"로 보이지만, 실제로는 **drift 1종과 안전망 부재 1종**의 합.

## 요구사항

무엇을 달성해야 하는가 (what + why):

- **R1.** 웹 뷰어의 Threads 카드 사용자명이 더 이상 "Unknown"으로 표시되지 않아야 한다.
  - *why*: 카드 식별 불가 → 실질적으로 88%가 내용만 있고 누구 글인지 모름.
- **R2.** 웹 뷰어의 Threads 카드 "View Original" 링크가 실제 threads.net 원본으로 이동해야 한다.
  - *why*: 저장한 게시물을 다시 확인할 경로 자체가 차단됨.
- **R3.** 공용 스키마 유틸(`validate_post`, `normalize_post`)을 신설해 Post dict의 단일 진실 원천을 확립한다.
  - *why*: CLAUDE.md 리스트·migrate_schema.py·각 스크래퍼가 각자 필드를 알고 있어 drift가 반복됨.
- **R4.** 현재 누적된 레거시 Threads 레코드 583건을 표준 스키마로 정본 교정한다.
  - *why*: 뷰어 fallback으로만 덮으면 검색·필터·즐겨찾기 키가 불일치해 기능이 반쪽으로 남음.
- **R5.** Threads Producer/Consumer/backfill 경로가 표준 스키마를 위반하면 **저장 전에** 실패 또는 자동 정규화되도록 게이트를 심는다.
  - *why*: 재발 방지의 핵심. 경로가 3개인데 각자 따로 필드를 쓰면 drift가 되돌아옴.
- **R6.** 뷰어 fallback 안전망을 유지하되, 데이터 정합 후에는 발동하지 않도록 한다.
  - *why*: 미래 drift의 조기 감지용. 정상 데이터면 fallback이 동작하지 않으므로 "Unknown"이 보이면 즉시 원인 조사.
- **R7.** 작업 전 상태를 이중 백업(git archive 브랜치 + 폴더 복사)하여 롤백 가능성을 확보한다.
  - *why*: 1인 사용이고 데이터 유실이 SNS 저장 해제로 직결되므로 안전망 필수.
- **R8.** `web_viewer/convert_data.py`처럼 하드코딩된 경로의 유령 스크립트를 정리해 혼란 요소를 제거한다.
  - *why*: "누가 어떤 스크립트로 data.js를 만드는가"가 모호하면 또다시 drift가 은밀히 들어옴.

## 성공 기준

완료 판단은 다음 7가지가 모두 참이어야 한다:

1. 웹 뷰어 기동 후 Threads 필터 선택 → DOM `article h3` 중 "Unknown" 카운트 = **0**.
2. 무작위 Threads 카드 5장의 "View Original" 링크가 `https://www.threads.net/@{user}/post/{code}` 형식으로 이동하고 원본 페이지가 로드됨.
3. `validate_post`를 `output_total/total_full_*.json`의 전 레코드(975건)에 돌려 누락 필드 리스트가 **모두 빈 배열**.
4. `git diff`로 확인 시 LinkedIn/X/Substack 관련 코드·데이터는 변경 없음 (회귀 없음 보장).
5. 소규모 재수집(`python thread_scrap.py --mode update --limit 5`) 실행 후 신규 레코드 5건이 전부 표준 스키마로 저장됨.
6. `archive/pre-cleanup-20260411` 브랜치가 로컬·원격에 존재하고, 폴더 백업 `D:/vibe-coding/scrap_sns_backup_20260411/`이 실재.
7. 뷰어 fallback 헬퍼 `resolvePostUrl`이 정상 데이터에서 호출되어도 `post.url`을 그대로 반환하고 합성 경로를 타지 않음 (= 안전망이 평시엔 잠들어 있음).

## 제약 조건

### 기술적
- Windows 11 환경. 파일 I/O는 `encoding='utf-8'` 또는 `utf-8-sig` 명시 필수 (CLAUDE.md 규정).
- 패키지 매니저는 pnpm 기본이나, 본 작업은 Python + 정적 JS이므로 npm/pnpm 무관.
- `node:sqlite` 이외 sqlite 드라이버 사용 금지 (공용 DB 정책).
- 삭제 명령은 `trash` CLI 사용. `rm`/`Remove-Item` 직접 호출 금지.

### 환경적
- 1인 사용. 프로덕션 배포·멀티 사용자 호환성 고려 불필요.
- 수집 파이프라인은 현재 동작 중이며, 작업 중에도 사용자가 수동으로 `total_scrap.py`를 돌릴 수 있으므로 **정비 중 경쟁 조건** 주의.
- `auth/` 폴더는 gitignore되어 폴더 복사로만 보존됨.

### 시간적
- 단일 세션 내 완료 목표. 단, LinkedIn/X/Substack 수정은 이번 범위 밖이며 추후 별개 세션에서 다룬다 (검토 결과 현재 수정 불필요로 확인됨).

## 경계선

### [OK] 허용 범위
- Threads Producer/Consumer/backfill 3개 경로의 post dict 빌드 로직 수정
- `utils/post_schema.py` 신설
- `migrate_schema.py` 레포 루트로 복구·재작성
- `output_threads/python/threads_py_full_*.json` 및 `output_total/total_full_*.json` 정본 교정 (백업 후)
- `web_viewer/script.js`의 username/url fallback 4개 지점 수정
- `web_viewer/convert_data.py`를 `_deprecated/`로 이동
- `CHANGELOG.md` 업데이트 (커밋별)

### [ASK] 해소 완료
- ✅ **data.js 재생성**: 임시 인라인 Python 스크립트로 1회 실행 (`total_scrap.py`에 병합 전용 모드 없음 확인)
- ✅ **gitignore 예외**: `.gitignore:54`의 `output_*` 다음 줄에 `!output_total/total_full_*.json` 추가

### 확인 완료 (F6, F7)
- **F6**: `CHANGELOG.md`가 레포 루트에 존재. 양식은 표 형식 (`| 일시 | 유형 | 범위 | 변경내용 |`) + **최상단 추가** 원칙. CLAUDE.md 규정에 따라 동일 양식 유지.
- **F7**: `.gitignore:54`의 `output_*` 패턴에 의해 `output_total/total_full_*.json`이 모두 gitignore 상태. 사용자의 "커밋하자" 요청을 반영하려면 위 옵션 중 하나 선택 필요.

### [NO] 금지 사항
- LinkedIn/X/Substack 스크래퍼 수정 (검토 결과 불필요)
- Flask API·웹 뷰어 UI 디자인 변경 (요구사항 밖)
- `script.js` 리팩터링 (요청 범위 초과)
- 스크래퍼 인증 로직·Playwright 설정 변경
- 원점 재구축·플랫폼·프레임워크 교체 (사용자가 질문했으나 검토 후 배제)
- 투기적 추상화 (Pydantic 도입, 테스트 프레임워크 도입 등) — 1인 사용 규모에 과함

## 결정안

### D1. 스키마 유틸을 공용 모듈로 분리

**채택**: `utils/post_schema.py` 단일 파일에 다음 3개를 정의.

```python
STANDARD_FIELD_ORDER = [
    "sequence_id", "platform_id", "sns_platform", "code", "urn",
    "username", "display_name", "full_text", "media", "url",
    "created_at", "date", "crawled_at", "source", "local_images",
    "is_detail_collected", "is_merged_thread",
]

def validate_post(post: dict) -> list[str]:
    """표준 필드 누락 여부 검증. 누락 키 리스트 반환, 빈 리스트면 OK."""
    ...

def normalize_post(post: dict) -> dict:
    """레거시 필드(user, timestamp, post_url 등) → 표준으로 변환.
    Threads의 경우 url 누락 시 https://www.threads.net/@{user}/post/{code} 합성.
    이미 표준이면 passthrough."""
    ...
```

- **근거**: CLAUDE.md·migrate_schema.py·각 스크래퍼가 각자 필드를 정의하던 분산 상태를 단일 소스로 수렴. 신설 코드가 50줄 내외로 작고 의존성 없음.
- **트레이드오프**: Pydantic·TypedDict 같은 정적 타입 도구는 도입하지 않음. 1인 사용 규모 + 필드 수 17개에서 런타임 검증 함수만으로 충분하고, 의존성 증가는 재발방지와 무관.

### D2. migrate_schema.py는 "복구 + 재작성"으로 일회성·반복가능 스크립트로

**채택**:
- `_backup_20260310/scripts/migrate_schema.py`를 레포 루트로 이동(복사 아님).
- 내부 로직을 `normalize_post`를 호출하는 얇은 래퍼로 재작성.
- 실행 모드: `--dry-run` (기본) / `--apply` (명시적) / `--target <glob>` (파일 지정).
- Threads만 변환 대상으로 기본 설정, 플래그로 확장 가능.

- **근거**: 과거 스크립트를 완전히 버리면 "과거엔 어떻게 변환했지?" 추적이 어려움. 재작성해두면 미래에 또 drift가 생겨도 바로 재적용 가능.
- **트레이드오프**: 지금은 일회성 교정이지만, 재작성된 스크립트는 영구 자산으로 레포에 남긴다. LinkedIn/X에 쓰일 일이 없을 수도 있지만 50줄 남짓의 비용을 감수.

### D3. 3층 게이트 — 원인층(item 빌더) + 중간층(병합) + 영구화층(write)

**채택**: F2 근본 원인 재정의에 따라 단일 지점 게이트가 아닌 **3층 방어선**으로 재설계.

#### 층 1: 원인 수정 — `utils/threads_parser.py:extract_posts_from_node`

Threads 상세 JSON을 item dict로 빌드하는 지점에서 **표준 키로 직접 작성**. 이전 코드가 `user`, `timestamp`, `code`를 쓰던 것을 `username`, `created_at`, `platform_id`로 교체하고, `url`도 합성. 이게 가장 근본적이고, 여기만 고치면 새로 수집되는 모든 데이터가 표준이 된다.

```python
# 변경 전 (추정)
item = {
    "code": post_data.get("code"),
    "user": user.get("username"),
    "timestamp": format_timestamp(post_data.get("taken_at")),
    ...
}

# 변경 후
item = {
    "platform_id": post_data.get("code"),
    "code": post_data.get("code"),  # 호환 유지
    "root_code": root_code,
    "username": user.get("username"),
    "display_name": user.get("full_name") or user.get("username"),
    "url": f"https://www.threads.net/@{user.get('username')}/post/{post_data.get('code')}",
    "created_at": created_at,  # format_timestamp 결과
    "sns_platform": "threads",
    "full_text": caption_text,
    "media": images,
    "source": "consumer_detail",
    ...
}
```

#### 층 2: 중간층 안전망 — `merge_thread_items:79` 직후 `normalize_post`

```python
merged_post = root.copy()
merged_post['full_text'] = merged_text
merged_post['media'] = all_media
merged_post['is_merged_thread'] = True
merged_post['original_item_count'] = len(sorted_items)
merged_post = normalize_post(merged_post)  # ← 추가
return merged_post
```

층 1에서 표준을 지키면 여기서 normalize는 no-op. 층 1이 실패하거나 외부 데이터가 섞여도 여기서 복구 시도.

#### 층 3: 영구화 게이트 — `promote_to_full_history:135` write 직전 엄격 검사

```python
# write 직전
invalid = [(i, validate_post(p)) for i, p in enumerate(full_content['posts']) 
           if (p.get('sns_platform') or '').lower() == 'threads']
invalid = [x for x in invalid if x[1]]  # missing 필드가 있는 것만
if invalid:
    # 엄격 모드: 1인 사용이므로 즉시 실패 가시화
    raise RuntimeError(f"schema violation: {len(invalid)} threads posts missing fields. "
                       f"First: idx={invalid[0][0]} missing={invalid[0][1]}")
with open(latest_full_path, 'w', encoding='utf-8-sig') as f:
    json.dump(full_content, f, ensure_ascii=False, indent=4)
```

`import_from_simple_database:194`, `sync_detail_collected_flags:244`, `:369` 등 다른 write 지점도 동일 패턴 적용.

- **근거**: 단일 게이트는 잘못된 지점에 걸면 효과 없음. 3층으로 분산하면 (1) 원인 차단 (2) 자동 복구 (3) 실패 가시화가 순차 작동. 1인 사용이므로 Step 3 엄격 실패가 사용자에게 즉시 노출되어 drift를 바로 찾을 수 있다.
- **트레이드오프**: `normalize_post`를 매 단계 통과하므로 약간의 중복 처리 발생. 975건 규모에서는 무시 가능 (< 0.1초).

**엄격 모드는 층 3에만** 적용. 층 1·2는 관대 모드(normalize 후 그대로 진행). 이유: 층 1은 신규 수집 중 실패하면 그 게시물만 유실되는 반면, 층 3은 파일 전체 write를 막기 때문에 실패 시 손실이 크고 주목도가 높음 → drift 감지기 역할에 적합.

### D4. 데이터 정본 교정 — 대상 범위

**채택**: 변환 대상은 다음 3개 파일 집합에 한정.
1. `output_threads/python/threads_py_full_*.json` (Threads 누적 원본)
2. `output_total/total_full_*.json` (웹 뷰어 소스)
3. `web_viewer/data.js` (total_scrap.py가 자동 생성하므로 #2 교정 후 재생성)

- **근거**: `output_threads/python/update/` 증분 파일은 gitignore + 임시 성격이므로 교정 불필요 (다음 total 실행 시 재생성됨). `output_linkedin/`, `output_twitter/`는 drift 없음 확인.
- **트레이드오프**: 증분 파일을 건드리지 않으면 다음 total 실행 때 다시 레거시가 합쳐질 수 있음. → **완화책**: Step 6의 엄격 모드가 증분 파일 저장 시점에 이미 막음.

### D5. 뷰어 fallback — 제거가 아닌 유지

**채택**: `web_viewer/script.js` 4개 지점에 `post.user` fallback 추가 + `resolvePostUrl()` 헬퍼 도입. 데이터 정본 교정 후에는 동작하지 않지만 의도적으로 남김.

- **근거**: 평시엔 잠자는 "조기 감지기" 역할. 미래에 drift가 들어오면 "Unknown"이 카드에 다시 보이기 전에 fallback이 동작해 일시 덮어주되, 그 순간 사용자가 위화감(=신규 Threads에 `post.user` 기반 URL이 보임)을 느낄 가능성이 있음 → 즉시 조사 트리거.
- **대안 검토**: "마이그레이션 후엔 fallback 제거" 안도 고려. 그러나 fallback 제거 시 drift가 조용히 되돌아오면 사용자가 발견할 때까지 시간차가 커짐. 유지 쪽이 안전.

### D6. data.js 재생성은 임시 인라인 스크립트 (정정)

**채택**: plan-check 중 `total_scrap.py --mode` 옵션 확인 결과 `all`/`update` 2가지만 있고 수집 없이 병합만 하는 경로 부재 확인 (`total_scrap.py:344-345`). 따라서 일회성 인라인 Python 스크립트(`utils/build_data_js.py`)로 재생성하고, 해당 스크립트는 레포 루트에 영구 자산으로 남긴다.

```python
# utils/build_data_js.py (신규)
"""total_full_*.json → web_viewer/data.js 단독 변환 (재현성 확보)."""
import json, glob, os, sys
from utils.post_schema import validate_post

def build():
    latest = sorted(glob.glob('output_total/total_full_*.json'))[-1]
    with open(latest, encoding='utf-8-sig') as f:
        data = json.load(f)
    posts = data.get('posts', data) if isinstance(data, dict) else data
    # 전수 검증
    bad = [(i, validate_post(p)) for i, p in enumerate(posts)]
    bad = [x for x in bad if x[1]]
    if bad:
        print(f"[ERROR] {len(bad)} posts invalid. First: idx={bad[0][0]} missing={bad[0][1]}", file=sys.stderr)
        sys.exit(1)
    content = 'const snsFeedData = ' + json.dumps(data, ensure_ascii=False, indent=2) + ';'
    with open('web_viewer/data.js', 'w', encoding='utf-8-sig') as f:
        f.write(content)
    print(f'OK: {len(posts)} posts → web_viewer/data.js')

if __name__ == '__main__':
    build()
```

- **근거**: (a) `total_scrap.py`가 수집 없이 병합만 하는 모드를 신설하려면 해당 파일 구조 개선 필요 → 범위 확대 리스크. (b) 단일 파일 유틸은 import/테스트/실행이 자명하고 재현 가능. (c) 마이그레이션 스크립트와 동일 `utils/post_schema.py`에 의존하므로 drift 조기 감지에도 기여.
- **부수 작업**: `web_viewer/convert_data.py` → `_deprecated/convert_data.py`로 이동. 혼란 방지. 단 **먼저 import 참조 확인 필요** — 다른 파일에서 `from web_viewer.convert_data import ...`나 `web_viewer/convert_data.py` 직접 실행이 없는지 grep.

### D7. 이중 백업

**채택**:
- A. Git: `git checkout -b archive/pre-cleanup-20260411` → 현 unstaged 포함 커밋 → push
- B. 폴더: `cp -r D:/vibe-coding/scrap_sns D:/vibe-coding/scrap_sns_backup_20260411`

- **근거**: A는 git tracked 파일의 이력·diff 보존, B는 gitignore된 `auth/`, `output_*/python/update/`, `logs/`, `.env.local` 보존. 두 가지 모두 필요.
- **트레이드오프**: 폴더 복사는 수 GB가 될 수 있음. 용량 한 번 확인 후 진행.

## 사실 확인

논의 중 검증한 사실. 가정이 아닌 확인된 근거.

### F1. 현재 데이터의 drift 규모 (검증 완료)

`output_total/total_full_20260411.json` 기준 전수 카운트:

| 플랫폼 | 전체 | username 누락 | url 누락 | 레거시 `user` 키 | 레거시 `timestamp` 키 |
|---|---|---|---|---|---|
| threads | 659 | 583 | 583 | 583 | 583 |
| linkedin | 237 | 0 | 0 | 0 | 0 |
| x | 79 | 0 | 0 | 0 | 71 (부가 메타, 표준과 공존) |

→ Threads만 **88%가 레거시**. LinkedIn·X는 drift 없음 (X의 `timestamp`는 표준 `created_at`과 공존하는 부가 필드로 drift 아님).

### F2. 생성 코드 경로의 건전성 (재검증 완료 — 2026-04-11 plan-check 결과로 정정)

**이전 F2는 부정확했음**. plan-check 중 실제 코드·데이터 재검증 결과 근본 원인이 재정의됨.

| 파일 | 상태 | 근거 |
|---|---|---|
| `thread_scrap.py:428-449` (Producer, network 경로) | 🟢 표준 준수 | `username`, `url`, `display_name` 모두 작성 |
| `thread_scrap.py:526-539` (Producer, DOM 경로) | 🟢 표준 준수 | 동일하게 표준 작성 |
| `thread_scrap.py:127-135` (backfill) | 🟡 정합성 낮음 | `url` 누락, `post_url` 키 사용. 단 데이터 샘플상 실제 생성원 아님 (source 필드 누락 + is_merged_thread: true가 583건 전부) |
| **`utils/threads_parser.py:extract_posts_from_node`** (Consumer의 item 빌더) | 🔴 **레거시 생성원** | Threads 상세 페이지 JSON → item dict 변환 시 `user`, `timestamp`, `code` 등 레거시 키 사용으로 추정. 583건 전원 `user`, `timestamp`, `original_item_count`, `root_code` 필드 보유 |
| `thread_scrap_single.py:65-84` `merge_thread_items` | 🔴 **레거시 증폭원** | `root.copy()`로 레거시 item의 모든 키를 병합 결과에 그대로 상속. `is_merged_thread: true` + `original_item_count`만 추가 |
| `thread_scrap_single.py:135/194/237/244/369` | 🔴 **레거시 영구화원** | 5곳의 `json.dump` write가 위 병합 결과를 파일에 저장. 이전 F2가 "write 경로 없음"이라 기록한 것은 **오류** — 실제로는 필드 단위 write가 없을 뿐 파일 단위 write는 5곳 존재 |
| `thread_scrap_single.py:177` `import_from_simple_database` | 🟡 보조 경로 | simple → full 승격 시 `p.copy()` 후 `is_merged_thread: False` 세팅. simple이 레거시면 그대로 복사되지만 현재 데이터상 merged=True만 레거시이므로 이 경로는 부차적 |
| `utils/linkedin_parser.py:123-141` | 🟢 표준 준수 | 6종 필드 직접 작성 |
| `twitter_scrap.py:112-124, 178-190` | 🟢 표준 준수 | Producer 양 경로 |
| `twitter_scrap_single.py:127-147` | 🟢 표준 준수 | in-place update, 표준 키만 write |

**근본 원인 체인 (재정의)**:
```
Threads 상세 페이지 HTML
  → extract_json_from_html() 
  → utils/threads_parser.py extract_items_multi_path()
  → extract_posts_from_node()  ← 레거시 키(`user`, `timestamp`, `code`)로 item dict 생성 (추정)
  → results.append(item)
  → grouped[root_code].append(item)
  → merge_thread_items(items):65  ← root.copy() + is_merged_thread:true
  → promote_to_full_history():135  ← json.dump로 파일 영구화
  → 전체 레거시 583건 생성
```

**영구화 경로**: `thread_scrap_single.py`의 5개 write 지점 전부가 잠재적 영구화원. 하지만 핵심은 `:135` promote_to_full_history — 레거시 키가 처음 full DB에 들어가는 지점.

**재발방지 수정 지점 (plan Step 6 재설계 필요)**:
1. **최우선**: `utils/threads_parser.py:extract_posts_from_node` — item 빌더가 표준 키(`username`, `url`, `platform_id`, `created_at`)를 작성하도록 수정. 여기만 고치면 새로 수집되는 모든 데이터가 표준.
2. **안전망**: `merge_thread_items:79` `root.copy()` 후 `normalize_post` 한 번 통과. 과거 데이터나 외부 소스가 섞여 들어와도 차단.
3. **영구화 게이트**: `promote_to_full_history:135` write 직전 `validate_post` 전수 검사. 위반 시 엄격 실패(assert) 또는 관대 normalize 후 재검사.

### F2-legacy. 이전 탐색의 오류 (기록 보존)

이전 F2 "write 경로 없음"은 탐색 에이전트가 "post dict에 `post['username'] = ...` 같은 필드 단위 write가 없다"는 관찰을 spec으로 옮기는 과정에서 "파일 write 없음"으로 잘못 확장됐다. 실제로는 `json.dump(full_content, f, ...)` 형태의 전체 dict write가 5곳 있고, 필드 단위 write가 없다는 점은 오히려 "wrapping 기회가 적다" = "게이트를 wrapping 층에서 한 번에 걸 수 있다"는 의미. plan에는 이 점이 이점으로 반영되어야 한다.

### F3. data.js 생성 경로 (검증 완료)

- **자동**: `total_scrap.py:274-282`가 수집 완료 후 `total_full_*.json` → `web_viewer/data.js` 자동 변환.
- **레거시 수동**: `web_viewer/convert_data.py`는 `total_full_20260201.json` 하드코딩. 현재 사용되지 않는 유령 스크립트로 판단.

### F4. 뷰어 fallback 누락 지점 (검증 완료)

`web_viewer/script.js`에서 `post.user` 또는 Threads URL 합성 로직이 없는 지점:
- `:498` — `getFilteredPosts()` 내부 favorites/todos 키
- `:579` — `createCard()` 내부 `postUrl` 정의
- `:626` — Header 사용자명 `${post.display_name || post.username || 'Unknown'}`
- `:1303` — invisible-post-item 사용자명 `${post.username || 'Unknown'}`

### F6. CHANGELOG.md 양식 (검증 완료)

레포 루트 `CHANGELOG.md`는 표 형식 `| 일시 | 유형 | 범위 | 변경내용 (목적 포함) |`, 최상단 추가 원칙. 본 작업 커밋도 동일 양식 준수.

### F7. total_full_*.json gitignore 상태 (검증 완료)

`.gitignore:54`의 `output_*` 패턴이 `output_threads/`, `output_linkedin/`, `output_twitter/`, `output_total/`, `output_substack/`, `output_linkedin_user/` 전부를 제외. 과거에 `output-linkedin-twitter` 커밋(2026-03-10 17:09)이 있었던 것을 보면, 의도적으로 이후 "수집 산출물은 추적하지 않는" 정책으로 전환한 것으로 보임. 사용자의 "total은 커밋하자" 요청과 현재 정책이 충돌하므로 plan 단계에서 결정 필요.

### F5. LinkedIn/X/Substack 수정 불필요 (검증 완료)

Explore 에이전트 전수 조사 결과:
- LinkedIn 237건 + X 79건 전원 표준 6종 필드 100% 완비.
- 두 플랫폼의 post dict 빌더가 표준 키를 직접 작성.
- **backfill 패턴은 `thread_scrap.py:127-135` 단 1곳에만 존재** — LinkedIn/X는 구조적으로 이 drift가 발생할 수 없음.
- Substack은 현재 활성 데이터셋에 0건 (`substack_scrap_by_user.py`도 `_backup_20260310/`에만 존재).

## 의사결정 로그

| 시점 | 결정 내용 | 근거 | 검토한 대안 |
|---|---|---|---|
| 초기 진단 | 원점 재구축 배제 | 설계는 건전, drift는 1종뿐, 재수집 중단 시 SNS 유실 리스크 | 원점 재구축 / 현상만 수정 |
| 범위 설정 | 이번 세션은 Threads만 | LinkedIn/X/Substack drift 없음 확인 (F5) | 전 플랫폼 일괄 / Threads만 |
| 스키마 유틸 | 단일 파일 `utils/post_schema.py` | 단일 진실 원천 확립, 의존성 없음 | Pydantic 도입 / CLAUDE.md 리스트를 그대로 사용 |
| 마이그레이션 | 1회성 + 반복가능 스크립트로 복구 | 추적성 확보, 미래 재사용 가능 | 한 번만 실행 후 삭제 / 복구 안 함 |
| 생성 게이트 | 엄격 모드 (assert) | 1인 사용에서 drift 즉시 가시화 | 관대 모드 (normalize) / 경고만 |
| 데이터 범위 | full 파일만 교정, update/ 제외 | update/는 임시·gitignore, 게이트가 다음 실행부터 막음 | update/ 포함 / full만 |
| 뷰어 fallback | 마이그레이션 후에도 유지 | 조기 감지기 역할 | 마이그레이션 후 제거 |
| data.js 재생성 | total_scrap.py 기존 경로 활용 | 이미 자동화되어 있음 | 별도 스크립트 신설 |
| convert_data.py | `_deprecated/`로 이동 | 유령 스크립트 혼란 제거 | 삭제 / 유지 |
| 백업 | git 브랜치 + 폴더 복사 병행 | gitignore 파일까지 보호 | git 브랜치만 / 폴더 복사만 |
| 커밋 전략 | `total_full_*.json`을 main에 커밋 | 사용자 명시 요청 | 데이터 파일은 로컬만 유지 |
| gitignore 예외 | `.gitignore`에 `!output_total/total_full_*.json` 예외 추가 | 가장 깔끔하고 자동 커밋 가능 | 별도 경로 복사 / 로컬만 유지 |
| data.js 재생성 | 임시 인라인 Python 스크립트 | total_scrap.py에 병합 전용 모드 부재 확인 | total_scrap.py --mode merge 신설 |

## 부록: 작업 순서 개요 v2 (plan-check 반영, plan 파일로 이관 완료)

**v1→v2 변경**: 생성 게이트(v1 Step 6 → v2 Step 3)를 마이그레이션(v1 Step 3 → v2 Step 4)보다 **먼저** 실행. 순서 역전은 "마이그레이션 후 Consumer 재실행 시 레거시 재유입"을 차단하는 핵심.

1. 이중 백업 + 사전 확인 (import 참조·parser 실구현)
2. `utils/post_schema.py` 신설
3. `utils/build_data_js.py` 신설 + `migrate_schema.py` 복구·재작성
4. **3층 게이트 심기** (원인: `threads_parser`, 중간: `merge_thread_items`, 영구화: `_assert_threads_schema`)
5. `migrate_schema.py --dry-run` → `--apply` 실행
6. `utils/build_data_js.py`로 data.js 재생성
7. `web_viewer/script.js` fallback 4지점
8. `.gitignore` 2단 negation
9. `convert_data.py` → `_deprecated/` git mv
10. 검증 (성공 기준 7가지 — 전부 pass/fail 자동 스크립트)
11. `cp` 스킬로 커밋 6개 분리 + CHANGELOG 표 행 추가

상세 실행 계획 및 코드 조각: plan 파일 `C:/Users/ahnbu/.claude/plans/temporal-weaving-hartmanis.md` v2.
