---
model: "Gemini 3.1 Pro (High)"
performed_at: "2026-07-09 19:43:56"
---

# Plan Check Reviewer Report

## Verdict
**수정 필요** (실행 전 `existing_ids.json` 경로 경합(Race Condition) 문제 수정 필수)

## 목적 달성 가능성
**높음.**
Node `applyExistingStreak` 헬퍼를 도입하여 페이지를 순회하며 20건 연속 기수집 ID가 관측되면 즉시 루프를 조기 탈출(`break`)하도록 구성한 접근은 목표(update 시 빠른 종료)를 확실하게 달성합니다. 또한, 전체 확인이 필요한 `all` 모드는 기존 `--until-exhausted` 동작을 그대로 유지하여 요구사항을 충족합니다. 미관측 기존 글을 강제 삭제하지 않고 유지(`preserved_not_deletion_candidate`)하는 병합 정책도 데이터 유실을 방지하는 올바른 설계입니다.

## Blocking Issues
1. **`existing_ids.json` 파일 경로의 동시성 결함 (경합 위험)**
   - **위치**: Task 3 / Step 4의 `write_existing_ids_file(raw_dir, existing_codes)` 구현부.
   - **내용**: `ids_path = os.path.join(os.path.dirname(raw_dir), "existing_ids.json")`로 지정하면 파일이 `output_linkedin/opencli_runtime/raw/existing_ids.json`에 고정적으로 생성됩니다.
   - **문제**: `--mode update`가 여러 터미널/환경에서 동시에 실행될 경우, 고정된 파일명(`existing_ids.json`)을 공통 부모 폴더에 쓰므로 덮어쓰기(Race condition)가 발생하여 엉뚱한 ID 세트가 수집기에 주입될 치명적 결함이 있습니다.
   - **해결**: 파일 경로를 고유한 `raw_dir`(타임스탬프 기반 디렉토리) 내부로 변경하거나, 파일명에 타임스탬프를 명시해야 합니다.

## Required Fixes
- [ ] **Task 3 / Step 4 수정**:
  `existing_ids.json`의 생성 위치를 `raw_dir` 내부로 변경하여 동시 실행 안전성을 확보하십시오.
  ```python
  # 수정 제안
  def write_existing_ids_file(raw_dir, existing_codes):
      existing_ids = sorted(str(code) for code in existing_codes if code)
      os.makedirs(raw_dir, exist_ok=True)
      ids_path = os.path.join(raw_dir, "existing_ids.json")
      save_json(ids_path, existing_ids)
      return ids_path
  ```

- [ ] **Task 2 / Step 4 구체화 (권장)**:
  "For the `fetchedIds` branches, apply the same pattern."이라는 지시가 AI/개발자에게 변수 스코프 혼란을 줄 수 있습니다. 실제 `mjs` 파일에는 `ids`뿐만 아니라 `fetchedIds`를 사용하는 분기가 두 군데 더 존재합니다(line 221, 307).
  실행 가능성을 높이기 위해 `fetchedIds` 분기용 교체 코드 블록도 아래와 같이 명시해 주는 것을 권장합니다.
  ```javascript
  const freshIds = observeIdsForFastStop(fetchedIds);
  const before = seenIds.size;
  freshIds.forEach((id) => seenIds.add(id));
  const newIds = seenIds.size - before;
  ```

## 트레이드오프·리스크
1. **조기 종료 시 아주 오래된 글의 상태 변경 사항 추적 불가 (과최적화 트레이드오프)**
   - **설명**: 사용자가 예전에 저장한 글을 최근에 "저장 취소 후 다시 저장"하여 순서가 바뀌거나, 과거 글의 내용/메타데이터가 백그라운드에서 업데이트되었을 경우, 20개 연속 관측(`streak`)에 걸려 해당 페이지 이후의 변동 사항을 모두 놓칠 수 있습니다.
   - **평가**: 이 plan은 `--mode all` 전체 검증을 여전히 유지하므로, 가끔씩 `--mode all`을 돌려서 이 트레이드오프(과거 데이터 갱신 누락)를 주기적으로 보정할 수 있습니다. 시스템적으로 합리적이고 안전한 절충안입니다.
2. **Metadata 정책 구체화의 장점**:
   - `unobserved_existing_policy` 필드를 도입하여 `preserved_not_deletion_candidate`를 기록하게 한 점은 훌륭합니다. 차후 DB 정리나 리팩터링 시에 '관측되지 않았지만 지우면 안 되는 데이터'임을 명확히 추적할 수 있는 튼튼한 데이터 파이프라인 계약을 형성합니다.
