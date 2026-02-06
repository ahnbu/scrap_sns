---
trigger: always_on
glob: "**/*.{json,py,js,ts}"
description: UTF-8 파일 인코딩 안전 및 데이터 무결성 보호 (JSON 파일 필수)
---

## 핵심 원칙

UTF-8 JSON 파일은 **절대 PowerShell 명령어로 수정하지 않는다.**

---

## 금지 사항 ❌

### 1. Windows PowerShell 사용 금지

```powershell
# ❌ 절대 사용 금지
Get-Content file.json | ... | Set-Content file.json
```

**이유**:

- Windows PowerShell은 기본적으로 CP949(ANSI) 인코딩 사용
- UTF-8 파일을 읽고 쓰는 과정에서 한글이 손상됨
- JSON 구조가 파괴되어 복구 불가능

### 2. 기타 위험한 방법

- ❌ 텍스트 에디터의 '다른 이름으로 저장' (인코딩 설정 실수 위험)
- ❌ 스크립트 없이 수동으로 대량 치환
- ❌ Git에 커밋되지 않은 상태에서 직접 수정

---

## 안전한 파일 수정 방법 ✅

### 우선순위 1: VS Code 내장 기능 (권장)

```
1. Ctrl+H (찾기/바꾸기)
2. Find: 검색할 내용
3. Replace: 바꿀 내용
4. Replace All 클릭
```

- UTF-8 인코딩 100% 보존
- JSON 구조 무손상

### 우선순위 2: Python 스크립트

```python
import json

# 1. UTF-8로 읽기
with open('file.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 2. 데이터 수정
# ... 수정 로직 ...

# 3. UTF-8로 쓰기 (ensure_ascii=False 필수)
with open('file.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4, ensure_ascii=False)
```

### 우선순위 3: PowerShell 7+ (최후 수단)

```powershell
# PowerShell 7.0 이상에서만 사용 가능
Get-Content file.json -Encoding UTF8 |
    ForEach-Object { ... } |
    Set-Content file.json -Encoding UTF8NoBOM
```

---

## 작업 전 체크리스트

데이터 파일(`.json`) 수정 전 반드시 확인:

- [ ] **백업 생성**: 원본 파일을 다른 이름으로 복사했는가?
- [ ] **Git 상태**: 변경 사항이 커밋되어 있거나, `.gitignore`에 포함되어 있는가?
- [ ] **인코딩 명시**: Python 스크립트 사용 시 `encoding='utf-8'`을 명시했는가?
- [ ] **검증 계획**: 수정 후 JSON 유효성 검사를 수행할 것인가?

---

## 작업 후 검증

### Python으로 JSON 유효성 검사

```python
import json

# 파일이 정상적으로 파싱되는지 확인
with open('file.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    print(f"✅ JSON 파싱 성공: {len(data)} 항목")
```

### 인코딩 확인

```python
# 파일이 UTF-8로 저장되었는지 확인
with open('file.json', 'rb') as f:
    first_bytes = f.read(3)
    if first_bytes == b'\xef\xbb\xbf':
        print("⚠️ UTF-8 BOM 감지 (제거 필요)")
    else:
        print("✅ UTF-8 (BOM 없음)")
```

---

## 사고 발생 시 대응

### 증상

- `UnicodeDecodeError` 발생
- JSON 파싱 실패 (`json.decoder.JSONDecodeError`)
- 한글이 깨져 보임

### 조치

1. **즉시 작업 중단**
2. Git에서 복구 (`git checkout -- file.json`)
3. 백업 파일이 있다면 복원
4. **재수집 고려**: 복구 불가능한 경우, 크롤러를 다시 실행하여 데이터 재생성

---

## 요약

> **핵심**: UTF-8 JSON 파일은 **VS Code 내장 기능** 또는 **Python 스크립트**로만 수정한다.  
> **금지**: Windows PowerShell로 절대 수정하지 않는다.
