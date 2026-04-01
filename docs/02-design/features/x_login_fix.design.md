---
title: "Design: X(Twitter) 탐지 회피형 별도 창 브라우저 설계"
created: "2026-02-12 12:33"
---

# Design: X(Twitter) 탐지 회피형 별도 창 브라우저 설계

X의 자동화 차단을 우회하고 사용자가 제어하기 쉬운 독립된 브라우저 창을 구현하기 위한 상세 설계입니다.

## 1. 브라우저 구동 설계 (Window Management)
- **방식**: `launch_persistent_context` 사용
- **특징**: 기존 크롬과 별개의 프로세스로 실행되어 **완전히 새로운 창**으로 팝업됨.
- **프로필 경로**: `auth/x_user_data` (이 폴더에 로그인 정보가 영구 저장됨)
- **위치 및 크기**: 
    - `args=[f"--window-position=0,0", "--window-size=1200,800"]`
    - 창 위치를 (0,0)으로 고정하여 실행 즉시 확인할 수 있도록 설정.

## 2. 탐지 회피 상세 설정 (Anti-Detection)
- **채널 설정**: `channel="chrome"` (설치된 구글 크롬 강제 사용)
- **자동화 플래그 제거**: `args=["--disable-blink-features=AutomationControlled"]`
- **User-Agent 위장**: 최신 Windows Chrome의 User-Agent를 고정값으로 주입하여 봇으로 의심받는 패턴 제거.

## 3. 로그인 및 세션 워크플로우
1. 실행 시 `auth/x_user_data` 폴더 확인.
2. 북마크 페이지 진입 후 로그인 여부 판단.
3. 로그인이 안 된 경우 창을 띄운 상태로 **사용자가 직접 입력할 때까지 무한 대기**.
4. 로그인 성공 후 북마크 리스트가 나타나면 수집 로직으로 자동 전환.
5. 이후 실행 시에는 이미 폴더에 저장된 세션을 사용하여 로그인 과정 없이 즉시 수집 시작.

## 4. 코드 반영 계획
- `twitter_scrap.py`의 `main()` 함수 내 `sync_playwright` 블록을 위 설계대로 전면 교체.
- 기존 `storage_state` 방식은 `persistent_context` 폴더 관리 방식으로 대체되어 더 견고해짐.
