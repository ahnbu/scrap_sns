---
title: "[Analysis] 공통 유틸리티 통합 및 플랫폼 특화 로직 보존 분석 보고서"
created: "2026-03-10 00:00"
---

# [Analysis] 공통 유틸리티 통합 및 플랫폼 특화 로직 보존 분석 보고서

> **작성일**: 2026-03-10
> **작업**: common_utils_integration

## 1. 계획 대비 구현 결과 (Plan vs Implementation)

| 항목 | 계획 (Plan/Design) | 실제 구현 (Actual) | 일치율 |
| :--- | :--- | :--- | :---: |
| **중복 제거** | 6개 이상 파일의 중복 함수 제거 | 6개 주요 파일 통합 완료 | 100% |
| **플랫폼 로직 보존** | `platform` 인자로 분기 처리 | Twitter, Threads, LinkedIn 특화 로직 통합 | 100% |
| **JSON 표준화** | `utf-8-sig`, `ensure_ascii=False` 강제 | `utils/common.py`에 표준 로직 적용 | 100% |
| **단위 테스트** | `tests/unit/test_common.py` 검증 | 4개 케이스 모두 Pass 확인 | 100% |

## 2. 발견된 차이점 및 해결 방안 (Gap & Resolution)
- **Threads 필터링 로직**: 초기 설계 시 본문 시작 후에 나타나는 `답글` 등의 메타데이터가 걸러지지 않는 이슈 발견.
  - **해결**: `is_body_started` 플래그와 상관없이 `meta_patterns`에 매칭되면 무조건 스킵하도록 로직 수정 후 테스트 통과.

## 3. 최종 진단 (Review)
- **코드 품질**: 중복 코드가 제거되어 전체 코드 라인수가 감소하고 유지보수 지점이 단일화됨.
- **안정성**: 플랫폼별 미세한 차이(X의 줄바꿈 제거 등)를 완벽히 수용하여 기존 스크래핑 품질 유지 확인.
- **결론**: **매칭률 100%**. 배포 가능 수준으로 판단됨.

---

## 4. 완료 보고서 (PDCA Report)

### 📊 bkit Feature Usage
✅ Used: /pdca do, analyze, report, phase-8-review
⏭️ Not Used: /pdca iterate (첫 시도에서 테스트 통과 및 수정 완료)
💡 Recommended: /phase-9-deployment (프로덕션 적용 준비 완료)

### 🏁 최종 요약
이번 작업을 통해 프로젝트 내 가장 큰 기술 부채였던 **6중 중복 코드(`reorder_post`, `clean_text` 등)**를 `utils/common.py`로 성공적으로 통합했습니다. 특히 각 플랫폼의 특화 로직을 보존하면서도 공통화를 달성하여, 향후 새로운 SNS 플랫폼 추가 시에도 일관된 텍스트 클리닝 및 데이터 정합성을 보장할 수 있는 기반을 마련했습니다.
