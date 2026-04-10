"""
crawlers/homeplus.py — 홈플러스 와인 크롤러

타깃:
  https://www.homeplus.co.kr/CategoryBrowse?id=10000217

셀렉터 수정:
  CARD_SEL, NAME_SEL, SALE_SEL, ORIG_SEL, BADGE_SEL 상수만 수정
"""
import re
import asyncio
from playwright.async_api import Page
from loguru import logger
from base import BaseCrawler, normalize_price

# ── 수정 포인트 ──────────────────────────────────────────────
WINE_URL = "https://www.homeplus.co.kr/CategoryBrowse?id=10000217"

CARD_SEL  = ".product-item, .ty_col4 li, .goods-list__item, [class*='product_item']"
NAME_SEL  = ".product-name, .goods-name, h3, h4, .tit, [class*='product_name']"
SALE_SEL  = ".sale-price, .selling-price, .price-sale, [class*='sale_price']"
ORIG_SEL  = ".origin-price, .normal-price, .price-original, [class*='origin_price']"
BADGE_SEL = ".badge-sale, .discount-rate, .sale-badge, [class*='discount'], [class*='badge']"
# ────────────────────────────────────────────────────────────


class HomeplusCrawler(BaseCrawler):
    STORE_ID    = "homeplus"
    STORE_LABEL = "홈플러스"

    async def crawl(self, page: Page) -> list[dict]:
        items = []
        logger.info("[홈플러스] 페이지 로드...")

        await page.goto(WINE_URL, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2.5)

        # 행사 필터 클릭
        try:
            f = page.locator('button:has-text("행사"), a:has-text("할인"), button:has-text("특가")')
            if await f.count() > 0:
                await f.first.click()
                await asyncio.sleep(1.5)
        except Exception:
            pass

        await self._scroll_down(page, times=5, delay=1.0)

        cards = await page.query_selector_all(CARD_SEL)
        logger.info(f"[홈플러스] 카드 {len(cards)}개 발견")

        if not cards:
            await self.debug_save_html(page, "debug_homeplus.html")
            logger.warning("[홈플러스] 0개. debug_homeplus.html 확인 후 CARD_SEL 수정 필요")

        for card in cards:
            try:
                item = await self._parse_card(card)
                if item and self._is_wine(item["name"]) and item.get("discount_rate", 0) > 0:
                    items.append(item)
            except Exception as e:
                logger.debug(f"[홈플러스] 스킵: {e}")

        return items

    async def _parse_card(self, card) -> dict | None:
        name_el = await card.query_selector(NAME_SEL)
        if not name_el:
            return None
        name = (await name_el.text_content()).strip()
        if not name:
            return None

        sale_el  = await card.query_selector(SALE_SEL)
        orig_el  = await card.query_selector(ORIG_SEL)
        badge_el = await card.query_selector(BADGE_SEL)
        sale_raw = (await sale_el.text_content()).strip() if sale_el else ""
        orig_raw = (await orig_el.text_content()).strip() if orig_el else ""
        badge_txt= (await badge_el.text_content()).strip() if badge_el else ""

        price_sale = normalize_price(sale_raw)
        price_orig = normalize_price(orig_raw)
        if not price_sale:
            return None

        # 할인율 배지 추출 ("-30%")
        discount_rate = None
        dm = re.search(r"(\d+)%", badge_txt)
        if dm:
            discount_rate = float(dm.group(1))

        # 조건
        condition = None
        for kw in ["앱전용", "카드할인", "삼성카드", "현대카드", "홈플러스카드", "행사카드"]:
            if kw in badge_txt:
                condition = badge_txt[:100]
                break

        link_el  = await card.query_selector("a[href]")
        img_el   = await card.query_selector("img")
        prod_url = await link_el.get_attribute("href") if link_el else ""
        img_url  = (await img_el.get_attribute("src") or
                    await img_el.get_attribute("data-src") or "") if img_el else ""

        if prod_url and not prod_url.startswith("http"):
            prod_url = "https://www.homeplus.co.kr" + prod_url

        return self._build(
            name=name,
            price_sale=price_sale,
            price_original=price_orig,
            discount_rate=discount_rate,
            condition=condition,
            product_url=prod_url,
            image_url=img_url,
        )
