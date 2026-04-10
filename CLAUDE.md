# CLAUDE.md — Project AI Instructions

> Claude가 이 프로젝트에서 코드 작업, 커밋 메시지 생성, PR 작성 시 참고하는 지침 문서입니다.

---

## 🧵 Git Commit Convention

### 형식

```
<이모지> <타입>(<스코프>): <한국어 요약>

<본문>

<푸터>
```

### 타입 & 이모지 매핑

| 이모지 | 타입       | 설명                            |
|--------|------------|---------------------------------|
| ✨     | feat       | 새로운 기능 추가                |
| 🐛     | fix        | 버그 수정                       |
| 💡     | chore      | 주석, 포맷 등 자잘한 수정       |
| 📝     | docs       | 문서 수정                       |
| 🚚     | build      | 빌드/패키지 관련 수정           |
| ✅     | test       | 테스트 코드 추가/수정           |
| ♻️     | refactor   | 기능 변화 없는 리팩터링         |
| 🚑     | hotfix     | 긴급 수정                       |
| ⚙️     | ci         | CI/CD 변경                      |
| 🔧     | config     | 설정 파일 수정                  |
| 🗑️     | remove     | 불필요 파일/코드 삭제           |
| 🔒     | security   | 보안 관련 수정                  |
| 🚀     | deploy     | 배포 관련 커밋                  |
| 🧩     | style      | 코드 스타일 변경                |
| 🎨     | ui         | UI/템플릿/CSS 변경              |
| 🔄     | sync       | 코드/데이터 동기화              |
| 🔥     | clean      | 코드/로그 정리                  |
| 🧠     | perf       | 성능 개선                       |

### 규칙

- 제목은 **한국어**, 50자 이내, 마침표 없음
- 본문 각 줄 72자 이내, 변경 이유 서술
- 하나의 커밋 = 하나의 타입
- 이모지 **필수** (생략 금지)
- Breaking Change → 푸터에 `BREAKING CHANGE:` 명시
- 이슈 연결 → `Fixes #N` 또는 `Refs #N`

### 예시

```
✨ feat(products): 상품 상세페이지 추가

- Bootstrap 기반 product_detail.html 추가
- views.py에서 Product 더미데이터 연결

Fixes #12
```

---

## 📌 Claude에게 요청할 때

커밋 메시지 작성을 요청할 경우, Claude는 위 컨벤션에 따라 메시지를 생성합니다.

프롬프트 예시:
> "변경된 내용을 보고 CLAUDE.md 커밋 컨벤션에 맞게 커밋 메시지 작성해줘."
