"""
main.py — 와인딜 전체 크롤러 실행 + DB 저장

사용법:
  python main.py              # 전체 실행
  python main.py --store emart  # 특정 채널만
  python main.py --headless false  # 브라우저 보이게
"""
import asyncio
import argparse
import os
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

from models import Base, WineDeal, CrawlLog
from crawlers.emart    import EmartCrawler
from crawlers.gs25     import GS25Crawler
from crawlers.cu       import CUCrawler
from crawlers.homeplus import HomeplusCrawler
from crawlers.kurly    import KurlyCrawler

# ── DB 연결 ────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wine:wine@localhost:5432/winedeals")
engine  = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

# 테이블 생성 (최초 1회)
Base.metadata.create_all(engine)

# ── Redis (옵션) ───────────────────────────────────────────────
try:
    import redis as _redis
    _rc = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    _rc.ping()
    logger.info("Redis 연결 OK")
except Exception:
    _rc = None
    logger.warning("Redis 미연결 — 캐시 비활성화")


ALL_CRAWLERS = [EmartCrawler, GS25Crawler, CUCrawler, HomeplusCrawler, KurlyCrawler]

STORE_MAP = {
    "emart":    EmartCrawler,
    "gs25":     GS25Crawler,
    "cu":       CUCrawler,
    "homeplus": HomeplusCrawler,
    "kurly":    KurlyCrawler,
}


# ── UPSERT ──────────────────────────────────────────────────────
def save_deals(items: list[dict], store: str) -> int:
    if not items:
        return 0

    session = Session()
    saved = 0
    try:
        for item in items:
            existing = None

            # 1) product_id 기반
            if item.get("product_id"):
                existing = (
                    session.query(WineDeal)
                    .filter_by(store=store, product_id=item["product_id"])
                    .first()
                )

            # 2) 이름 정규화 기반 (product_id 없을 때)
            if not existing and item.get("name_normalized"):
                existing = (
                    session.query(WineDeal)
                    .filter_by(store=store, name_normalized=item["name_normalized"])
                    .first()
                )

            if existing:
                existing.price_sale     = item.get("price_sale",     existing.price_sale)
                existing.price_original = item.get("price_original",  existing.price_original)
                existing.discount_rate  = item.get("discount_rate",   existing.discount_rate)
                existing.sale_end       = item.get("sale_end",        existing.sale_end)
                existing.condition      = item.get("condition",       existing.condition)
                existing.event_name     = item.get("event_name",      existing.event_name)
                existing.image_url      = item.get("image_url",       existing.image_url)
                existing.is_active      = True
                existing.crawled_at     = datetime.utcnow()
            else:
                allowed = {c.key for c in WineDeal.__table__.columns}
                filtered = {k: v for k, v in item.items() if k in allowed and k != "id"}
                session.add(WineDeal(**filtered))

            saved += 1

        session.commit()

        # Redis 캐시 무효화
        if _rc:
            for key in [f"deals:{store}", "deals:all", "best:5", "status"]:
                _rc.delete(key)

    except Exception as e:
        session.rollback()
        logger.error(f"[{store}] DB 저장 오류: {e}")
        saved = 0
    finally:
        session.close()

    return saved


def _log_crawl(store, status, items_found=0, error_msg=None, started_at=None):
    session = Session()
    try:
        session.add(CrawlLog(
            store=store,
            started_at=started_at or datetime.utcnow(),
            finished_at=datetime.utcnow(),
            status=status,
            items_found=items_found,
            error_msg=error_msg,
        ))
        session.commit()
    finally:
        session.close()


# ── 채널별 실행 ─────────────────────────────────────────────────
async def run_crawler(CrawlerClass, headless: bool = True) -> int:
    crawler = CrawlerClass(headless=headless)
    started = datetime.utcnow()
    try:
        items = await crawler.run()
        saved = save_deals(items, crawler.STORE_ID)
        _log_crawl(crawler.STORE_ID, "success", saved, started_at=started)
        logger.success(f"[{crawler.STORE_LABEL}] 저장 {saved}개")
        return saved
    except Exception as e:
        _log_crawl(crawler.STORE_ID, "error", 0, str(e), started_at=started)
        logger.error(f"[{crawler.STORE_LABEL}] 실패: {e}")
        return 0


async def run_all(crawlers=None, headless: bool = True) -> int:
    crawlers = crawlers or ALL_CRAWLERS
    logger.info(f"=== 크롤링 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    total = 0
    for C in crawlers:
        total += await run_crawler(C, headless=headless)
        await asyncio.sleep(3)   # 채널 간 대기
    logger.info(f"=== 완료: 총 {total}개 저장 ===")
    return total


# ── CLI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="와인딜 크롤러")
    parser.add_argument("--store",    default="all",   help="all | emart | gs25 | cu | homeplus | kurly")
    parser.add_argument("--headless", default="true",  help="true | false")
    args = parser.parse_args()

    headless = args.headless.lower() != "false"

    if args.store == "all":
        asyncio.run(run_all(headless=headless))
    elif args.store in STORE_MAP:
        asyncio.run(run_crawler(STORE_MAP[args.store], headless=headless))
    else:
        print(f"알 수 없는 채널: {args.store}")
        print(f"사용 가능: {list(STORE_MAP.keys())}")
