"""
crawlers/cu.py — CU BGF리테일 와인 행사 크롤러

타깃:
  https://cu.bgfretail.com/product/product.do?category=001005  (주류)

셀렉터 수정:
  CARD_SEL, NAME_SEL, PRICE_SEL, BADGE_SEL 상수만 수정
"""
import calendar
import asyncio
from datetime import datetime
from playwright.async_api import Page
from loguru import logger
from base import BaseCrawler, normalize_price

# ── 수정 포인트 ──────────────────────────────────────────────
PROD_URL  = "https://cu.bgfretail.com/product/product.do?category=001005"
EVENT_URL = "https://cu.bgfretail.com/event/pbEventDetail.do"

CARD_SEL  = ".prod_item, .itemWrap, .pdtinfo, [class*='product_item'], [class*='item_wrap']"
NAME_SEL  = ".prod_name, .pdtName, h3, h4, [class*='prod_nm']"
PRICE_SEL = ".prod_price, .price, .pdtPrice, [class*='sale_price']"
ORIG_SEL  = ".original, .org_price, [class*='ori_price']"
BADGE_SEL = ".badge, .event_type, .ic_event, [class*='badge'], [class*='event']"
# ────────────────────────────────────────────────────────────


class CUCrawler(BaseCrawler):
    STORE_ID    = "cu"
    STORE_LABEL = "CU"

    async def crawl(self, page: Page) -> list[dict]:
        items = []
        logger.info("[CU] 페이지 로드...")

        await page.goto(PROD_URL, wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(2.5)

        # 와인 서브카테고리 필터
        try:
            wine_btn = page.locator('a:has-text("와인"), button:has-text("와인")')
            if await wine_btn.count() > 0:
                await wine_btn.first.click()
                await asyncio.sleep(1.5)
        except Exception:
            pass

        await self._scroll_down(page, times=5, delay=0.9)

        cards = await page.query_selector_all(CARD_SEL)
        logger.info(f"[CU] 카드 {len(cards)}개 발견")

        if not cards:
            await self.debug_save_html(page, "debug_cu.html")
            logger.warning("[CU] 0개. debug_cu.html 확인 후 CARD_SEL 수정 필요")

        for card in cards:
            try:
                item = await self._parse_card(card)
                if item and self._is_wine(item["name"]):
                    items.append(item)
            except Exception as e:
                logger.debug(f"[CU] 스킵: {e}")

        return items

    async def _parse_card(self, card) -> dict | None:
        name_el   = await card.query_selector(NAME_SEL)
        if not name_el:
            return None
        name = (await name_el.text_content()).strip()
        if not name:
            return None

        price_el  = await card.query_selector(PRICE_SEL)
        orig_el   = await card.query_selector(ORIG_SEL)
        badge_el  = await card.query_selector(BADGE_SEL)
        price_raw = (await price_el.text_content()).strip() if price_el else ""
        orig_raw  = (await orig_el.text_content()).strip() if orig_el else ""
        badge_txt = (await badge_el.text_content()).strip() if badge_el else ""

        price_sale = normalize_price(price_raw)
        price_orig = normalize_price(orig_raw)
        if not price_sale:
            return None

        event_name = None
        if "1+1" in badge_txt:
            price_orig = price_sale
            price_sale = price_sale // 2
            event_name = "1+1"
        elif "2+1" in badge_txt:
            price_orig = price_sale
            price_sale = (price_sale * 2) // 3
            event_name = "2+1"
        elif badge_txt:
            event_name = badge_txt[:50]

        link_el  = await card.query_selector("a[href]")
        img_el   = await card.query_selector("img")
        prod_url = await link_el.get_attribute("href") if link_el else ""
        img_url  = (await img_el.get_attribute("src") or
                    await img_el.get_attribute("data-src") or "") if img_el else ""

        if prod_url and not prod_url.startswith("http"):
            prod_url = "https://cu.bgfretail.com" + prod_url

        now = datetime.now()
        sale_end = datetime(now.year, now.month,
                            calendar.monthrange(now.year, now.month)[1])

        return self._build(
            name=name,
            price_sale=price_sale,
            price_original=price_orig,
            event_name=event_name,
            sale_end=sale_end,
            condition="CU 이달의 행사",
            product_url=prod_url,
            image_url=img_url,
        )
