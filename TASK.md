# 와인딜(WineDeal) — 작업지시서

> **목표**: 편의점·마트 와인 할인 행사를 자동 수집→DB→API→프론트까지 혼자 완성할 수 있도록
> 단계별로 체크박스로 관리하세요.

---

## 📁 최종 디렉토리 구조

```
winedeal/
├── TASK.md              ← 이 파일
├── .env                 ← 환경변수 (직접 작성)
├── docker-compose.yml   ← PostgreSQL + Redis
├── requirements.txt
│
├── models.py            ← SQLAlchemy ORM
├── base.py              ← 크롤러 베이스 + 유틸
├── main.py              ← 전체 실행 진입점
├── scheduler.py         ← APScheduler 주기 실행
├── api.py               ← FastAPI 서버
│
└── crawlers/
    ├── __init__.py
    ├── emart.py         ← 이마트 (SSG.COM)
    ├── gs25.py          ← GS25
    ├── cu.py            ← CU
    ├── homeplus.py      ← 홈플러스
    └── kurly.py         ← 마켓컬리
```

---

## ✅ PHASE 1 — 환경 세팅 (30분)

### 1-1. Python 패키지 설치
```bash
pip install -r requirements.txt
playwright install chromium
```

### 1-2. .env 파일 생성
```
DATABASE_URL=postgresql://wine:wine@localhost:5432/winedeals
REDIS_URL=redis://localhost:6379/0
```

### 1-3. DB + Redis 실행
```bash
docker-compose up -d db redis
# 확인
docker ps
```

### 1-4. 테이블 생성
```bash
python -c "from models import Base; from sqlalchemy import create_engine; import os; from dotenv import load_dotenv; load_dotenv(); engine=create_engine(os.getenv('DATABASE_URL')); Base.metadata.create_all(engine); print('OK')"
```

**체크**: `wine_deals` 테이블이 생성되면 완료.

---

## ✅ PHASE 2 — 이마트 크롤러 완성 (1~2시간)

> **가장 먼저 이마트부터 완성하세요. 구조가 가장 안정적입니다.**

### 2-1. 이마트 와인 카테고리 URL 확인
브라우저로 열어서 실제 HTML 구조 확인:
```
https://emart.ssg.com/category/catview.ssg?dispCtgId=6000083415
```

### 2-2. 셀렉터 디버깅 방법
```python
# 브라우저를 headless=False로 열어서 직접 확인
crawler = EmartCrawler(headless=False)
asyncio.run(crawler.run())
```

### 2-3. 셀렉터가 다를 경우 수정
`crawlers/emart.py`에서 아래 줄을 실제 HTML에 맞게 수정:
```python
# 현재 (추정값):
cards = await page.query_selector_all(".cunit_prod, .ty_list .item_unit")
name_el = await card.query_selector(".title, .tit_item")
sale_el = await card.query_selector(".ssg_price, .price_sale")
orig_el = await card.query_selector(".price_original, .ssg_price_origin")
```

**셀렉터 찾는 법**: 브라우저 개발자도구(F12) → 상품 카드 우클릭 → 검사
→ 해당 class명 복사해서 위 코드 수정

### 2-4. 테스트 실행
```bash
python -c "
import asyncio
from crawlers.emart import EmartCrawler
async def test():
    c = EmartCrawler(headless=False)
    items = await c.run()
    for i in items[:5]:
        print(i['name'], i['price_sale'], i['discount_rate'])
asyncio.run(test())
"
```

**기대 결과**: 와인 상품 목록 + 가격 출력

### 2-5. DB 저장 확인
```bash
python -c "
import asyncio
from main import run_crawler
from crawlers.emart import EmartCrawler
asyncio.run(run_crawler(EmartCrawler))
"
```

---

## ✅ PHASE 3 — 편의점 크롤러 (2~4시간)

> **주의**: GS25/CU는 구조가 자주 바뀝니다. headless=False로 먼저 확인.

### 3-1. GS25 행사 페이지 구조 확인
```
https://www.gs25.com/gs25/event/promList.gs
```
→ 주류 탭 클릭 후 HTML 구조 파악

### 3-2. CU 행사 페이지 확인
```
https://cu.bgfretail.com/product/product.do?category=001005
```

### 3-3. 편의점 특이사항: 1+1 / 2+1 처리
```python
# 이미 base.py에 구현되어 있음
# 1+1: 2개 가격 = 정가 1개 → 실질 50% 할인
# 2+1: 3개 가격 = 정가 2개 → 실질 33% 할인
```

### 3-4. 테스트
```bash
python -c "
import asyncio
from crawlers.gs25 import GS25Crawler
async def t():
    c = GS25Crawler(headless=False)
    items = await c.run()
    print(f'수집: {len(items)}개')
    for i in items[:3]: print(i['name'], i['event_name'])
asyncio.run(t())
"
```

---

## ✅ PHASE 4 — 마트/온라인몰 크롤러 (1~2시간)

### 4-1. 홈플러스
```
https://www.homeplus.co.kr/CategoryBrowse?id=10000217
```

### 4-2. 마켓컬리 (React SPA — 주의)
```
https://www.kurly.com/categories/804
```
마켓컬리는 JS 렌더링이 느립니다. `wait_until="networkidle"` + 3초 대기 필수.

---

## ✅ PHASE 5 — API 서버 실행 (30분)

### 5-1. 실행
```bash
uvicorn api:app --reload --port 8000
```

### 5-2. 엔드포인트 테스트
```bash
# 전체 목록
curl "http://localhost:8000/deals?limit=10"

# 이마트만, 레드 와인, 할인율 높은 순
curl "http://localhost:8000/deals?store=emart&wine_type=red&sort=discount_rate"

# 마감 임박
curl "http://localhost:8000/deals/ending-soon?days=3"

# 검색
curl "http://localhost:8000/deals/search?q=몬테스"

# 채널 상태
curl "http://localhost:8000/status"
```

### 5-3. Swagger UI
```
http://localhost:8000/docs
```

---

## ✅ PHASE 6 — 스케줄러 실행 (10분)

```bash
python scheduler.py
```

**스케줄 설정** (scheduler.py에서 수정):
- 편의점(GS25, CU): 매일 09:00, 21:00
- 대형마트: 매일 10:00, 16:00
- 마켓컬리: 매일 11:00, 23:00
- 전체: 6시간마다
- 만료처리: 매일 00:05

---

## ✅ PHASE 7 — 프론트 연결 (선택)

### API 연결 예시 (JavaScript)
```javascript
// 할인 와인 목록
const res = await fetch('http://localhost:8000/deals?sort=discount_rate&limit=50')
const { total, items } = await res.json()

// 마감 임박
const ending = await fetch('http://localhost:8000/deals/ending-soon?days=3')
```

---

## 🔧 트러블슈팅

### 셀렉터가 아무것도 안 잡힐 때
```python
# 페이지 전체 HTML 저장해서 확인
content = await page.content()
with open("debug.html", "w") as f:
    f.write(content)
# 브라우저로 debug.html 열어서 구조 파악
```

### 로그인 필요한 페이지
```python
# GS25 앱 전용 행사 → 로그인 처리 추가 필요
await page.fill('#userId', os.getenv('GS25_ID'))
await page.fill('#password', os.getenv('GS25_PW'))
await page.click('#loginBtn')
await page.wait_for_navigation()
```

### 봇 감지(Cloudflare 등) 우회
```python
# base.py의 _get_page()에 추가:
await page.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined})
""")
```

### 크롤링 주기 조정
```python
# scheduler.py에서 IntervalTrigger 시간 조정
IntervalTrigger(hours=2)   # 2시간마다
IntervalTrigger(minutes=30) # 30분마다 (과도한 요청 주의)
```

---

## 📊 채널별 난이도 & 현실적 기대

| 채널 | 난이도 | 웹 접근 | 행사 주기 | 예상 수집량 |
|------|--------|---------|----------|------------|
| 이마트 (SSG.COM) | ⭐⭐ | 가능 | 주 1회 장터 | 50~200개 |
| 홈플러스 | ⭐⭐⭐ | 가능 | 주 1회 | 30~100개 |
| 마켓컬리 | ⭐⭐⭐ | 가능 | 상시 | 100~300개 |
| GS25 | ⭐⭐⭐⭐ | 제한적 | 주 단위 | 10~30개 |
| CU | ⭐⭐⭐⭐ | 제한적 | 주 단위 | 10~30개 |

---

## 🚀 전체 실행 순서 요약

```bash
# 터미널 1: DB
docker-compose up -d db redis

# 터미널 2: 크롤러 1회 테스트
python main.py

# 터미널 3: API 서버
uvicorn api:app --reload --port 8000

# 터미널 4: 스케줄러
python scheduler.py
```
