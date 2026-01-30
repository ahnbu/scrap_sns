# Playwright CDP 연결 방식 실험 보고서

**실험 기간**: 2026-01-30  
**실험 목표**: 사용자의 Chrome 브라우저를 재시작하지 않고 Threads 데이터를 수집하는 "스윗스팟" 찾기

---

## 📋 실험 배경

### 기존 성공 사례 (v1)

- **방식**: Playwriter 확장 프로그램 + CDP 릴레이 서버
- **장점**: 안정적으로 작동, 30개 데이터 수집 성공
- **단점**: 사용자가 매번 브라우저를 켜고 확장 프로그램 아이콘을 클릭해야 함 (반자동)

### 문제 제기

기존 Python 스크립트(v2.py)가 실패한 원인이 "프로필 잠금(Lock) 이슈" 때문인지 검증하고, 이를 우회하여 완전 자동화를 달성할 수 있는지 실험.

---

## 🧪 실험 가설

### 가설 1: Playwright 라이브러리 제약

`launchPersistentContext`를 사용하면:

- 현재 사용 중인 Chrome 프로필과 충돌
- `--remote-debugging-port` 인자가 내부 통신 파이프와 충돌
- **검증 결과**: ✅ **사실**. 라이브러리 직접 기동은 계속 타임아웃 발생

### 가설 2: OS 레벨 Spawn 우회

OS 명령어로 Chrome을 직접 실행하면 라이브러리 제약을 우회할 수 있다.

- **검증 결과**: ⚠️ **부분 성공**. Chrome은 실행되지만 CDP 연결이 불안정함

### 가설 3: 세션 유지

디버깅 모드로 실행한 Chrome에서 기존 로그인 세션을 유지할 수 있다.

- **검증 결과**: ❌ **실패**. 별도 프로필로 실행되어 재로그인 필요

---

## 🔬 시도한 방법들

### 방법 1: launchPersistentContext (표준 방식)

```javascript
browserContext = await chromium.launchPersistentContext(USER_DATA_DIR, {
  executablePath: CHROME_PATH,
  headless: false,
  timeout: 15000,
});
```

**결과**:

- ❌ 15초 타임아웃 지속 발생
- ❌ "about:blank" 상태에서 멈춤
- 원인: 프로필 잠금 + 포트 충돌

---

### 방법 2: OS Spawn + CDP 연결

```javascript
spawn(
  CHROME_PATH,
  [
    "--remote-debugging-port=9222",
    "--user-data-dir=...",
    "--profile-directory=Default",
  ],
  { shell: true },
);

browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
```

**결과**:

- ✅ Chrome 실행 성공
- ✅ CDP 연결 성공 (일부 시도)
- ✅ 페이지 이동 성공
- ❌ **데이터 수집 0개** (네트워크 패킷 캡처 실패)

---

### 방법 3: PowerShell 직접 실행

```powershell
Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222", ...
```

**결과**:

- ✅ Chrome 실행 성공
- ✅ CDP 연결 성공
- ⚠️ 로그인 화면 표시 (세션 유지 실패)
- ❌ 데이터 수집 0개

---

## 🚧 발견된 핵심 문제점

### 1. 프로필 경로 문제

```
--user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data"
--profile-directory=Default
```

위 설정을 사용해도 **별도의 깨끗한 프로필**이 생성되어 로그인 정보가 유지되지 않음.

### 2. CDP 포트 개방 불안정

- 10초 대기 후에도 9222 포트가 열리지 않는 경우 발생
- `shell: true` vs `shell: false` 차이도 불명확
- 환경 변수 전달 문제 가능성

### 3. 네트워크 패킷 캡처 실패

```javascript
page.on("response", async (response) => {
  // 이 이벤트가 전혀 발생하지 않음
});
```

- 페이지 이동은 성공하지만 GraphQL 응답을 캡처하지 못함
- `waitUntil: 'networkidle'` 사용해도 동일

### 4. 타이밍 이슈

- Chrome 실행 → CDP 연결 사이 대기 시간이 매우 민감함
- 너무 짧으면 연결 실패, 너무 길면 비효율

---

## 📊 방법별 비교표

| 방법                        | Chrome 실행 | CDP 연결 | 페이지 이동 | 데이터 수집 | 재시작 필요 | 안정성     |
| --------------------------- | ----------- | -------- | ----------- | ----------- | ----------- | ---------- |
| **v1 (Playwriter)**         | ✅          | ✅       | ✅          | ✅ (30개)   | ❌          | ⭐⭐⭐⭐⭐ |
| **launchPersistentContext** | ❌          | ❌       | ❌          | ❌          | ✅          | ⭐         |
| **Spawn + CDP**             | ✅          | ⚠️       | ✅          | ❌          | ✅          | ⭐⭐       |
| **PowerShell + CDP**        | ✅          | ✅       | ✅          | ❌          | ✅          | ⭐⭐       |

---

## 💡 최종 결론

### ❌ 실험 실패 선언

**"재시작 없이 안정적으로 작동하는 스윗스팟"은 찾지 못했습니다.**

### 원인 분석

1. **Chrome 프로필 시스템의 복잡성**
   - 동일한 프로필을 두 프로세스가 동시에 사용할 수 없음
   - 디버깅 모드 실행 시 별도 프로필이 생성됨
2. **Playwright CDP 연결의 불안정성**
   - 포트 개방 타이밍이 예측 불가능
   - 네트워크 이벤트 리스너가 작동하지 않는 원인 불명확

3. **과도한 엣지 케이스**
   - OS 환경 차이, Chrome 버전, Playwright 버전 등 변수가 너무 많음
   - 로컬 개발 환경에서만 동작하는 불안정한 솔루션

---

## 🎯 권장 사항

### Option 1: v1 유지 (강력 추천 ⭐⭐⭐⭐⭐)

**현재 작동하는 v1(Playwriter 방식)을 그대로 사용**

- 안정성: 검증됨
- 단점: 사용자가 확장 프로그램 클릭 필요
- 결론: "반자동"이지만 **100% 신뢰할 수 있음**

### Option 2: 재시작 허용 (차선책 ⭐⭐⭐)

```bash
# 1. 모든 Chrome 종료
taskkill /F /IM chrome.exe

# 2. 디버깅 모드로 재시작
chrome.exe --remote-debugging-port=9222

# 3. 스크립트 실행
```

- 장점: 기술적으로 가능
- 단점: 매번 브라우저 재시작 필요, 탭 복원 등 UX 저하

### Option 3: 별도 프로필 사용

```javascript
--user-data-dir="./chrome-debug-profile"
```

- 장점: 충돌 없음
- 단점: Threads 로그인을 별도로 유지해야 함

---

## 📝 교훈

### 1. "완벽한 자동화"의 환상

브라우저 자동화는 언제나 트레이드오프가 존재합니다:

- 안정성 vs 편의성
- 보안 vs 자동화
- 표준 방식 vs 해킹

### 2. 검증된 솔루션의 가치

**v1(Playwriter)이 이미 잘 작동하고 있었다는 것이 가장 중요한 사실입니다.**
불필요한 "최적화"를 시도하다가 더 많은 시간을 소비했습니다.

### 3. 브라우저 자동화의 본질

Chrome DevTools Protocol은 강력하지만:

- 공식 문서가 부족함
- 버전 간 호환성 문제
- 환경별 동작 차이가 큼

→ **프로덕션 환경에서는 "검증된 단순한 방법"이 최선**

---

## 🔚 최종 의사결정

**실험을 종료하고 v1(Playwriter 방식)을 계속 사용하기로 결정합니다.**

이유:

1. ✅ 이미 작동 검증됨
2. ✅ 코드가 단순하고 이해하기 쉬움
3. ✅ 30개 데이터 수집 성공 사례 존재
4. ❌ v2 실험은 너무 많은 시간 투입 대비 성과 없음

---

**작성일**: 2026-01-30  
**실험자**: Antigravity AI Agent  
**결론**: v1 유지, v2 실험 중단
