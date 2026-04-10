"""base.py — 크롤러 공통 베이스 클래스 + 파싱 유틸"""
import re
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from loguru import logger
from playwright.async_api import async_playwright, Browser, Page


# ── 와인 타입 키워드 분류 ──────────────────────────────────────
_TYPE_KEYWORDS = {
    "sparkling": [
        "샴페인", "스파클링", "프로세코", "카바", "크레망", "브뤼", "brut",
        "champagne", "prosecco", "cava", "cremant", "NV", "모스카토 스푸만테",
    ],
    "rose": ["로제", "rosé", "rose"],
    "white": [
        "화이트", "white", "샤르도네", "소비뇽 블랑", "소비뇽블랑", "리슬링",
        "피노 그리", "피노그리", "게뷔르츠", "비오니에", "알바리뇨",
        "chardonnay", "sauvignon", "riesling", "pinot gris", "viognier",
    ],
    "red": [
        "레드", "red", "까베르네", "카베르네", "메를로", "쉬라즈", "피노 누아",
        "피노누아", "말벡", "산지오베제", "네비올로", "바롤로", "바르바레스코",
        "템프라니요", "그르나슈", "cabernet", "merlot", "shiraz", "syrah",
        "malbec", "pinot noir", "nebbiolo", "tempranillo", "grenache",
    ],
}


def classify_wine_type(name: str) -> str:
    n = name.lower()
    for wtype, kws in _TYPE_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in n:
                return wtype
    return "unknown"


def normalize_price(text: str) -> Optional[int]:
    """'38,900원' / '₩14,900' / '9900' → 38900"""
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None


def normalize_name(name: str) -> str:
    """채널 간 동일 상품 비교용 정규화"""
    n = name.lower().strip()
    n = re.sub(r"\s+", " ", n)
    n = re.sub(r"[^\w\s가-힣]", "", n)
    return n


def extract_discount_rate(original: Optional[int], sale: Optional[int]) -> Optional[float]:
    if original and sale and original > 0 and original > sale:
        return round((1 - sale / original) * 100, 1)
    return None


def extract_vintage(name: str) -> Optional[str]:
    m = re.search(r"\b(19|20)\d{2}\b", name)
    return m.group() if m else None


def extract_volume(name: str) -> Optional[int]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|ML|ℓ|l\b|L\b)", name)
    if m:
        val, unit = float(m.group(1)), m.group(2).lower()
        return int(val * 1000) if unit in ("l", "ℓ") else int(val)
    return None


# ── 베이스 크롤러 ──────────────────────────────────────────────
class BaseCrawler(ABC):
    STORE_ID    = ""
    STORE_LABEL = ""
    WINE_KEYWORDS = ["와인", "wine", "샴페인", "스파클링", "브뤼", "로제", "카바", "프로세코"]

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.results: list[dict] = []

    async def _new_page(self, browser: Browser) -> Page:
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 390, "height": 844},
        )
        page = await ctx.new_page()
        # 이미지·폰트 차단 → 속도 향상
        await page.route(
            re.compile(r"\.(png|jpg|jpeg|gif|webp|woff2?|ttf|otf|svg)(\?.*)?$"),
            lambda r: r.abort(),
        )
        # 봇 탐지 우회
        await page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        return page

    async def _scroll_down(self, page: Page, times: int = 4, delay: float = 1.0):
        for _ in range(times):
            await page.keyboard.press("End")
            await asyncio.sleep(delay)

    @abstractmethod
    async def crawl(self, page: Page) -> list[dict]:
        ...

    def _build(self, **kw) -> dict:
        name     = kw.get("name", "")
        original = kw.get("price_original")
        sale     = kw.get("price_sale")
        return {
            "store":           self.STORE_ID,
            "store_label":     self.STORE_LABEL,
            "product_id":      kw.get("product_id"),
            "name":            name,
            "name_normalized": normalize_name(name),
            "price_original":  original,
            "price_sale":      sale,
            "discount_rate":   kw.get("discount_rate") or extract_discount_rate(original, sale),
            "discount_label":  kw.get("discount_label"),
            "wine_type":       kw.get("wine_type") or classify_wine_type(name),
            "origin_country":  kw.get("origin_country"),
            "origin_region":   kw.get("origin_region"),
            "grape":           kw.get("grape"),
            "vintage":         kw.get("vintage") or extract_vintage(name),
            "volume_ml":       kw.get("volume_ml") or extract_volume(name),
            "abv":             kw.get("abv"),
            "event_name":      kw.get("event_name"),
            "sale_start":      kw.get("sale_start"),
            "sale_end":        kw.get("sale_end"),
            "condition":       kw.get("condition"),
            "stock_limited":   kw.get("stock_limited", False),
            "image_url":       kw.get("image_url"),
            "product_url":     kw.get("product_url"),
            "crawled_at":      datetime.utcnow(),
        }

    def _is_wine(self, name: str) -> bool:
        return any(kw in name.lower() for kw in self.WINE_KEYWORDS)

    async def run(self) -> list[dict]:
        logger.info(f"[{self.STORE_LABEL}] 크롤링 시작")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            try:
                page = await self._new_page(browser)
                self.results = await self.crawl(page)
                logger.success(f"[{self.STORE_LABEL}] {len(self.results)}개 수집")
            except Exception as e:
                logger.error(f"[{self.STORE_LABEL}] 오류: {e}")
                self.results = []
            finally:
                await browser.close()
        return self.results

    async def debug_save_html(self, page: Page, filename: str = "debug.html"):
        """셀렉터 디버깅용 — HTML 저장"""
        content = await page.content()
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug(f"HTML 저장: {filename}")
