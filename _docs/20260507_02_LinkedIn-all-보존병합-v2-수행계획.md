# LinkedIn All 보존 병합 V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LinkedIn `--mode all`이 부분 수집 상황에서도 기존 저장글을 삭제하지 않고, 새로 관측된 글만 추가/갱신하도록 만든다.

**Architecture:** 변경 범위는 `linkedin_scrap.py`의 full 저장 병합 로직과 해당 단위 테스트로 제한한다. `all`은 깊게 훑는 수집 모드로 유지하되, 저장 시에는 기존 full DB를 기준으로 보존 병합한다. 이번 계획은 Threads, 이미지 보강, `update` 중단기준, UI 변경을 다루지 않는다.

**Tech Stack:** Python, pytest, existing JSON full files under `output_linkedin/python`.

---

## 현재 상태

현재 `linkedin_scrap.py`는 최신 full DB를 읽어 `existing_posts_map`, `existing_codes`, `max_sequence_id`를 구성한다.

문제는 `update_full_version()`의 `all` 분기다.

```python
if CRAWL_MODE == "all":
    # ALL 모드일 때는 기존 데이터를 무시하고 새로 수집한 것으로 대체 (개행 등 변경사항 반영)
    final_posts = self.posts
    duplicate_count = 0
    new_items = self.posts
```

이 구조에서는 LinkedIn 전체 크롤링이 중간에 끊겨 일부 글만 수집되면, 기존 full DB에 있던 미관측 글이 최종 파일에서 빠질 수 있다.

## 원하는 동작

예시:

- 기존 DB: `A, B, C, D`
- 이번 `all` 수집 결과: `A, B, C, E`
- 최종 DB: `A, B, C, D, E`
- 보고: `D`는 “이번 all 수집에서 다시 관측되지 않음”으로만 기록

즉, 미관측 기존글은 삭제하지 않는다.

## 범위

포함:

- LinkedIn `all` 저장 병합 방식 수정
- 기존 `sequence_id`, `crawled_at`, `local_images` 보존
- 신규 글에는 기존 방식대로 `sequence_id` 부여
- 미관측 기존글 수를 metadata/merge_history에 기록
- 단위 테스트 추가

제외:

- `update` 중단기준 변경
- Threads/X 로직 변경
- `total_scrap.py`, `server.py`, `web_viewer/script.js` 변경
- 이미지 보강
- 실제 크롤링 실행
- 기존 데이터 삭제/마이그레이션

## 영구화 Surface

- 영향받는 파일: `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`
- 보조 산출물: `output_linkedin/python/update/linkedin_python_update_YYYYMMDD_HHMMSS.json`
- 통합본 영향: 이후 `total_scrap.py`가 최신 LinkedIn full 파일을 병합할 때 `output_total/total_full_YYYYMMDD.json`에 간접 반영

## 마이그레이션 판단

기존 데이터 마이그레이션은 불필요하다.

근거:

- 게시글 스키마 필드를 바꾸지 않는다.
- 기존 `posts` 배열의 ID, URL, 본문, `media`, `local_images` 구조를 유지한다.
- 새로 추가되는 정보는 metadata/merge_history의 실행 보고용 값뿐이다.

마이그레이션 실행 명령:

```powershell
# 없음
```

마이그레이션 결과 검증 명령:

```powershell
pytest tests/unit/test_linkedin_full_merge.py -q
python -m py_compile linkedin_scrap.py
```

기대 출력:

- 기존 ID가 미관측이어도 최종 posts에 유지된다.
- 신규 ID는 추가된다.
- 기존 `local_images`는 보존된다.

## Task 1: LinkedIn all 병합 단위 테스트 추가

**Files:**

- Create: `tests/unit/test_linkedin_full_merge.py`
- Modify: 없음

- [ ] **Step 1: failing test 작성**

```python
import linkedin_scrap


def _post(pid, *, sequence_id, text=None, local_images=None, media=None):
    return {
        "platform_id": pid,
        "code": pid,
        "sequence_id": sequence_id,
        "sns_platform": "linkedin",
        "username": "tester",
        "display_name": "Tester",
        "full_text": text or f"text {pid}",
        "media": media if media is not None else [],
        "local_images": local_images if local_images is not None else [],
        "url": f"https://www.linkedin.com/feed/update/urn:li:activity:{pid}",
        "created_at": "2026-05-07 10:00:00",
        "date": "2026-05-07",
        "crawled_at": "2026-05-07T10:00:00",
    }


def test_all_mode_preserves_unobserved_existing_posts():
    old_posts = [
        _post("A", sequence_id=4),
        _post("B", sequence_id=3),
        _post("C", sequence_id=2),
        _post("D", sequence_id=1, local_images=["web_viewer/images/d.jpg"]),
    ]
    scraped_posts = [
        _post("A", sequence_id=4, text="updated A"),
        _post("B", sequence_id=3),
        _post("C", sequence_id=2),
        _post("E", sequence_id=5),
    ]

    final_posts, new_items, merge_report = linkedin_scrap.merge_linkedin_full_posts(
        old_posts,
        scraped_posts,
        crawl_mode="all",
    )

    final_ids = [post["platform_id"] for post in final_posts]

    assert final_ids == ["E", "A", "B", "C", "D"]
    assert [post["platform_id"] for post in new_items] == ["E"]
    assert merge_report["observed_existing_count"] == 3
    assert merge_report["unobserved_existing_count"] == 1
    assert merge_report["unobserved_existing_ids"] == ["D"]
    assert next(post for post in final_posts if post["platform_id"] == "D")["local_images"] == [
        "web_viewer/images/d.jpg"
    ]


def test_all_mode_preserves_existing_metadata_when_post_is_observed_again():
    old_posts = [
        _post(
            "A",
            sequence_id=10,
            local_images=["web_viewer/images/a.jpg"],
            media=["https://cdn.example.com/a.jpg"],
        )
    ]
    scraped_posts = [
        {
            **_post("A", sequence_id=10, text="newer text", media=["https://cdn.example.com/a2.jpg"]),
            "crawled_at": "2026-05-07T11:00:00",
            "local_images": [],
        }
    ]

    final_posts, new_items, merge_report = linkedin_scrap.merge_linkedin_full_posts(
        old_posts,
        scraped_posts,
        crawl_mode="all",
    )

    assert len(final_posts) == 1
    assert new_items == []
    assert final_posts[0]["sequence_id"] == 10
    assert final_posts[0]["crawled_at"] == "2026-05-07T10:00:00"
    assert final_posts[0]["local_images"] == ["web_viewer/images/a.jpg"]
    assert final_posts[0]["full_text"] == "newer text"
    assert merge_report["observed_existing_count"] == 1
    assert merge_report["unobserved_existing_count"] == 0
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
pytest tests/unit/test_linkedin_full_merge.py -q
```

Expected:

```text
FAILED ... AttributeError: module 'linkedin_scrap' has no attribute 'merge_linkedin_full_posts'
```

## Task 2: LinkedIn full 병합 helper 구현

**Files:**

- Modify: `linkedin_scrap.py`
- Test: `tests/unit/test_linkedin_full_merge.py`

- [ ] **Step 1: helper 추가**

`linkedin_scrap.py`의 utility 함수 영역에 아래 함수를 추가한다.

```python
def get_post_identity(post):
    return post.get("platform_id") or post.get("code")


def merge_linkedin_full_posts(old_posts, scraped_posts, crawl_mode):
    old_by_id = {}
    old_order = []
    for post in old_posts:
        pid = get_post_identity(post)
        if not pid or pid in old_by_id:
            continue
        old_by_id[pid] = post
        old_order.append(pid)

    final_by_id = dict(old_by_id)
    observed_existing_ids = []
    new_items = []

    for post in scraped_posts:
        pid = get_post_identity(post)
        if not pid:
            continue

        existing = old_by_id.get(pid)
        if existing:
            merged = {**existing, **post}
            if existing.get("sequence_id") is not None:
                merged["sequence_id"] = existing.get("sequence_id")
            if existing.get("crawled_at"):
                merged["crawled_at"] = existing.get("crawled_at")
            if existing.get("local_images") and not post.get("local_images"):
                merged["local_images"] = existing.get("local_images")
            final_by_id[pid] = merged
            observed_existing_ids.append(pid)
        else:
            final_by_id[pid] = post
            new_items.append(post)

    observed_existing = set(observed_existing_ids)
    unobserved_existing_ids = [pid for pid in old_order if pid not in observed_existing]

    final_posts = list(final_by_id.values())
    final_posts.sort(key=lambda item: item.get("sequence_id", 0), reverse=True)

    merge_report = {
        "crawl_mode": crawl_mode,
        "observed_existing_count": len(observed_existing),
        "unobserved_existing_count": len(unobserved_existing_ids),
        "unobserved_existing_ids": unobserved_existing_ids[:20],
    }

    return final_posts, new_items, merge_report
```

- [ ] **Step 2: 테스트 통과 확인**

Run:

```powershell
pytest tests/unit/test_linkedin_full_merge.py -q
```

Expected:

```text
2 passed
```

## Task 3: `update_full_version()`의 all 분기 교체

**Files:**

- Modify: `linkedin_scrap.py`
- Test: `tests/unit/test_linkedin_full_merge.py`, `tests/unit/test_linkedin_auth_wait.py`

- [ ] **Step 1: all/update 공통 병합 경로 적용**

`linkedin_scrap.py::update_full_version()`에서 현재 분기를 아래 흐름으로 바꾼다.

```python
        if CRAWL_MODE == "all":
            final_posts, new_items, merge_report = merge_linkedin_full_posts(
                old_posts,
                self.posts,
                CRAWL_MODE,
            )
            duplicate_count = len(self.posts) - len(new_items)
        else:
            existing_codes = {p.get("platform_id") or p.get("code") for p in old_posts}
            new_items = [p for p in self.posts if (p.get("platform_id") or p.get("code")) not in existing_codes]
            duplicate_count = len(self.posts) - len(new_items)
            final_posts = new_items + old_posts
            merge_report = {
                "crawl_mode": CRAWL_MODE,
                "observed_existing_count": 0,
                "unobserved_existing_count": 0,
                "unobserved_existing_ids": [],
            }

        final_posts.sort(key=lambda x: x.get("sequence_id", 0), reverse=True)
```

- [ ] **Step 2: merge_history에 보고값 추가**

`merge_history.append(...)` 블록에 아래 필드를 추가한다.

```python
                "observed_existing_count": merge_report["observed_existing_count"],
                "unobserved_existing_count": merge_report["unobserved_existing_count"],
                "unobserved_existing_ids": merge_report["unobserved_existing_ids"],
```

그리고 metadata에도 짧은 summary를 추가한다.

```python
                "all_mode_observed_existing_count": merge_report["observed_existing_count"],
                "all_mode_unobserved_existing_count": merge_report["unobserved_existing_count"],
```

- [ ] **Step 3: 검증**

Run:

```powershell
pytest tests/unit/test_linkedin_full_merge.py tests/unit/test_linkedin_auth_wait.py -q
python -m py_compile linkedin_scrap.py
```

Expected:

```text
all tests passed
```

## Task 4: 실제 실행 전 dry 검토

**Files:**

- Modify: 없음

- [ ] **Step 1: 현재 미커밋 변경 분리 확인**

Run:

```powershell
git status --short
```

Expected:

```text
M linkedin_scrap.py
M tests/unit/test_linkedin_auth_wait.py
?? docs/plans/20260507_02_LinkedIn-all-보존병합-v2-수행계획.md
```

현재 남아 있는 `update` 중단기준 변경과 이번 `all` 변경이 섞이지 않도록 구현 전 커밋/보류 상태를 결정한다. 커밋이 필요하면 직접 `git commit`하지 않고 cp 스킬을 사용한다.

- [ ] **Step 2: 운영 실행은 별도 승인 후 진행**

Run:

```powershell
python linkedin_scrap.py --mode all
```

Expected:

- 사용자가 명시적으로 운영 실행을 승인한 경우에만 실행한다.
- 실행 후 `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`의 전체 건수가 기존보다 조용히 감소하지 않는다.
- 미관측 기존글은 posts에 남고 metadata/merge_history에 개수만 기록된다.

## 완료 기준

- LinkedIn `all`은 기존 DB를 base로 유지한다.
- 이번 `all`에서 다시 보이지 않은 기존글은 삭제하지 않는다.
- 새로 관측된 글만 추가된다.
- 다시 관측된 기존글은 `sequence_id`, `crawled_at`, `local_images`를 보존한다.
- `update` 중단기준, Threads, 이미지 보강은 변경하지 않는다.

## 자체 검토

- 목적 충족: LinkedIn `all`의 데이터 손실 위험만 직접 해결한다.
- 과최적화 제거: 별도 audit 스크립트, 이미지 보강, media-empty 분류를 제거했다.
- 검증 가능성: helper 단위 테스트로 부분 수집 케이스를 고정한다.
- 남은 한계: 사용자가 실제 LinkedIn에서 저장 해제한 글도 기본적으로 보존된다. 삭제 반영은 별도 “저장 해제 동기화” 기능으로 다뤄야 한다.
