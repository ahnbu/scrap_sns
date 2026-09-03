---
title: LinkedIn OpenCLI 디버깅배너 정리 수행계획
created: 2026-07-09 14:19
tags:
  - scrap_sns
  - linkedin
  - opencli
  - implementation-plan
session_id: codex:019f44b8-c2e6-7b30-8fc4-95124148ca4f
session_path: C:/Users/ahnbu/.codex/sessions/2026/07/09/rollout-2026-07-09T11-33-12-019f44b8-c2e6-7b30-8fc4-95124148ca4f.jsonl
ai: codex
status: implemented
---

# LinkedIn OpenCLI 디버깅배너 정리 수행계획

## 목적

LinkedIn OpenCLI 수집 완료 후 사용자가 보고 있는 SNS Scrap Chrome 창 상단에 남는 OpenCLI 디버깅 배너를 제거한다.

이번 1차 작업의 목표는 수집 탭/창 정책을 새로 설계하는 것이 아니라, OpenCLI가 Chrome에 남긴 디버깅 연결과 내부 세션 점유, 백그라운드 daemon 점유를 안전하게 정리하는 것이다.

## 논의 과정 요약

| 단계 | 당시 판단 | 현재 결론 |
|---|---|---|
| 최초 문제제기 | LinkedIn 수집 중 Chrome 상단에 OpenCLI 디버깅 배너가 뜸 | ✅ OpenCLI가 Chrome 디버깅 연결을 만드는 것은 맞다 |
| 수집 완료 후 배너 잔존 | 명시적 종료 로직 누락 의심 | ✅ 종료 cleanup 부족으로 판단한다 |
| 초기 대응 가설 | `opencli browser ... close`면 창/배너가 정리될 수 있음 | ❌ `close`는 창 닫기가 아니라 tab lease 해제다 |
| 추가 테스트 | `opencli daemon stop`만 실행하면 사라질 수 있음 | ❌ daemon stop만으로는 사용자 화면 배너 제거를 보장하지 않는다 |
| 핵심 테스트 | `unbind -> close -> daemon stop` 실행 | ✅ SNS Scrap 탭 배너 제거와 daemon 종료가 확인됐다 |
| 수집 탭 닫기 가설 | `pageId` 저장 후 `tab close <pageId>` 필요 | ⚠️ 실제 수집 탭 잔존 문제가 확인될 때만 필요하다 |
| 빈 `about:blank` 창 | 별도 정리 로직 필요 | ❌ 테스트 부산물 가능성이 높아 1차 범위에서 제외한다 |

## 확인된 런타임 근거

테스트는 실제 스크랩을 실행하지 않고, 창/탭 레벨만 축소 재현했다.

확인된 사실:

- 기준선에서 `localhost:5000` SNS Scrap 탭에는 OpenCLI 배너가 없었다.
- OpenCLI로 수집용 대체 탭 `https://example.com`을 열자 별도 Chrome 창이 생성됐다.
- 별도 창이 생성됐음에도 기존 `SNS Feed Viewer - Chrome` 창 상단에도 OpenCLI 디버깅 배너가 붙었다.
- 아래 종료 순서 실행 후 SNS Scrap 탭은 유지됐고, 배너는 사라졌다.
- 최종 `opencli daemon status`는 `Daemon: not running`이었다.

검증된 종료 순서:

```bash
opencli browser linkedin_saved_production unbind
opencli browser linkedin_saved_production close
opencli daemon stop
```

## 원인 진단

LinkedIn OpenCLI 수집 종료 후 `browser session`과 `daemon` 정리가 부족해서 Chrome 디버깅 연결이 남고, 그 결과 SNS Scrap 탭이 들어 있는 기존 Chrome 창에도 디버깅 배너가 남는다.

따라서 이번 작업의 직접 원인은 "수집용 탭이 닫히지 않음"이 아니라 "OpenCLI 디버깅 연결과 세션 점유가 충분히 해제되지 않음"이다.

## 각 명령의 역할

각 명령의 역할은 다르다.

| 명령 | 왜 필요한가 | 사용자에게 유리한 점 |
|---|---|---|
| `opencli browser linkedin_saved_production unbind` | OpenCLI가 Chrome에 붙어 있는 디버깅 연결을 해제한다. | ✅ SNS Scrap 탭 상단의 디버깅 배너를 없애는 핵심이다. |
| `opencli browser linkedin_saved_production close` | OpenCLI 세션의 tab lease를 해제한다. 창을 닫는 명령은 아니다. | ✅ OpenCLI 내부 세션 점유를 정리한다. |
| `opencli daemon stop` | OpenCLI 백그라운드 daemon 프로세스를 종료한다. | ✅ 수집 후 OpenCLI가 계속 떠 있는 상태를 막는다. |

정리하면:

```bash
unbind      # Chrome 디버깅 연결 해제
close       # OpenCLI 세션 점유 해제
daemon stop # OpenCLI 백그라운드 프로세스 종료
```

## 기존 코드와 새로 필요한 것

현재 확인된 코드 기준으로 나누면 다음과 같다.

| 항목 | 기존에 있었나 | 판단 |
|---|---:|---|
| `opencli daemon stop` | 있음 | `linkedin_scrap.py`의 `finally`에서 실행되는 구조가 있다. |
| `opencli browser ... unbind` | 없었거나, 수집기 쪽에만 불완전하게 들어간 상태 | 이번 문제의 핵심 보완 대상이다. |
| `opencli browser ... close` | 없었거나, 수집기 쪽에만 불완전하게 들어간 상태 | `unbind`와 함께 세션 점유 해제용으로 필요하다. |
| `tab close <pageId>` | 없음 | 지금은 추가하지 않는 게 맞다. 실제 문제는 탭 잔존이 아니라 디버깅 배너/점유 잔존이다. |

## 최종 작업 대상

수정 대상 후보:

- `linkedin_scrap.py`
  - 기존 `stop_opencli_daemon()` 흐름 유지
  - daemon stop 전에 parent process 기준의 authoritative browser session cleanup을 보장
  - `SCRAP_SNS_KEEP_OPENCLI_DAEMON=1`이어도 browser `unbind`와 `close`는 실행한다. 이 옵션은 daemon 유지 여부만 제어하고, 배너 제거를 막으면 안 된다.
- `scripts/linkedin_opencli_shadow_collect.mjs`
  - 이미 collector 내부 cleanup이 있다면 동작과 호출 순서를 확인
  - 중복 cleanup이 있더라도 실패가 수집 결과 저장 흐름을 깨지 않도록 정리
- `tests/integration/test_linkedin_opencli_pipeline.py`
  - 이미 중간 수정이 들어갔다면 `tab close` 중심 테스트는 제거하고 cleanup 명령 호출/실패 격리 테스트로 정리
  - cleanup 기대 순서는 `unbind`, `close`, `daemon stop`이다.
  - `unbind` 실패 시에도 `close`와 `daemon stop`을 계속 시도하는지 검증한다.

1차 수정의 목표 명령:

```bash
opencli browser linkedin_saved_production unbind
opencli browser linkedin_saved_production close
opencli daemon stop
```

구현 방향:

- 기존 `daemon stop`은 유지한다.
- 그 전에 `unbind`와 `close`를 실행한다.
- cleanup 실패는 경고로 남기되, 이미 완료된 수집 결과 저장 흐름을 망치지 않는다.
- 단, 수집 자체 실패와 cleanup 실패는 로그에서 구분되게 한다.

## 제외 대상

| 제외 항목 | 처리 | 근거 |
|---|---|---|
| `tab close <pageId>` / 수집 탭 강제 종료 | ❌ 보류 또는 제거 | 실제 문제는 탭 잔존이 아니라 SNS Scrap 탭의 디버깅 배너 잔존이다. |
| `browser open` 반환 `pageId` 저장 | ❌ 보류 | `tab close`를 1차 범위에서 제외하므로 필수 데이터가 아니다. |
| 빈 `about:blank` / `OpenCLI Browser` 창 정리 | ❌ 제거 | 테스트 부산물 가능성이 높고, 기존 수집 문제로 확정되지 않았다. |
| 사용자 Chrome 창을 탐색해 강제로 닫기 | ❌ 제외 | SNS Scrap 탭이나 사용자의 일반 탭을 건드릴 위험이 있다. |
| LinkedIn 수집 로직/파서/저장 정책 변경 | ❌ 제외 | 이번 원인은 수집 품질이 아니라 cleanup 부족이다. |

## 현재 중간 diff 정리 원칙

중간 수정에는 진단 전 가설이 섞여 있을 수 있다. 전부 폐기하지 말고, 진단 결과와 맞는 부분만 선별 보존한다.

| 변경 유형 | 처리 | 이유 |
|---|---|---|
| `unbind -> close -> daemon stop` 정리 | ✅ 유지 후보 | 실제 테스트로 배너 제거와 daemon 종료에 필요성이 확인됐다. |
| `tab close <pageId>` / 수집 탭 강제 종료 | ❌ 보류 또는 제거 | 실제 문제는 탭 잔존이 아니라 SNS Scrap 탭의 디버깅 배너 잔존이다. |
| 빈 `about:blank` / OpenCLI Browser 창 정리 | ❌ 제거 | 테스트 부산물 가능성이 높고, 기존 수집 문제로 확정되지 않았다. |

권장 정리 방향:

1. 현재 diff를 먼저 확인한다.
2. `linkedin_scrap.py` 또는 OpenCLI collector 쪽에 들어간 변경 중 `unbind`, `close`, `daemon stop` 순서 보장만 남긴다.
3. `tab close`, `pageId 저장`, 빈 창 닫기 로직은 제거한다.
4. 테스트도 "탭이 닫힌다"가 아니라 "cleanup 명령이 호출된다 / 실패해도 수집 결과 저장 흐름을 망치지 않는다" 쪽으로 정리한다.
5. 그 다음 실제 수집 또는 축소 OpenCLI 시나리오로 배너 제거만 검증한다.

## Wave 계획

### Wave 1: 현재 diff 확인과 범위 축소

수행 내용:

- `git diff -- linkedin_scrap.py scripts/linkedin_opencli_shadow_collect.mjs tests/integration/test_linkedin_opencli_pipeline.py`로 중간 수정 내용을 확인한다.
- `tab close`, `pageId 저장`, 빈 창 닫기 로직이 있으면 1차 범위에서 제거한다.
- `unbind -> close -> daemon stop` 순서만 남긴다.

완료 기준:

- diff에 `tab close`, `pageId` 기반 강제 종료, Windows 창 강제 닫기 로직이 없다.
- diff에 browser session cleanup과 daemon cleanup의 순서가 드러난다.

검증 방법:

```bash
git diff -- linkedin_scrap.py scripts/linkedin_opencli_shadow_collect.mjs tests/integration/test_linkedin_opencli_pipeline.py
```

기대 결과:

- `unbind`와 `close` 호출이 확인된다.
- `daemon stop`은 cleanup 마지막 단계에 유지된다.
- `tab close` 관련 변경은 없다.

### Wave 2: cleanup 구현 정리

수행 내용:

- `linkedin_scrap.py`에 browser session cleanup helper를 둔다.
- helper는 `opencli browser linkedin_saved_production unbind`와 `opencli browser linkedin_saved_production close`를 순서대로 실행한다.
- 기존 `stop_opencli_daemon()`은 유지하되 browser session cleanup 이후 실행한다.
- cleanup 실패는 경고 출력 후 다음 cleanup 단계로 진행한다.

완료 기준:

- LinkedIn 수집 성공/실패와 무관하게 `finally`에서 browser session cleanup과 daemon cleanup이 실행된다.
- cleanup 실패가 수집 결과 parse/저장 성공 여부를 덮어쓰지 않는다.

검증 방법:

```bash
pytest tests/integration/test_linkedin_opencli_pipeline.py -q
```

기대 결과:

- cleanup 명령 호출 순서가 `unbind`, `close`, `daemon stop`으로 검증된다.
- `unbind` 실패 시에도 `close`와 `daemon stop` 시도가 유지된다.
- `SCRAP_SNS_KEEP_OPENCLI_DAEMON=1`일 때도 `unbind`와 `close`는 실행되고 `daemon stop`만 생략된다.

### Wave 3: 축소 OpenCLI 시나리오 수동 검증

수행 내용:

- 실제 스크랩은 실행하지 않는다.
- SNS Scrap 탭을 열어둔 상태에서 OpenCLI로 수집용 대체 탭을 연다.
- 배너가 SNS Scrap 창에 붙는지 확인한다.
- `unbind -> close -> daemon stop`으로 배너 제거와 daemon 종료를 확인한다.

완료 기준:

- SNS Scrap 탭은 유지된다.
- SNS Scrap 창 상단의 OpenCLI 디버깅 배너가 사라진다.
- `opencli daemon status` 출력이 `Daemon: not running`이다.

검증 방법:

```bash
opencli browser linkedin_saved_production open https://example.com --window background
opencli browser linkedin_saved_production unbind
opencli browser linkedin_saved_production close
opencli daemon stop
opencli daemon status
```

기대 결과:

```markdown
Daemon: not running
```

화면 확인:

- `localhost:5000` SNS Scrap 탭이 살아 있다.
- 상단 OpenCLI 디버깅 배너가 보이지 않는다.

증거 산출물:

- `docs/evidence/20260709_opencli_banner_before.png`
- `docs/evidence/20260709_opencli_banner_after.png`
- `docs/evidence/20260709_opencli_daemon_status.txt`
- `docs/evidence/20260709_opencli_manual_qa.txt`

### Wave 4: 사용자 화면 기준 최종 확인

수행 내용:

- 사용자가 실제로 쓰는 SNS Scrap 화면(`localhost:5000`)을 기준으로 확인한다.
- 전체 스크랩은 다시 실행하지 않는다. 이번 문제의 검증 대상은 게시글 수집 결과가 아니라 Chrome/OpenCLI 연결 정리이므로, 동일 OpenCLI session을 짧게 붙였다가 cleanup하는 축소 시나리오로 확인한다.
- 수집 결과 건수 자체가 아니라 cleanup 후 Chrome 배너 제거와 daemon 종료를 확인한다.

완료 기준:

- cleanup 완료 후 SNS Scrap 탭 상단에 OpenCLI 디버깅 배너가 남지 않는다. 이 화면 확인이 최종 gate이며, `daemon not running`만으로 완료 처리하지 않는다.
- `opencli daemon status`가 `Daemon: not running`이다.
- 수집 완료 로그와 cleanup 경고 로그가 구분된다.

검증 방법:

```bash
opencli daemon status
```

기대 결과:

```markdown
Daemon: not running
```

화면 확인:

- cleanup 완료 후 SNS Scrap 탭이 유지된다.
- 상단 OpenCLI 디버깅 배너가 보이지 않는다.

증거 산출물:

- `docs/evidence/20260709_opencli_banner_after_printwindow.png`
- `docs/evidence/20260709_opencli_daemon_status_final.txt`

## 수행 결과 기록

2026-07-09 KST 기준 수행 결과다.

| 항목 | 결과 | 증거 |
|---|---|---|
| 계획 검수 | ✅ 완료. `tab close`, `pageId`, 빈 창 정리 로직은 제외하고 `unbind -> close -> daemon stop`만 1차 범위로 확정했다. | 계획 검수 지적사항 반영, 본 문서의 제외 대상/완료 기준 갱신 |
| cleanup 테스트 | ✅ 통과. cleanup 순서, daemon 유지 옵션, `unbind` 실패 시 `close` 계속 시도를 검증했다. | `docs/evidence/20260709_opencli_pytest.txt` (`11 passed`) |
| 문법 검증 | ✅ 통과. Python collector와 Node helper 문법 오류가 없다. | `python -m py_compile linkedin_scrap.py`, `node --check scripts/linkedin_opencli_shadow_collect.mjs` |
| 축소 OpenCLI 화면 QA | ✅ 통과. 전에는 SNS Scrap Chrome 창 상단에 OpenCLI 디버깅 배너가 보였고, cleanup 후 같은 `SNS Feed Viewer - Chrome` 창 캡처에서 배너가 사라졌다. | `docs/evidence/20260709_opencli_banner_before.png`, `docs/evidence/20260709_opencli_banner_after_printwindow.png` |
| daemon 종료 | ✅ 통과. cleanup 후 OpenCLI daemon이 남아 있지 않다. | `docs/evidence/20260709_opencli_daemon_status_final.txt` (`Daemon: not running`) |
| 전체 업데이트 재실행 | ⚠️ 미수행. 사용자가 컴퓨터를 사용 중이어서 전체 수집 재실행은 과도하게 방해된다. 이번 결함의 검증 대상은 수집 데이터가 아니라 OpenCLI 연결 정리이므로 동일 session의 축소 화면 QA로 대체했다. | `docs/evidence/20260709_opencli_manual_qa.txt` |
| 커밋 | 대기 | cp 수행 예정 |

폐기한 증거:

- `docs/evidence/20260709_opencli_banner_after.png`: Chrome이 아니라 Codex 화면이 캡처되어 증거에서 제외한다.
- `docs/evidence/20260709_opencli_banner_after_user_surface.png`: Chrome 전면 전환이 실패해 Codex 화면이 캡처되어 증거에서 제외한다.

## 리스크와 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| `unbind` 실패 | 배너가 남을 수 있음 | 실패를 경고로 출력하고 `close`, `daemon stop`을 계속 시도한다. |
| `close` 실패 | OpenCLI 내부 세션 lease가 남을 수 있음 | 실패를 경고로 출력하고 `daemon stop`을 계속 시도한다. |
| `daemon stop` 실패 | 백그라운드 daemon이 계속 실행될 수 있음 | 기존처럼 경고를 출력하되 수집 결과 저장 성공 여부와 구분한다. |
| 너무 넓은 창 정리 로직 | 사용자 탭을 닫을 수 있음 | 1차 범위에서 창 강제 닫기와 `tab close`를 제외한다. |
| 실제 수집 탭 잔존 문제가 별도로 존재 | 수집용 창이 남을 수 있음 | 이번 작업 후 실제 수집에서 별도 확인되면 2차 작업으로 분리한다. |

## 최종 판단

이번 OpenCLI 이슈의 1차 목표는 SNS Scrap 탭을 닫지 않고, 상단 디버깅 배너와 OpenCLI 점유만 해제하는 것이다.

따라서 지금 구현해야 할 것은 탭 닫기 로직이 아니라, LinkedIn OpenCLI collector 종료부의 `unbind + close + daemon stop` 보강이다.
