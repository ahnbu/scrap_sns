---
title: temporal-weaving-hartmanis plan 검수보고서
created: 2026-04-11
session_id: 54973faf-dfdf-4f72-9cf5-edd416fd5394
plan: C:/Users/ahnbu/.claude/plans/temporal-weaving-hartmanis.md
spec: D:/vibe-coding/scrap_sns/docs/specs/20260411_01_threads-schema-drift-정비.md
reviewer: Codex (gpt-5.4) + Claude 코드베이스 확증
---

# Plan 검수보고서: temporal-weaving-hartmanis

## Codex 검수보고서 (전문)

> **목적 달성 가능성은 낮음.**

### 요약 판정

이 plan은 증상 완화는 가능해 보이지만, spec이 요구한 "재발 방지까지 닫힌 실행안"으로는 덜 닫혀 있다. 특히 재발 방지의 핵심인 생성 게이트가 spec의 엄격 모드에서 soft normalize/skip으로 후퇴했고, 검증 절차 일부가 그대로는 실행 불가능해서 완료 판단 근거가 약하다.

### 치명 결함

`thread_scrap_single.py`를 재발 방지의 핵심 경로처럼 다루는데, spec 본문 자체가 이 파일은 "write 없음"이라고 적고 있다. 실제 저장 경로가 아니면 이 수정은 효과가 없다.

spec은 Threads 생성 게이트에 엄격 모드(assert)를 채택했는데, plan Step 6은 `normalize -> continue`와 경고로 바꿨다. 이러면 drift가 즉시 실패로 드러나지 않고 조용한 skip이나 자동 보정으로 묻혀 재발 감지가 늦어진다.

검증 단계가 실행 계약으로 성립하지 않는다. `python server.py &`, `node -e ... snsFeedData`, `python -c "검증 스크립트..."`는 그대로는 신뢰 가능한 검증 절차가 아니어서, plan이 끝나도 "정말 고쳐졌는지"를 증명하기 어렵다.

문서 안의 실행 예시가 자체 규칙과 충돌한다. 직접 `git add/commit`, `rm -rf`, bash 스타일 명령이 섞여 있어, 실행자가 plan을 그대로 따를수록 복구보다 2차 사고 가능성이 커진다.

### 트레이드오프

얻는 것은 분명하다. Threads의 `Unknown`/깨진 링크를 빠르게 줄이고, 레거시 583건 교정과 viewer fallback으로 체감 문제를 바로 낮출 수 있다.

잃는 것도 크다. `post_schema.py`, migration script, fallback 유지, `_deprecated`, `.gitignore` 예외, 이중 백업까지 한 번에 묶으면서 운영 포인트가 늘어난다. 작은 drift 1종을 잡으려다 저장 정책과 생성물 관리까지 같이 흔들 수 있다.

### 과최적화 징후

Threads 1종 drift 문제인데, 커밋 6개 분리, 이중 백업, 공용 유틸 영구화, deprecated 정리, output 추적 정책 변경까지 한 세트로 묶었다. 문제 해결보다 주변 구조 정리가 더 커질 조짐이 있다.

`convert_data.py` 이동과 `output_total` 추적 예외는 핵심 증상 해결과 직접 연결이 약하다. 재발 방지라는 명분 아래 유지비가 큰 변경이 섞여 있다.

### spec-plan 불일치

spec D3는 Threads에 엄격 모드(assert) 적용, backfill만 관대 모드다. plan Step 6은 producer/consumer 모두 soft normalize/continue/경고로 바뀌어 핵심 결정이 뒤집혔다.

spec F2는 `thread_scrap_single.py`에 write 경로가 없다고 적는다. 그런데 plan Step 6-c는 "저장 직전" normalize를 넣겠다고 해서 전제와 실행안이 충돌한다.

spec의 성공 기준 3은 `total_full` 전체 975건 전수 검증이다. plan Step 3-d는 threads subset `invalid=0`만 확인하므로 완료 기준과 검증 범위가 다르다.

spec D6는 기존 `total_scrap.py` 경로 활용이 채택안인데, plan Step 4는 결국 임시 인라인 스크립트로 우회한다. 재현성 측면에서 후퇴다.

### 검증 불가

실제 코드에서 `thread_scrap.py`, `thread_scrap_single.py`, `web_viewer/script.js`의 현재 경로와 저장 흐름이 plan/spec 설명과 일치하는지는 검증 불가다.

Threads 659건/583건, total 975건, `convert_data.py`의 실제 사용 여부, `.gitignore` 상태, `total_scrap.py`의 병합 전용 모드 부재는 이 보고서 범위에서는 검증 불가다.

`web_viewer/data.js`가 Node `require` 방식 검증에 맞는 구조인지, 브랜치 백업/push/Playwright/DevTools 검증 절차가 실제 환경에서 그대로 동작하는지도 검증 불가다.

---

## Claude 코드베이스 확증 / 반박

각 피드백 항목을 실제 코드·데이터로 검증한다.

### ✅ 확증 — spec F2 vs plan Step 6-c 충돌은 실제 존재하지만, **spec F2가 틀렸음**

Codex 지적: "spec은 thread_scrap_single.py write 없음이라 했는데 plan은 write 수정."

**실제 코드 확인 결과**:
- `thread_scrap_single.py:135` — `with open(latest_full_path, 'w', encoding='utf-8-sig') as f: json.dump(full_content, f, ...)` → **write 존재**
- `thread_scrap_single.py:194` — `with open(today_full_path, 'w', ...)` → **write 존재**
- `thread_scrap_single.py:237, 244` — simple/full write → **write 존재**
- `thread_scrap_single.py:369` — simple write → **write 존재**

→ **spec F2의 "write 없음" 기술은 부정확**. 이전 탐색 에이전트가 "`post['username'] = ...` 같은 field write가 없다"는 의미로 보고한 것을 spec에 "write 경로 없음"으로 잘못 옮긴 것. 실제로는 write 경로가 5군데 존재하며, 모두 dict 전체를 파일에 쓴다.

→ **영향**: spec F2 정정 필요. plan Step 6-c가 "저장 직전 normalize"를 노리는 방향 자체는 맞지만, 구체적 개입 지점은 line 다르다.

### 🚨 **Codex가 놓친 더 심각한 결함 — 레거시 생성원 오진**

plan과 spec 모두 레거시 583건의 원인을 `thread_scrap.py:127-135` backfill로 지목한다. 그러나 실제 데이터 검증:

```
threads total=659, merged=583, legacy(no username)=583
```

**레거시 583건 = 병합 타래 583건 = `is_merged_thread: true` 레코드 전체**.

원인은 `thread_scrap_single.py:65-84` `merge_thread_items` 함수:
```python
def merge_thread_items(thread_items):
    ...
    root = sorted_items[0]
    ...
    merged_post = root.copy()  # ← root가 레거시면 병합 결과도 레거시
    merged_post['full_text'] = merged_text
    merged_post['media'] = all_media
    merged_post['is_merged_thread'] = True
    return merged_post
```

- `root`는 simple DB에서 읽은 레거시 레코드(username/url 없음)일 가능성이 높음.
- 병합 후 `merged_post`는 `full_text`만 갱신되고 username/url은 그대로 빈 채 남음.
- 이 결과가 `promote_to_full_history` → `thread_scrap_single.py:135` write로 파일에 저장됨.

→ **plan Step 6의 backfill 수정은 원인 제거가 아님**. backfill은 **과거 1회성** 마이그레이션 경로이고, **지속적 생성원은 `merge_thread_items`**. plan Step 6에 `merge_thread_items` 수정이 반드시 추가되어야 함.

→ **root cause 재정의**: "Threads Consumer가 simple DB의 레거시 root를 병합·저장하면서 표준화를 건너뜀." plan과 spec 모두 이 경로를 놓쳤다.

### ✅ 확증 — spec D3 엄격 모드 vs plan Step 6 soft normalize 불일치

- SPEC `docs/specs/20260411_01_threads-schema-drift-정비.md` D3 명시: "Threads 파이프라인에는 **엄격 모드**를 적용. backfill 구 경로처럼 필드 누락이 확실한 곳만 예외적으로 관대 모드."
- Plan Step 6-b (Producer): `normalize_post(post)` → 재시도 → `continue` = **자동 보정 + silent skip**
- Plan Step 6-c (Consumer): `normalize_post` → 실패 시 경고만 = **관대 모드**
- Plan Step 6-a (backfill): `normalize_post` → 실패 시 continue = spec과 일치

→ **spec의 "엄격 모드" 정의(assert 실패)가 plan에서 완화됐음**. Codex 지적 정확. 수정 필요.

### ✅ 확증 — 검증 절차가 실행 계약으로 불성립

- Step 9-a `python server.py &` — Windows bash에서 `&` 백그라운드 신뢰성 낮고 프로세스 회수 미기술
- Step 9-c "DevTools MCP로 Unknown 카운트 확인" — 구체 evaluate_script 코드 미제공 (`document.querySelectorAll('article h3')`는 elements 리스트만 반환, 텍스트 "Unknown" 카운트 로직 없음)
- Step 4 `node -e "require('./web_viewer/data.js'); console.log(snsFeedData.posts.length)"` — `web_viewer/data.js`는 `const snsFeedData = {...};`로 시작, Node `require`는 module.exports 없으면 undefined 반환 → **작동 안 함**
- Step 9-g `python -c "검증 스크립트 — 새 5건이 validate_post 통과"` — 문자열 자체가 주석, 실제 검증 코드 누락

→ 검증 단계가 "실행하면 pass/fail이 자동 판정되는 스크립트"가 아니라 "사람이 판단하는 수동 체크리스트"에 가까움. 자동화 필요.

### ✅ 확증 — CLAUDE.md 규정 위반 예시가 plan에 존재

- Step 0 `git add -A`, `git commit -m ...` — CLAUDE.md: "커밋할 때는 cp 스킬을 사용하라. git add/commit을 직접 실행하지 마라"
- 롤백 절차 `rm -rf D:/vibe-coding/scrap_sns` — CLAUDE.md: "삭제는 `trash` 명령을 사용하라. `rm`/`rmdir`/`del`/`Remove-Item` 금지"
  - plan 본문이 옆에 "← trash 사용: trash D:/vibe-coding/scrap_sns"로 주석을 달아놨으나, 실행 예시 자체가 금지 명령
- Step 0-b `cp -r D:/vibe-coding/scrap_sns ...` — CLAUDE.md 금지는 아니지만 Windows bash에서 수 GB 복사가 수십 분 걸릴 수 있어 주의 필요

→ Codex 지적 정확. plan의 실행 예시를 CLAUDE.md 규정 준수 형태로 재작성 필요.

### ✅ 확증 — spec 성공 기준 3번과 plan Step 3-d 검증 범위 불일치

- SPEC 성공 기준 3: "`validate_post`를 `output_total/total_full_*.json`의 전 레코드(975건)에 돌려 누락 필드 리스트가 모두 빈 배열"
- Plan Step 3-d: Threads subset 659건만 `invalid=0` 확인

→ LinkedIn 237건 + X 79건은 drift 없다고 F1/F5에서 확인됐으므로 실질적으로 문제 없지만, 성공 기준의 "전 레코드"를 엄격히 해석하면 plan 검증이 부족. **수정 용이**: `threads subset` → `all 975건`으로 변경.

### ✅ 확증 — spec D6 vs plan Step 4 재생성 방식 불일치

- SPEC D6: "`total_scrap.py` 기존 경로(`:274-282`) 활용"
- Plan Step 4: 기존 경로가 수집 없이 실행 불가 확인 후 임시 인라인 스크립트로 우회

→ plan이 spec을 수정하지 않고 우회한 형태. 정합성 낮음. **선택지**:
- A) spec D6를 "임시 인라인 스크립트"로 수정
- B) `total_scrap.py`에 `--mode merge_only` 같은 경로 추가 (범위 확대)

### 📊 데이터 카운트 전수 확증

plan/spec에 기재된 수치를 실제 데이터로 재확인:

```python
# output_total/total_full_20260411.json 기준
total: 975
by_platform: {'linkedin': 237, 'threads': 659, 'x': 79}
threads: total=659, merged=583, legacy(no username)=583
```

→ spec F1의 수치 전부 일치. **단, 새 사실**: "레거시 583 = 병합 타래 583". 이 등식이 spec/plan에 없고, 원인 분석이 틀어진 증거.

### 📊 CLAUDE.md 규정 vs plan 실행 예시 매핑

| CLAUDE.md 규정 | plan 위치 | 위반 여부 |
|---|---|---|
| cp 스킬로 커밋 | Step 0, Step 10 | Step 0 위반 / Step 10은 "cp 스킬 사용" 명시, OK |
| trash 사용 | 롤백 절차 | 위반 (주석 있으나 본 명령이 `rm -rf`) |
| 세션DB `node:sqlite` 전용 | - | 해당 없음 |
| utf-8 encoding 명시 | 인라인 스크립트 | OK (`encoding='utf-8-sig'`) |

### 검증 불가 항목

- `total_scrap.py --mode merge_only` 신설 가능성 — 코드 구조 추가 분석 필요
- Step 7에서 `convert_data.py`를 `_deprecated/`로 옮길 때 import 경로 손상 여부 — `web_viewer/convert_data.py`가 다른 파일에서 import되는지 확인 필요
- `.gitignore:54`에 `!output_total/total_full_*.json` 예외 추가 시 `output_*` 와일드카드와의 우선순위 실제 적용 여부 — git ignore rule은 후행 negation이 상위 디렉토리 ignore를 이길 수 없음. `output_total/` 자체가 `output_*`로 ignore되면 negation 무효.

### 🚨 검증 과정에서 추가 발견 — gitignore 예외의 구조적 문제

git `.gitignore` rule: **디렉토리가 ignore되면 그 하위 파일의 negation은 무효**.

- `.gitignore:54` `output_*` → `output_total/` 디렉토리 자체가 ignore됨
- `!output_total/total_full_*.json` 추가해도 git는 `output_total/` 디렉토리를 스캔하지 않으므로 negation 무시

**해결책**: 디렉토리와 파일 negation을 분리
```
output_*
!output_total/
output_total/*
!output_total/total_full_*.json
```
→ plan에 이 상세가 없으면 Step 8이 실패한다. 확증 필요 항목.

---

## 종합 판정 및 수정 권고

### 치명 결함 3가지 (실행 전 반드시 수정)

1. **레거시 생성원 오진** — `merge_thread_items`(`thread_scrap_single.py:65`)가 실제 원인. plan Step 6에 해당 함수 수정 추가 필수.
2. **엄격 모드 후퇴** — plan Step 6-b (Producer)는 spec D3에 따라 `assert` 또는 명시적 실패로 복원.
3. **gitignore 예외 구조 불완전** — `!output_total/` 디렉토리 negation부터 단계적으로 작성.

### 중요 결함 3가지 (실행 전 권장 수정)

4. 검증 절차 자동화 — Step 4, Step 9 각 검증을 pass/fail 스크립트로 재작성
5. CLAUDE.md 규정 준수 — Step 0 커밋은 cp 스킬 경유, 롤백 절차는 `trash` 사용
6. spec D6 vs plan Step 4 불일치 해소 — spec을 plan 쪽으로 수정

### 과최적화 검토 — 유지 권고

Codex가 지적한 "과최적화" 항목들 중:
- `utils/post_schema.py` 신설 — 유지 (재발방지 핵심)
- `migrate_schema.py` 복구 — 유지 (1회성이지만 추적성 확보)
- 이중 백업 — 유지 (사용자 명시 요청)
- `convert_data.py` deprecated — 유지 (사용자 요청 "스파게티 정리" 맥락)
- `.gitignore` 예외 — 유지하되 위 #3 구조적 문제 해결 선결

→ 사용자 요청 맥락("재발방지까지 정비")과 Codex의 "과최적화 경고"는 가치관 차이. 사용자 의도 우선.

### 결론

**plan 전면 재작성 수준의 수정이 필요**. 특히 근본 원인이 `merge_thread_items`로 재정의되면서 Step 6의 타깃 파일·함수가 바뀐다. spec도 F2 정정 + 근본 원인 섹션 추가가 필요하다.
