"""
crawlers/emart.py — 이마트 (SSG.COM) 와인 할인 크롤러

타깃:
  https://emart.ssg.com/category/catview.ssg?dispCtgId=6000083415

셀렉터 수정이 필요하면:
  headless=False로 실행 → 개발자도구(F12) → 상품 카드 구조 확인
  → CARD_SEL, NAME_SEL, SALE_SEL, ORIG_SEL 상수만 수정
"""
import re
import asyncio
from datetime import datetime
from playwright.async_api import Page
from loguru import logger
from base import BaseCrawler, normalize_price

# ── 수정 포인트: 셀렉터 상수 ─────────────────────────────────
# 이마트가 HTML 구조를 변경하면 여기만 수정
CATEGORY_URL = "https://emart.ssg.com/category/catview.ssg?dispCtgId=6000083415"

CARD_SEL  = ".cunit_prod, .ty_list .item_unit, [class*='product-item']"
NAME_SEL  = ".title, .tit_item, .info_tit, [class*='product-name']"
SALE_SEL  = ".ssg_price, .price_sale, [class*='sale-price'], [class*='ssg_price']"
ORIG_SEL  = ".price_original, .ssg_price_origin, [class*='original-price'], [class*='origin_price']"
BADGE_SEL = ".badge_area, .flag_sale, .ico_event, [class*='badge']"
LINK_SEL  = "a[href]"
IMG_SEL   = "img[src]"
# ────────────────────────────────────────────────────────────


class EmartCrawler(BaseCrawler):
    STORE_ID    = "emart"
    STORE_LABEL = "이마트"

    async def crawl(self, page: Page) -> list[dict]:
        items = []

        logger.info("[이마트] 페이지 로드...")
        await page.goto(CATEGORY_URL, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)

        # 행사 상품 필터 탭 클릭 시도
        try:
            sale_tab = page.locator('a:has-text("행사"), button:has-text("행사")')
            if await sale_tab.count() > 0:
                await sale_tab.first.click()
                await asyncio.sleep(1.5)
                logger.info("[이마트] 행사 탭 클릭")
        except Exception:
            pass

        # 스크롤 — lazy load 트리거
        await self._scroll_down(page, times=4, delay=1.2)

        cards = await page.query_selector_all(CARD_SEL)
        logger.info(f"[이마트] 카드 {len(cards)}개 발견")

        if not cards:
            # 셀렉터 미스 → 디버그 HTML 저장
            await self.debug_save_html(page, "debug_emart.html")
            logger.warning("[이마트] 카드 0개. debug_emart.html 확인 후 CARD_SEL 수정 필요")

        for card in cards:
            try:
                item = await self._parse_card(card)
                if item and self._is_wine(item["name"]) and item.get("discount_rate", 0) > 0:
                    items.append(item)
            except Exception as e:
                logger.debug(f"[이마트] 카드 파싱 스킵: {e}")

        return items

    async def _parse_card(self, card) -> dict | None:
        name_el = await card.query_selector(NAME_SEL)
        if not name_el:
            return None
        name = (await name_el.text_content()).strip()
        if not name:
            return None

        sale_el = await card.query_selector(SALE_SEL)
        orig_el = await card.query_selector(ORIG_SEL)
        sale_raw = (await sale_el.text_content()).strip() if sale_el else ""
        orig_raw = (await orig_el.text_content()).strip() if orig_el else ""

        price_sale = normalize_price(sale_raw)
        price_orig = normalize_price(orig_raw)
        if not price_sale:
            return None

        badge_el  = await card.query_selector(BADGE_SEL)
        badge_txt = (await badge_el.text_content()).strip() if badge_el else ""

        link_el  = await card.query_selector(LINK_SEL)
        img_el   = await card.query_selector(IMG_SEL)
        prod_url = await link_el.get_attribute("href") if link_el else ""
        img_url  = (await img_el.get_attribute("src") or
                    await img_el.get_attribute("data-src") or "") if img_el else ""

        if prod_url and not prod_url.startswith("http"):
            prod_url = "https://emart.ssg.com" + prod_url

        # 행사 종료일 파싱: "~06/30", "6/30까지"
        sale_end = None
        dm = re.search(r"(\d{1,2})[./](\d{1,2})", badge_txt)
        if dm:
            try:
                m, d = int(dm.group(1)), int(dm.group(2))
                y = datetime.now().year
                sale_end = datetime(y, m, d)
            except ValueError:
                pass

        # 카드 조건 파싱
        condition = None
        for kw in ["삼성카드", "신세계카드", "이마트e", "KB국민", "현대카드", "행사카드", "앱전용"]:
            if kw in badge_txt:
                condition = badge_txt
                break

        event_name = None
        if "와인장터" in badge_txt:
            event_name = "이마트 와인장터"
        elif "쓱데이" in badge_txt:
            event_name = "쓱데이"

        return self._build(
            name=name,
            price_sale=price_sale,
            price_original=price_orig,
            event_name=event_name,
            sale_end=sale_end,
            condition=condition,
            product_url=prod_url,
            image_url=img_url,
        )
