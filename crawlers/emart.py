"""
crawlers/emart.py — 이마트 (SSG.COM) 와인 크롤러

타깃:
  https://emart.ssg.com/search.ssg?target=all&query=와인&sort=popularScore_desc

구조 (2025년 기준 Chakra UI 기반 React SPA):
  - 카드: .cta-item-unit-cart-btn 부모 3단계 위
  - 상품명: 카드 내 두 번째 a.chakra-link 하위 div 텍스트
  - 가격: 카드 내 em 태그 (판매가격 sr-only 텍스트 포함)
  - 원가: del 태그 또는 em 이전 span

셀렉터 수정 포인트:
  SEARCH_URL, CARD_BTN_SEL, PRICE_EM_SEL 상수
"""
import re
import asyncio
from playwright.async_api import Page
from loguru import logger
from base import BaseCrawler, normalize_price

# ── 수정 포인트 ─────────────────────────────────────────────────
SEARCH_URL   = "https://emart.ssg.com/search.ssg?target=all&query=와인&sort=popularScore_desc"
CARD_BTN_SEL = ".cta-item-unit-cart-btn"   # 카드당 1개, 안정적
NAME_LINK_SEL = "a.chakra-link"            # 카드 내 링크 (두 번째가 상품 정보)
PRICE_EM_SEL  = "em"                       # 판매가격
ORIG_DEL_SEL  = "del"                      # 원가 (할인 시 존재)
DISC_SEL      = "span"                     # 할인율 % 포함
# ────────────────────────────────────────────────────────────────


class EmartCrawler(BaseCrawler):
    STORE_ID    = "emart"
    STORE_LABEL = "이마트"

    async def crawl(self, page: Page) -> list[dict]:
        items = []
        logger.info("[이마트] 검색 페이지 로드...")

        await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=35_000)
        await asyncio.sleep(3)

        # 스크롤로 lazy-load 트리거
        await self._scroll_down(page, times=5, delay=1.2)

        # 더보기 버튼 클릭 (있을 경우)
        for _ in range(3):
            try:
                more = page.locator('button:has-text("더보기"), button:has-text("더 보기")')
                if await more.count() > 0:
                    await more.first.click()
                    await asyncio.sleep(1.5)
            except Exception:
                break

        btns = await page.query_selector_all(CARD_BTN_SEL)
        logger.info(f"[이마트] 카드 {len(btns)}개 발견")

        if not btns:
            await self.debug_save_html(page, "debug_emart.html")
            logger.warning("[이마트] 카드 0개. debug_emart.html 확인 필요")
            return []

        for btn in btns:
            try:
                item = await self._parse_card(btn)
                if item and self._is_wine(item["name"]):
                    items.append(item)
            except Exception as e:
                logger.debug(f"[이마트] 카드 파싱 스킵: {e}")

        logger.info(f"[이마트] 와인 필터 후 {len(items)}개")
        return items

    async def _parse_card(self, btn) -> dict | None:
        # 카드 루트: 버튼 → 부모 → 부모 → 부모
        card = await btn.evaluate_handle(
            "el => el.parentElement.parentElement.parentElement"
        )
        card = card.as_element()
        if not card:
            return None

        # 상품명: a.chakra-link 2번째 링크 하위 div 텍스트
        links = await card.query_selector_all(NAME_LINK_SEL)
        name = ""
        prod_url = ""
        for link in links:
            href = await link.get_attribute("href") or ""
            if "itemView" in href:
                prod_url = href if href.startswith("http") else "https://emart.ssg.com" + href
                # 링크 내 div 중 상품명 텍스트 찾기
                divs = await link.query_selector_all("div")
                for div in divs:
                    text = (await div.text_content() or "").strip()
                    # 불필요 텍스트 제외: 짧은 것, 픽업 관련, 별점 관련
                    if (text and len(text) > 3
                            and "픽업" not in text
                            and "별점" not in text
                            and "리뷰" not in text
                            and "원" not in text):
                        name = text
                        break
                if name:
                    break

        if not name:
            return None

        # 가격 — em 태그 (판매가격 텍스트 포함, 제거 후 파싱)
        em_el = await card.query_selector(PRICE_EM_SEL)
        if not em_el:
            return None
        price_raw = (await em_el.text_content() or "").replace("판매가격", "").strip()
        price_sale = normalize_price(price_raw)
        if not price_sale:
            return None

        # 원가 — del 태그 (할인 상품에만 존재)
        del_el = await card.query_selector(ORIG_DEL_SEL)
        price_orig = None
        if del_el:
            orig_raw = (await del_el.text_content() or "").strip()
            price_orig = normalize_price(orig_raw)

        # 할인율 — % 포함 span
        discount_rate = None
        spans = await card.query_selector_all(DISC_SEL)
        for span in spans:
            t = (await span.text_content() or "").strip()
            m = re.search(r"(\d+)%", t)
            if m and len(t) < 10:
                discount_rate = float(m.group(1))
                break

        # 이미지
        img_el = await card.query_selector("img")
        img_url = ""
        if img_el:
            img_url = (await img_el.get_attribute("src")
                       or await img_el.get_attribute("data-src") or "")

        return self._build(
            name=name,
            price_sale=price_sale,
            price_original=price_orig,
            discount_rate=discount_rate,
            product_url=prod_url,
            image_url=img_url,
        )
