# LinkedIn 테스트 로케이터 매칭 및 안정화 계획

> Version: 1.0.0 | Created: 2026-03-10 | Status: Draft

## 1. Executive Summary
현재 	ests/smoke/test_linkedin_smoke.py에서 사용 중인 LinkedIn 게시물 목록 로케이터(.reusable-search__entity-result-list)가 최신 레이아웃과 일치하지 않아 테스트가 실패하고 있습니다. 이를 해결하기 위해 최신 레이아웃을 분석하여 유효한 로케이터를 매칭하고 테스트 안정성을 확보합니다.

## 2. Goals and Objectives
- LinkedIn "저장된 게시물" 페이지의 유효한 DOM 로케이터 식별
- Smoke 테스트(	est_linkedin_smoke.py)의 성공적인 통과 (세션 유효성 검증 완료)
- 네트워크 인터셉트 방식과 DOM 가시성 체크의 정합성 확보

## 3. Scope
### In Scope
- 	ests/smoke/test_linkedin_smoke.py의 로케이터 수정
- LinkedIn 저장된 게시물 페이지(.reusable-search__result-container 등) 분석
- 세션 유지 상태 확인 로직 강화

### Out of Scope
- linkedin_scrap.py의 전체 파싱 로직 리팩토링 (필요 시에만 수정)

## 4. Success Criteria
| Criterion | Metric | Target |
|-----------|--------|--------|
| Smoke 테스트 성공 | pytest tests/smoke/test_linkedin_smoke.py 결과 | 100% (PASSED) |
| 로케이터 범용성 | 다양한 계정 환경에서의 동작 확인 | 성공 |

## 5. Timeline
| Milestone | Date | Description |
|-----------|------|-------------|
| 레이아웃 분석 및 로케이터 식별 | 2026-03-10 | 다양한 가능성 있는 선택자 시도 |
| 테스트 코드 수정 및 검증 | 2026-03-10 | 새로운 로케이터 적용 및 테스트 실행 |
| 최종 보고 | 2026-03-10 | 결과 정리 및 보고서 업데이트 |

## 6. Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| LinkedIn의 잦은 레이아웃 변경 | 테스트 지속 실패 | 텍스트 기반 또는 상위 컨테이너 기반의 견고한 선택자 사용 |
| 계정별 AB 테스트 레이아웃 | 일부 환경 실패 | 다중 선택자(.A, .B) 또는 유연한 로케이터 적용 |
