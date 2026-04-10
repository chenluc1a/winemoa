"""
crawlers/kurly.py — 마켓컬리 와인 크롤러

타깃:
  https://www.kurly.com/categories/804  (와인 카테고리)

주의:
  React SPA → wait_until="networkidle" + 넉넉한 sleep 필수
  셀렉터는 data-testid 기반 (비교적 안정적)

셀렉터 수정:
  CARD_SEL, NAME_SEL, SALE_SEL, ORIG_SEL, DISC_SEL 상수만 수정
"""
import re
import asyncio
from playwright.async_api import Page
from loguru import logger
from base import BaseCrawler, normalize_price

# ── 수정 포인트 ──────────────────────────────────────────────
WINE_URL = "https://www.kurly.com/categories/804"

CARD_SEL = '[data-testid="product-card"], .css-y1kxzp, [class*="ProductCard"]'
NAME_SEL = '[data-testid="product-name"], [class*="product-name"], [class*="ProductName"]'
SALE_SEL = '[data-testid="discounted-price"], [class*="discounted"], [class*="sale-price"]'
ORIG_SEL = '[data-testid="original-price"], [class*="original"], [class*="origin-price"]'
DISC_SEL = '[data-testid="discount-rate"], [class*="discount-rate"], [class*="DiscountRate"]'
# ────────────────────────────────────────────────────────────


class KurlyCrawler(BaseCrawler):
    STORE_ID    = "kurly"
    STORE_LABEL = "마켓컬리"

    async def crawl(self, page: Page) -> list[dict]:
        items = []
        logger.info("[마켓컬리] 페이지 로드 (SPA, 느림)...")

        await page.goto(WINE_URL, wait_until="networkidle", timeout=40_000)
        await asyncio.sleep(3)

        # 할인 상품 필터
        try:
            disc_btn = page.locator('[data-testid="discount-filter"], button:has-text("할인")')
            if await disc_btn.count() > 0:
                await disc_btn.first.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        # 더 보기 버튼 반복 클릭 or 스크롤
        for _ in range(8):
            try:
                more = page.locator('button:has-text("더보기"), button:has-text("더 보기")')
                if await more.count() > 0:
                    await more.first.click()
                    await asyncio.sleep(1.2)
                    continue
            except Exception:
                pass
            await page.keyboard.press("End")
            await asyncio.sleep(1.0)

        cards = await page.query_selector_all(CARD_SEL)
        logger.info(f"[마켓컬리] 카드 {len(cards)}개 발견")

        if not cards:
            await self.debug_save_html(page, "debug_kurly.html")
            logger.warning("[마켓컬리] 0개. debug_kurly.html 확인 후 CARD_SEL 수정 필요")

        for card in cards:
            try:
                item = await self._parse_card(card)
                if item and item.get("discount_rate", 0) > 0:
                    items.append(item)
            except Exception as e:
                logger.debug(f"[마켓컬리] 스킵: {e}")

        return items

    async def _parse_card(self, card) -> dict | None:
        name_el = await card.query_selector(NAME_SEL)
        if not name_el:
            return None
        name = (await name_el.text_content()).strip()
        if not name or not self._is_wine(name):
            return None

        sale_el  = await card.query_selector(SALE_SEL)
        orig_el  = await card.query_selector(ORIG_SEL)
        disc_el  = await card.query_selector(DISC_SEL)
        sale_raw = (await sale_el.text_content()).strip() if sale_el else ""
        orig_raw = (await orig_el.text_content()).strip() if orig_el else ""
        disc_raw = (await disc_el.text_content()).strip() if disc_el else ""

        price_sale = normalize_price(sale_raw)
        price_orig = normalize_price(orig_raw)
        if not price_sale:
            return None

        discount_rate = None
        dm = re.search(r"(\d+)", disc_raw)
        if dm:
            discount_rate = float(dm.group(1))

        link_el  = await card.query_selector("a[href]")
        img_el   = await card.query_selector("img")
        href     = await link_el.get_attribute("href") if link_el else ""
        img_url  = (await img_el.get_attribute("src") or
                    await img_el.get_attribute("data-src") or "") if img_el else ""
        prod_url = f"https://www.kurly.com{href}" if href else ""

        return self._build(
            name=name,
            price_sale=price_sale,
            price_original=price_orig,
            discount_rate=discount_rate,
            product_url=prod_url,
            image_url=img_url,
        )
