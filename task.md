# 🧪 Threads 스크래퍼 v2 실험 계획: "브라우저 제어권 획득의 스윗스팟"

## 1. 실험 목적

- **목표**: 사용자의 수동 개입 없이, 이미 로그인된 브라우저 프로필을 활용하여 Threads '저장됨' 데이터를 100% 무손실 수집하는 최적의 경로(Sweet Spot)를 찾는다.
- **핵심 과제**: Playwright 라이브러리의 프로필 잠금(Lock) 이슈를 우회하고 OS 레벨에서 브라우저를 직접 조종한다.

## 2. 실험 가설 (Hypotheses)

- **가설 1 (전문가 검증)**: `launchPersistentContext` 시 사용 중인 프로필 충돌뿐만 아니라 `--remote-debugging-port` 인자 자체가 Playwright 내부 통신과 충돌을 일으켰을 것이다. (포트 인자 제거 환경에서 재검토 가능)
- **가설 2 (무적의 스윗스팟)**: OS 레벨에서 Chrome을 `spawn`하여 포트를 개방한 뒤 `connectOverCDP`로 접근하는 방식은 기존 브라우저 실행 여부와 상관없이 가장 안정적인 자동화를 보장할 것이다.

## 3. 실험 단계 (Task Checklist)

### Phase 1: 환경 분석 및 경로 확보

- [ ] Windows 내 Google Chrome 실행 파일 경로 확인 (`C:\Program Files\Google\Chrome\Application\chrome.exe`)
- [ ] 사용자 데이터 디렉토리(User Data Dir) 경로 동적 확보

### Phase 2: 원인 분석 (Root Cause Analysis)

- [ ] `launchPersistentContext`로 기존 프로필 열기 시도
- [ ] 실패 시 에러 로그 기록 및 분석 (프로필 잠금 메시지 확인)

### Phase 3: 스윗스팟 구현 (OS Level Spawn)

- [ ] `child_process.spawn`으로 Chrome을 `--remote-debugging-port=9222` 옵션과 함께 실행
- [ ] `localhost:9222`로 Playwright CDP 연결 시도
- [ ] 연결 성공 여부 및 브라우저 창 팝업 확인

### Phase 4: 데이터 수집 및 검증

- [ ] Threads 저장됨 페이지(`https://www.threads.net/saved`) 자동 이동
- [ ] 네트워크 패킷(GraphQL) 인터셉트 로직 실행
- [ ] 30개 이상의 아이템 수집 완료 및 `output2/scraped_items_playwriter_v2.json` 저장
- [ ] 수집 완료 후 브라우저 프로세스 자동 종료

## 4. 예상 결과물

- `task.md`: 본 실험 계획서
- `scrape_with_playwriter_v2.js`: 실험 코드가 담긴 최종 스크립트
- `output2/scraped_items_playwriter_v2.json`: 수집된 결과 데이터

---

**실험 시작 시점**: `task.md` 생성 직후
**실험 담당**: Antigravity (AI Agent)
