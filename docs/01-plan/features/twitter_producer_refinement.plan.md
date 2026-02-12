# Plan: X(Twitter) 목록 수집기 정교화 및 상세 로그 시스템 도입

이 문서는 X(Twitter) 스크래핑의 첫 단추인 목록 수집기(`twitter_scrap.py`)에서 발생하는 사용자 정보 누락 문제를 해결하고, Threads 수준의 상세 작업 로그를 구현하기 위한 계획을 담고 있습니다.

## 1. 현상 및 원인 분석
- **사용자 정보 누락**: JSON 패킷 파싱 시 특정 트윗 형태(광고, 인용, 긴 타래 등)에서 사용자 정보 경로가 달라 `user` 필드가 `None`으로 기록됨.
- **가시성 부족**: 크롤링 진행 중 어떤 데이터를 가져오고 있는지, 오류가 발생하는지 알 수 있는 실시간 로그가 전무함.

## 2. 해결 전략
### 2.1 견고한 사용자 정보 추출 (Anti-None)
- X API의 다양한 응답 구조를 지원하는 다중 경로 탐색 로직 구현.
- `tweet_results -> result -> core -> user_results -> result -> legacy` (표준)
- `tweet_results -> result -> tweet -> core -> user_results -> result -> legacy` (중첩형)
- `tweet_results -> result -> author -> legacy` (대체형)

### 2.2 Threads 방식의 상세 로그 도입
- 수집 단계별(Net/DOM) 시각적 피드백 제공.
- 형식: `[소스] @아이디 | 본문 요약 (누적 개수)`
- 브라우저 상태(접속, 로그인, 스크롤)에 대한 명확한 메시지 출력.

### 2.3 데이터 구조 일관성 보장
- `url` 생성 시 반드시 `user` 아이디가 포함된 정식 형식 보장.
- 모든 신규 수집 항목에 `is_detail_collected: false` 강제 부여.

## 3. 진행 단계 (PDCA)
1. **[Plan]**: (현재) 추출 경로 보강 및 로그 강화 계획 수립.
2. **[Design]**: 상세 로그 인터페이스 및 JSON 경로 매핑 설계.
3. **[Do]**: `twitter_scrap.py` 코드 수정.
4. **[Check]**: 실시간 로그 출력 및 생성된 JSON 데이터의 무결성 검증.
5. **[Act]**: 깨끗해진 목록 데이터를 바탕으로 상세 수집기(`twitter_scrap_single.py`) 실행.
