"""
crawlers/gs25.py — GS25 와인 행사 크롤러

타깃:
  https://www.gs25.com/gs25/event/promList.gs
  (주류 탭 필터 후 와인 추출)

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
PROMO_URL = "https://www.gs25.com/gs25/event/promList.gs"
# 대안 URL (행사 상품 직접 접근)
ALT_URL   = "https://www.gs25.com/product/index.gs?ctg1Id=10000015"

CARD_SEL  = ".prd_box, .product-item, .item_prd, [class*='prd_list'] li"
NAME_SEL  = ".prd_name, .name, .tit, h3, [class*='product_name']"
PRICE_SEL = ".prd_price, .price, .tx_price, [class*='sale_price']"
ORIG_SEL  = ".original_price, .ori_price, [class*='org_price']"
BADGE_SEL = ".badge, .event_badge, .flag, [class*='event_type'], [class*='badge']"
# ────────────────────────────────────────────────────────────


class GS25Crawler(BaseCrawler):
    STORE_ID    = "gs25"
    STORE_LABEL = "GS25"

    async def crawl(self, page: Page) -> list[dict]:
        items = []
        logger.info("[GS25] 페이지 로드...")

        # 행사 상품 페이지 시도
        try:
            await page.goto(PROMO_URL, wait_until="domcontentloaded", timeout=25_000)
        except Exception:
            await page.goto(ALT_URL, wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(2)

        # 주류 탭 클릭
        try:
            liquor_tab = page.locator('li:has-text("주류"), a:has-text("주류"), button:has-text("주류")')
            if await liquor_tab.count() > 0:
                await liquor_tab.first.click()
                await asyncio.sleep(1.5)
                logger.info("[GS25] 주류 탭 클릭")
        except Exception:
            pass

        await self._scroll_down(page, times=5, delay=0.9)

        cards = await page.query_selector_all(CARD_SEL)
        logger.info(f"[GS25] 카드 {len(cards)}개 발견")

        if not cards:
            await self.debug_save_html(page, "debug_gs25.html")
            logger.warning("[GS25] 0개. debug_gs25.html 확인 후 CARD_SEL 수정 필요")

        for card in cards:
            try:
                item = await self._parse_card(card)
                if item and self._is_wine(item["name"]):
                    items.append(item)
            except Exception as e:
                logger.debug(f"[GS25] 스킵: {e}")

        return items

    async def _parse_card(self, card) -> dict | None:
        name_el = await card.query_selector(NAME_SEL)
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

        # 1+1 / 2+1 처리
        event_name = None
        if "1+1" in badge_txt:
            price_orig = price_sale          # 정상가 = 행사가 (1개 가격)
            price_sale = price_sale // 2     # 실질 1개당 가격
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
            prod_url = "https://www.gs25.com" + prod_url

        # 편의점 행사는 월 단위
        now = datetime.now()
        sale_end = datetime(now.year, now.month,
                            calendar.monthrange(now.year, now.month)[1])

        return self._build(
            name=name,
            price_sale=price_sale,
            price_original=price_orig,
            event_name=event_name,
            sale_end=sale_end,
            condition="GS25 이달의 행사",
            product_url=prod_url,
            image_url=img_url,
        )
