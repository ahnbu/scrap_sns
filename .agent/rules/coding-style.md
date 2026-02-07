---
trigger: always_on
glob: "**/*.{js,jsx,ts,tsx,py,go,css,scss,html}"
description: 불변성 유지 및 소형 파일 지향 원칙 (전역 적용)
---

# Coding Style Rules

이 규칙은 코드의 안정성을 확보하고 AI 에이전트의 컨텍스트 분석 효율을 극대화하기 위해 설계되었습니다.

## 1. 불변성 (Immutability) - [CRITICAL]

- 기존 객체이나 배열을 직접 수정(Mutation)하지 마십시오.
- 항상 Spread 연산자(`...`)나 구조 분해 할당을 통해 **새로운 객체를 반환**하십시오.
- **Why?**: 상태 관리 버그를 방지하고, 코드의 예측 가능성을 높이며, 에이전트가 데이터 흐름을 추적하기 쉽게 만듭니다.

```javascript
// WRONG
user.active = true;

// CORRECT
const updatedUser = { ...user, active: true };
```

## 2. 파일 규모 및 모듈화

- **작은 파일 지향 (Many Small Files)**: 하나의 큰 파일보다 역할이 분리된 여러 개의 작은 파일을 권장합니다.
- **라인 수 제한**: 파일당 **200~400줄**을 표준으로 하며, 최대 **800줄**을 넘지 않도록 관리합니다.
- **기능 분리**: 대형 컴포넌트나 복잡한 로직은 즉시 별도의 유틸리티나 하위 모듈로 추출하십시오.
- **Why?**: 에이전트가 한 번에 처리해야 할 컨텍스트 양을 줄여 코드 생성의 정확도를 비약적으로 높입니다.

## 3. 명명 및 가독성

- 변수와 함수 이름은 그 역할을 명확히 설명할 수 있도록 상세하게 짓습니다.
- 코드 내 `console.log` 등 디버깅용 코드는 최종 제출 전 반드시 삭제합니다.

## 4. 문서화 및 주석 (Documentation & Comments)

코드의 의도를 명확히 하여 유지보수성을 높이고 AI 에이전트와의 협업 효율을 극대화합니다.

- **Why, not What**: 코드가 '무엇을 하는지'보다 '왜 이 코드가 존재하는지'에 집중하여 주석을 작성하십시오. 단순한 동작 설명은 코드 자체로 드러나야 합니다.
- **복잡한 로직 설명**: 트릭이 사용되었거나 복잡한 알고리즘이 포함된 로직에는 반드시 상세한 설명을 추가하십시오.
- **TODO 관리**: 향후 개선이 필요하거나 미완성인 부분은 `TODO:` 키워드를 사용하여 명시하십시오.
- **JSDoc 기반 문서화**: 함수 정의 시 JSDoc 형식을 사용하여 매개변수와 반환값의 역할을 설명하십시오.

```typescript
/**
 * 사용자의 총 포인트를 계산합니다.
 * @param userId - 사용자의 고유 ID
 * @returns 획득한 총 포인트 점수
 */
function calculateUserPoints(userId: string): number {
  // implementation
}
```

## 5. 이식성 및 동적 경로 처리 (Portability & Dynamic Paths) - [CRITICAL]

코드의 환경 독립성과 유지보수성을 위해 다음 규칙을 반드시 준수하십시오.

- **절대 경로 사용 금지**: `C:\Users\...` 또는 `d:\vibe-coding\...`와 같은 절대 경로를 코드나 설정에 하드코딩하지 마십시오. 반드시 실행 파일 위치 기준의 상대 경로(`os.path` 등)를 사용하십시오.
- **상황에 맞는 날짜 및 경로 처리**: 파일명에 날짜가 포함된 경우(예: `data_20240101.json`), 다음과 같이 목적에 따라 구분하여 구현하십시오.
  - **자동화/최신 데이터**: **최신 데이터 수집 및 병합**이 핵심인 워크플로우에서는 `glob` 모듈을 사용하여 **가장 최신 파일**을 자동으로 찾도록 하십시오.
  - **명시적 분석/과거 데이터**: 특정 버전이나 과거 데이터를 타겟팅해야 하는 경우엔 날짜를 명시적으로 지정할 수 있습니다.
- **환경 독립적 지침**: `README.md`나 주석 등 문서에서도 특정 사용자의 개인 디렉토리 경로를 노출하지 말고, 프로젝트 루트 기준의 범용적인 경로를 기술하십시오.

```python
# WRONG
path = r'd:\vibe-coding\scrap_sns\data\file_20260201.json'

# CORRECT
base_dir = os.path.dirname(os.path.abspath(__file__))
latest_file = max(glob.glob(os.path.join(base_dir, 'data', 'file_*.json')))
```
