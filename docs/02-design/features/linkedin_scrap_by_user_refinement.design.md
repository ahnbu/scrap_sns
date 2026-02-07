---
template: design
version: 1.2
description: 링크드인 사용자 스크래퍼 기능 개선 (실행 요약, --after 인자, 에러 카운팅)
---

# linkedin_scrap_by_user_refinement 설계서

> **요약**: 수집 범위의 시작점 조절 기능과 상세 실행 통계 출력을 위한 클래스 구조 및 로직 설계
>
> **프로젝트**: scrap_sns
> **작성자**: Gemini CLI
> **날짜**: 2026-02-07
> **상태**: 진행 중

---

## 1. 시스템 컴포넌트 설계

### 1.1 CLI 파서 확장

- `after` 인자 추가: 사용자가 `--after 1m` 또는 `--after 30d` 형식으로 입력 가능하도록 `argparse` 설정을 업데이트합니다.

### 1.2 LinkedinUserScraper 클래스 변수 추가

```python
class LinkedinUserScraper:
    def __init__(self):
        # ...
        self.success_count = 0
        self.fail_count = 0
        self.skip_count = 0      # after_date 필터에 의한 스킵
        self.duplicate_count = 0 # 기존 데이터 중복에 의한 스킵
        
        # 날짜 기준점 계산
        self.after_duration = parse_duration(AFTER_STR)
        self.after_date = CRAWL_START_TIME - self.after_duration if self.after_duration else None
```

---

## 2. 상세 로직 설계

### 2.1 스크래핑 제어 로직 (After Filter)

데이터 추출 함수(`extract_post_...`) 최상단에 다음 로직을 추가합니다:

```python
post_date = get_date_from_snowflake_id(activity_id)

# 수집 시작 시점(After) 체크: 기준 날짜보다 최신이면 스킵
if self.after_date and post_date and post_date > self.after_date:
    self.skip_count += 1
    return
```

### 2.2 에러 카운팅 로직

`try...except` 구문에서 예외 발생 시 `self.fail_count += 1`을 수행합니다.

### 2.3 실행 요약 리포트 (Summary Report)

`run()` 메서드 종료 시점에 소요 시간을 계산하고 통계를 출력합니다.

```python
def print_summary(self, start_time):
    end_time = datetime.now()
    duration = end_time - start_time
    
    print("\n" + "="*50)
    print(f"📊 스크래핑 결과 요약 ({USER_ID})")
    print("-" * 50)
    print(f"⏱️  소요 시간: {str(duration).split('.')[0]}")
    print(f"✅ 성공 건수: {self.success_count}개")
    print(f"❌ 실패 건수: {self.fail_count}개")
    print(f"⏭️  범위 제외: {self.skip_count}개 (최신글 무시)")
    print(f"💾 최종 수집: {len(self.posts)}개")
    print("="*50 + "\n")
```

---

## 3. 테스트 계획

### 3.1 기능 테스트

1.  **After 필터 테스트**: `--after 1d`를 주고 어제~오늘 글이 수집 목록에서 제외되는지 확인합니다.
2.  **리포트 출력 테스트**: 전체 과정 종료 후 콘솔에 요약표가 정상적으로 표시되는지 확인합니다.
3.  **에러 집계 테스트**: 고의로 잘못된 데이터를 주입하거나 파싱 실패 시 `fail_count`가 올라가는지 확인합니다.

---

## 4. 향후 단계

1.  [ ] `linkedin_scrap_by_user.py` 코드 수정 적용
2.  [ ] `gb-jeong` 사용자를 대상으로 `--after` 옵션 포함 테스트 실행
3.  [ ] Gap 분석 및 최종 보고