# Plan: X(Twitter) 타래 수집 시스템 고도화 및 데이터 소스 정규화

이 문서는 X(Twitter) 스크래핑을 Threads와 동일한 '목록 수집(Simple)' 및 '상세 수집(Full)' 구조로 개편하고, 데이터 수집 경로를 명확히 구분하기 위한 계획을 담고 있습니다.

## 1. 개편 목표
- **수집 방식 세분화**: `source` 필드를 통해 데이터가 어떤 단계(`initial_dom`, `network`, `scroll_dom`)에서 수집되었는지 명시.
- **타래 수집 자동화**: 개별 트윗 페이지를 방문하여 작성자의 연속된 답글을 하나의 게시물로 병합하는 전용 스크래퍼 도입.
- **Threads 구조 벤치마킹**: Producer(목록 확보) - Consumer(상세 수집) 파이프라인 구축.

## 2. 주요 작업 내용
### 2.1 twitter_scrap.py (Producer) 고도화
- 저장 파일명을 `twitter_py_simple_full_*.json`으로 변경.
- `source` 필드 값 정규화:
    - 초기 화면 스캔: `initial_dom`
    - 네트워크 패킷: `network`
    - 스크롤 중 스캔: `scroll_dom`

### 2.2 twitter_scrap_single.py (Consumer) 신규 개발
- 기능: `simple` 파일에서 미수집 URL을 읽어 개별 접속.
- 타래 추출: 동일 작성자의 하위 답글들을 수집하여 `full_text`로 병합.
- 결과 저장: `twitter_py_full_*.json`으로 최종 데이터 생성.

### 2.3 total_scrap.py 파이프라인 통합
- 전체 실행 프로세스에 `twitter_scrap_single.py` 단계 추가.

## 3. 진행 단계 (PDCA)
1. **[Plan]**: (현재) 수집 구조 정의 및 필드 정규화 계획 수립.
2. **[Design]**: `twitter_scrap_single.py`의 타래 추적 로직 상세 설계.
3. **[Do]**: 스크래퍼 수정 및 신규 스크립트 구현.
4. **[Check]**: 수집 결과물의 데이터 정합성(타래 병합 여부) 및 소스 필드 확인.
5. **[Act]**: 최종 통합 DB 반영 및 마이그레이션.
