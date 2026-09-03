---
title: saved-thereads-crawler 도입 검토 세션 문서화
created: 2026-04-20 15:15

session_id: 1bc8000d-6c92-405f-ac43-5a4ac961fed3
session_path: C:/Users/ahnbu/.claude/projects/D--vibe-coding-scrap-sns/1bc8000d-6c92-405f-ac43-5a4ac961fed3.jsonl


ai: claude
---

# saved-thereads-crawler 도입 검토 세션 문서화

## 발단: 사용자 요청

사용자 원요청은 아래와 같다.

> 현재 프로젝트에서 다음 레포에서 도입할만한 크리티컬한 포인트가 있는지 꼼꼼하게 코드 베이스로 검토하고 보고하라.
>
> 검토 대상 레포: https://github.com/shinsooshinsoo/saved-thereads-crawler

검토 기준 프로젝트는 현재 저장소 `scrap_sns`이며, 확인된 원격 주소는 `https://github.com/ahnbu/scrap_sns.git`이다. 세션 마지막에는 "현재 세션을 문서화시켜라. 문서 내에는 해당 레포 주소와 내역들이 포함되도록 구성하라" 요청이 추가되었다.

## 작업 상세내역

- `plan-stop` 스킬을 먼저 로드하고, plan 파일 생성 없이 대화형 검토로만 진행했다.
- 외부 레포 구조 파악과 현재 프로젝트 Threads 수집 구조 파악을 병렬로 진행했다.
- 외부 레포는 `gh repo view`와 `gh api`로 README 및 핵심 파일(`scraper.py`, `classifier.py`, `deduplicate.py`, `deep_clean.py`, `clean_garbage.py`, `add_tags.py`, `config.py`)을 확인했다.
- 현재 프로젝트는 [`thread_scrap.py`](../thread_scrap.py), [`thread_scrap_single.py`](../thread_scrap_single.py), [`utils/post_schema.py`](../utils/post_schema.py), [`utils/common.py`](../utils/common.py), [`server.py`](../server.py)를 읽어 수집 경로, 스키마, 정제 로직, 뷰어 구조를 대조했다.
- 사용자가 "비교표 작성시, 표 작성스킬로 다시 작성하라."고 요청해 compare-table 규칙으로 비교표를 다시 정렬했다.

### 외부 레포 vs 우리 프로젝트 — 사용자 관점 비교

| 항목 | 우리 프로젝트 (`scrap_sns`) | 외부 레포 (`saved-thereads-crawler`) |
|---|---|---|
| 데이터 신뢰성 (스키마 정합성) | ✅ `STANDARD_FIELD_ORDER` + `validate_post`/`normalize_post` 단일 정본 | ❌ dict 자유 구조, 검증 없음 |
| 수집 안정성 (Threads) | ✅ GraphQL 네트워크 캡처 + DOM 폴백 + 스레드/답글 검증 | ❌ DOM `a[href]` 긁기 + 글마다 페이지 재방문 |
| 수집 속도 | ██████ ThreadPoolExecutor 5병렬 HTTP | ██░░░░ 페이지 재방문 직렬 |
| 증분 수집 견고성 | ✅ `is_detail_collected` + 실패카운트 + 연속dup 자동중단 | ❌ `.crawled_urls.txt` 라인 추가만 |
| 도메인 정책 (canonical) | ✅ `threads.com` 강제 + 마이그레이션 도구 | ❌ `threads.net` (레거시) |
| 멀티 플랫폼 지원 | ✅ Threads / LinkedIn / X(Twitter) | ❌ Threads 전용 |
| 본문 가비지 정제 | ✅ `clean_text(platform=...)` 공통 함수 보유 | 사후 `deep_clean.py`/`clean_garbage.py` |
| 테스트 커버리지 | ████░░ unit/contract/integration/e2e/smoke | ░░░░░░ 없음 |
| AI 의미기반 분류 | ❌ 키워드 매칭 `auto-tag` 룰만 존재 | ✅ Gemini Flash 5카테고리 자동 분류 |
| AI 해시태그 추출 | ❌ 없음 | ✅ Gemini로 키워드 3~5개 추출 |
| 뷰어/검색 UX | ✅ Flask API + JS 뷰어 + 서버검색 + ETag/gzip | ❌ `index.md` 정적 링크 목록 |
| 운영 비용 (외부 API) | ✅ 무료 (LLM 호출 없음) | ⚠️ Gemini 유료 결제 권장 (README 명시) |

<span style="color:#888">*정렬 기준: 데이터 신뢰성과 수집 안정성을 최상단에 두었다. 두 항목이 무너지면 AI 분류나 뷰어 기능보다 운영 리스크가 훨씬 커지기 때문이다. AI 분류·해시태그는 외부 레포의 거의 유일한 우위라 중간 이후에 배치했다.*</span>

### 포인트별 검토 메모

1. **AI 의미기반 분류 (`classifier.py`)**는 조건부 검토 가치가 있다고 판단했다. 다만 외부 레포의 5개 카테고리(`정보/지혜/기술/뉴스/인생`)는 현재 사용자 사업 맥락과 직접 맞지 않아 그대로 도입하지 않기로 정리했다.
2. **AI 해시태그 추출 (`add_tags.py`)**은 현재 `auto-tag` 룰을 보조하는 아이디어로는 참고 가능하다고 봤다. 본문에서 3~5개 키워드를 뽑아 룰 생성을 돕는 방향이 적합하다고 판단했다.
3. **수집 로직 (`scraper.py`)**은 도입 가치가 없다고 결론냈다. 현재 프로젝트는 GraphQL 네트워크 응답 캡처와 HTTP 상세 호출을 사용해 이미 더 빠르고 정확한 구조를 갖고 있다.
4. **본문 정제 도구 (`clean_garbage.py`, `deep_clean.py`)**는 이미 현재 프로젝트의 공통 `clean_text` 로직으로 대체 가능하다고 봤다. 외부 레포에서 보완하는 댓글 혼입 문제는 현재 구조에서는 발생 가능성이 낮다고 정리했다.
5. **사후 중복 정리/파일명 정리 도구 (`deduplicate.py`, `fix_duplicates.py`, `clean_rename.py`)**는 필요 없다고 판단했다. 현재 프로젝트는 JSON 정본 중심 구조라 Markdown 사후 청소 전제가 약하다.
6. **`.crawled_urls.txt` 기반 증분 수집**은 현재 프로젝트의 `is_detail_collected`, 실패카운트, 연속 dup 중단보다 열등하다고 봤다. 운영 안정성 기준으로 채택 대상에서 제외했다.

## 의사결정 기록

- 결정: 외부 레포의 수집, 정제, 증분 로직은 도입 보류하고, AI 의미기반 분류와 해시태그 추출 아이디어만 조건부 검토 대상으로 남긴다.
- 근거: 현재 프로젝트가 수집 안정성, 스키마 정합성, 속도, 증분 견고성, canonical 도메인 정책, 멀티 플랫폼, 뷰어 UX, 테스트 체계에서 전반적으로 우위였다.
- 트레이드오프: 의미기반 분류를 도입하면 태그 품질은 높아질 수 있지만, API 비용이 생기고 외부 레포의 카테고리 체계는 현재 비즈니스 맥락과 맞지 않는다.
- 제외한 대안: 외부 레포의 `scraper.py`, `deep_clean.py`, `deduplicate.py`, `.crawled_urls.txt` 증분 방식은 직접 도입안에서 제외했다.

## 검증계획과 실행결과

> compare-table 스킬 이모지 포맷 적용 (✅❌⚠️⏳)

| 검증 항목 | 검증 방법 | 결과 | 비고 |
|-----------|-----------|------|------|
| 외부 레포 핵심 파일 재검토 | `gh repo view`와 `gh api`로 핵심 파일 목록 및 내용 재확인 | ⏳ 미실행 | 원세션에서는 확인했지만 문서화 단계에서 재실행하지 않음 |
| 현재 프로젝트 Threads 수집 경로 재검토 | [`thread_scrap.py`](../thread_scrap.py), [`thread_scrap_single.py`](../thread_scrap_single.py), [`utils/post_schema.py`](../utils/post_schema.py) 재확인 | ⏳ 미실행 | 원세션 기반 기록만 반영 |
| AI 분류 도입 타당성 검증 | `auto-tag` 파이프라인에 LLM 보조 단계를 붙이는 PoC 설계 및 비용 추정 | ⏳ 미실행 | 후속 작업 필요 |

## 리스크 및 미해결 이슈

- 외부 레포의 AI 분류 카테고리는 현재 사용자 사업 맥락에 바로 맞지 않아, 도입 전 taxonomy 재설계가 필요하다.
- 외부 레포 기준의 장단점은 2026-04-20 시점 GitHub 상태를 바탕으로 정리했으므로 upstream 변경 시 결론이 달라질 수 있다.
- 의미기반 분류를 붙일 경우 API 비용, 응답 지연, 실패 처리 정책을 별도로 설계해야 한다.

## 다음 액션

- AI 기반 태그 보조를 실제로 검토한다면 현재 `auto-tag` 규칙 구조에 맞는 카테고리 체계를 먼저 정의한다.
- 필요 시 외부 레포 코드를 직접 가져오지 말고, LLM 보조 분류만 얇은 PoC로 별도 설계한다.
- 이후 구현 단계로 넘어가면 분류 정확도, 비용, 실패 처리 기준을 포함한 별도 plan을 작성한다.

## 참고 자료

| 출처 | 용도 |
|------|------|
| [saved-thereads-crawler](https://github.com/shinsooshinsoo/saved-thereads-crawler) | 검토 대상 외부 레포 주소 및 구조 확인 |
| [scrap_sns](https://github.com/ahnbu/scrap_sns.git) | 현재 프로젝트 기준 레포 주소 |
| [`thread_scrap.py`](../thread_scrap.py), [`thread_scrap_single.py`](../thread_scrap_single.py), [`utils/post_schema.py`](../utils/post_schema.py), [`utils/common.py`](../utils/common.py), [`server.py`](../server.py) | 수집 경로, 스키마, 정제, 뷰어 비교 근거 |
