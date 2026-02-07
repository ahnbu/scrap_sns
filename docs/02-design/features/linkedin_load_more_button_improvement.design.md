---
template: design
version: 1.2
description: 링크드인 사용자 스크래퍼 "결과 더 보기" 버튼 클릭 로직 설계
---

# linkedin_load_more_button_improvement 설계서

> **요약**: 무한 스크롤 중 나타나는 "결과 더 보기" 버튼을 Playwright Selector로 탐지하고 클릭하는 로직을 설계합니다.
>
> **프로젝트**: scrap_sns
> **버전**: 1.2.0
> **작성자**: Gemini CLI
> **날짜**: 2026-02-07
> **상태**: Draft
> **Planning Doc**: [linkedin_load_more_button_improvement.plan.md](../01-plan/features/linkedin_load_more_button_improvement.plan.md)

---

## 1. 개요

### 1.1 설계 목표

- 링크드인 활동 페이지의 유한 스크롤(Finite Scroll) 대응.
- 버튼 탐지 실패 시에도 스크래퍼가 중단되지 않고 폴백(Fallback) 작동 보장.
- 버튼 클릭 후 네트워크 응답을 기다리는 적절한 지연 시간(Wait time) 설정.

### 1.2 설계 원칙

- **견고성(Robustness)**: ID 기반이 아닌 클래스 및 텍스트 조합 Selector를 사용하여 UI 변경에 대응.
- **비차단성(Non-blocking)**: 버튼 클릭 시도가 에러를 발생시켜도 전체 루프는 유지.
- **단순성(Simplicity)**: 기존 `run` 메서드의 루프 내에 최소한의 변경으로 통합.

---

## 2. 아키텍처

### 2.1 컴포넌트 구조

- `LinkedinUserScraper.run()`: 메인 제어 루프.
- `Playwright Page Object`: 브라우저 자동화 도구.
- `Selector`: 버튼 탐지를 위한 전략 객체.

### 2.2 데이터 흐름

1. 루프 시작 (while not stopped_early)
2. **버튼 탐지**: `page.locator('button.scaffold-finite-scroll__load-button')`
3. **버튼 가시성 확인**: `is_visible()`
4. **액션 결정**:
   - 버튼 존재 시: `click()` -> `time.sleep(3)`
   - 버튼 부재 시: `window.scrollTo` -> `time.sleep(3)`
5. 데이터 수집 및 종료 조건 확인 (기존 로직)

---

## 3. 구현 상세

### 3.1 Selector 정의

타겟 버튼:
```html
<button id="ember775" class="artdeco-button artdeco-button--muted artdeco-button--1 artdeco-button--full artdeco-button--secondary ember-view scaffold-finite-scroll__load-button" type="button">
  <span class="artdeco-button__text"> 결과 더보기 </span>
</button>
```

최적화된 Selector:
- `button.scaffold-finite-scroll__load-button` (가장 고유한 클래스)
- `button:has-text("결과 더보기")` (다국어 대응 필요 시)
- `button:has-text("Show more results")` (영어 환경 대응)

### 3.2 의사 코드 (Pseudo Code)

```python
# run 메서드 내부
while not self.stopped_early:
    try:
        # 1. 특정 클래스 버튼 찾기
        load_more_btn = page.locator('button.scaffold-finite-scroll__load-button')
        
        # 2. 버튼이 보이고 클릭 가능한지 확인
        if load_more_btn.is_visible() and load_more_btn.is_enabled():
            print("   🖱️ '결과 더보기' 버튼 클릭")
            load_more_btn.click()
            time.sleep(3)
        else:
            # 3. 버튼이 없으면 기존 스크롤
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)
    except Exception as e:
        # 예외 발생 시 안전하게 스크롤로 폴백
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(3)
```

---

## 4. 테스트 플랜

### 4.1 테스트 케이스

- [ ] **버튼 클릭 성공**: 버튼이 나타났을 때 정확히 클릭하고 새로운 포스트가 네트워크로 들어오는지 확인.
- [ ] **버튼 부재 시 스크롤**: 버튼이 없는 페이지 상단/중단에서는 기존처럼 스크롤이 작동하는지 확인.
- [ ] **다국어 대응**: 브라우저 언어 설정에 관계없이 클래스 기반 Selector가 작동하는지 확인.
- [ ] **종료 조건**: 버튼을 계속 눌러도 더 이상 데이터가 없을 때 `no_new_data_count`가 올라가서 정상 종료되는지 확인.

---

## 5. 코딩 컨벤션 준수

- 기존 `linkedin_scrap_by_user.py`의 스타일 유지 (4-space indentation, print logging).
- 복잡한 에러 핸들링보다는 `try-except`를 통한 흐름 유지에 집중.

---

## 6. 향후 단계

1. [ ] `linkedin_scrap_by_user.py` 파일 수정 (구현)
2. [ ] `gb-jeong` 사용자로 실제 버튼 클릭 발생 여부 테스트
3. [ ] 갭 분석 수행

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-02-07 | 최초 설계 초안 작성 | Gemini CLI |
