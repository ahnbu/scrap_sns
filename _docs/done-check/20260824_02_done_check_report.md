---
title: Done Check Reviewer Report
created: 2026-08-24 12:39
session_id: 4efc85ee-1841-4417-bd43-ced95062bdc2
session_path: C:/Users/ahnbu/.claude/projects/D--vibe-coding-scrap-sns/4efc85ee-1841-4417-bd43-ced95062bdc2.jsonl
ai: claude
---

# Done Check Reviewer Report

## Verdict
승인 필요

판정 기준에 따라, 확정된 구현 범위였던 Threads 중복 방지 코드 수정(B-1)이 전제 붕괴(파서 무력화)로 인해 실행 보류되고 사용자 판단을 기다리고 있으므로 `승인 필요`로 판정한다. 또한, X ID 대조 가드(C-1)에 데이터 오염 재발 리스크(Important)가 발견되어 완료를 차단한다.

## Verification Audit
- **W1 (C-1 X ID 대조 가드):** 구현됨. 단, 하위 호환 폴백에 취약점이 있음. 테스트(`pytest tests/unit tests/contract`) 156 passed 확인됨. (근거: 계획서 5.1 요약)
- **W2 (C-2 X 리셋·재수집):** 61건 리셋 후 60건 성공, 1건 백업 복원. `scripts/verify_twitter_reset.py` 단언 통과로 오염 해소 확인. (근거: 계획서 5.1, 5.2)
- **W3 (B-0 Threads 실패 진단):** 파서 무력화(응답 구조 변경)로 원인 진단 완료. (근거: 계획서 5.4)
- **W4 (B-1 Threads alias 조건 완화):** 미실행 (전제 붕괴로 인한 정당한 보류).
- **W5 (B-2 Threads 중복 정리, D 중복 키 보강):** 완전중복 20그룹 제거, alias 3건 처리 완료. `scripts/verify_threads_dedupe.py` 단언 통과. headless 뷰어 총건수 1999건 일치 확인. (근거: 계획서 5.1, 5.2)
- **산출물 및 커밋 범위:** 7개의 신규 스크립트가 `.gitignore` 화이트리스트에 정상 등록되었으며(`cat .gitignore` 로 확인), 백업 디렉토리(`_docs/backup/`)는 커밋에서 제외됨. (근거: 계획서 3.5 및 `.gitignore` 실측 일치)

## Blocking Findings
- Claim: X ID 대조 가드의 하위 호환 폴백이 원래 막으려던 오염을 다시 허용할 여지가 있음 (지시 마).
- Evidence: `utils/twitter_cli_adapter.py:50-52` (`if not any(str(item.get("id") or "") for item in items): return items[0]`) 및 `tests/unit/test_twitter_cli_adapter.py` 의 `test_select_focal_tweet_falls_back_when_payload_has_no_ids` 테스트 케이스.
- Impact: `twitter_cli`의 응답 구조가 예기치 않게 변경되어 `id` 필드가 누락될 경우, 스크립트는 안전하게 실패하는 대신 첫 번째 항목(`items[0]`)을 맹목적으로 채택하게 된다. 만약 첫 번째 항목이 타겟 트윗이 아닌 부모 트윗(답글의 경우)이라면, 이전에 발생했던 "저자 및 본문 오염(C-1, C-2)" 현상이 동일하게 재발하여 중앙 데이터셋을 조용히 손상시킨다.
- Severity: Important
- Fix: `utils/twitter_cli_adapter.py`의 `select_focal_tweet` 함수에서, 호출자가 `expected_id`를 전달했음에도 payload 항목들에 `id`가 하나도 없다면 `items[0]`을 반환하지 말고 `None`을 반환(Fail-safe)하도록 수정하여 데이터 오염을 원천 차단해야 한다.

## Advisory Findings
- Claim: B-1 미실행은 승인 없는 범위 축소가 아닌, 전제 붕괴에 따른 정당한 보류임 (지시 가, 나).
- Evidence: 계획서 5.4 "B-1 미실행 — 사용자 판단 필요"
- Impact: Threads 상세 수집 파서 자체가 응답 구조 변경(`result.data.media` 로 이동)으로 인해 0건을 반환하는 상황이다. 상세 수집 성공을 전제로 하는 B-1(중복 방지 조건 완화) 분기에 도달조차 할 수 없으므로 강행은 무의미하다. 원 요청인 '진단'을 통해 파서 무력화라는 근본 원인을 밝혔으나, 파서 전면 재작성은 "본문 결측·중복 진단"이라는 원래 스코프를 넘어서는 대형 작업이므로 사용자 승인을 대기한 것은 올바른 엔지니어링 판단이다. 요구사항 누락이 아니다.
- Severity: Advisory
- Fix: 사용자는 Threads 파서 재작성(DOM/API 구조 대응)을 새 세션으로 진행할지 여부를 결정해 지시해야 한다.

- Claim: 계획 대비 달라진 점 6건은 모두 데이터 손실을 막기 위한 정당한 방어적 대응임 (지시 다).
- Evidence: 계획서 5.5 "계획 대비 달라진 점"
- Impact: 특히 `total_scrap.py --mode update` 실행이 전체 수집기를 가동시켜 42건의 `fail_count`를 임계치(3)까지 올려 영구 제외될 뻔한 상황을 감지하고, 즉시 백업에서 원상 복구한 뒤 수집 없는 전용 병합 스크립트(`scripts/merge_total_only.py`)를 짠 것은 치명적인 데이터 손실을 막은 훌륭한 조치다. 나머지 C-2 부분 복원 및 미디어 병합 추가 조치 역시 기존 데이터를 보호하기 위한 적절한 대응이었다.
- Severity: Advisory
- Fix: 없음. 현재 조치 유지.

## Unverified Concerns
없음

## Rationale
1. **판정(Verdict) 사유:** AI는 계획된 B-1 작업을 진행하려 했으나, 대상 플랫폼(Threads)의 API 응답 구조 변경으로 전제가 붕괴되었음을 확인했다. 무리하게 범위를 확장하지 않고 작업을 보류한 후 사용자 승인을 요청한 것은 정당하나, 계획된 구현 범위가 유보되어 사용자 승인을 대기 중이므로 규정에 따라 `승인 필요`로 판정한다.
2. **Blocking Finding 사유:** 추가 지시 (마)에 따라 검토한 결과, `utils/twitter_cli_adapter.py`에 구현된 "id가 없을 때 첫 번째 항목 반환" 폴백은 과거 데이터 오염의 핵심 원인(순서에 의존한 맹목적 채택)과 동일한 구조적 취약점을 안고 있다. 외부 도구(`twitter_cli`)의 출력 변화 시 조용히 데이터가 오염(Data Corruption)되는 결과를 낳으므로 Important 이슈로 지정해 수정(Fail-safe)을 요구한다.
3. **기타 지시사항 반영:** 지시 (가, 나)의 B-1 보류, (다)의 돌발 상황 대응, (라)의 커밋 산출물 범위는 모두 안전하고 타당한 조치로 판단되어 Advisory 로 명시하고 완료를 차단하지 않았다.
