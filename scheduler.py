"""
scheduler.py — APScheduler 주기 실행

python scheduler.py
"""
import asyncio
import os
from datetime import datetime, timedelta
from loguru import logger
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

from main import run_all, run_crawler, STORE_MAP
from crawlers.emart    import EmartCrawler
from crawlers.gs25     import GS25Crawler
from crawlers.cu       import CUCrawler
from crawlers.homeplus import HomeplusCrawler
from crawlers.kurly    import KurlyCrawler
from models import WineDeal

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wine:wine@localhost:5432/winedeals")
Session = sessionmaker(bind=create_engine(DATABASE_URL))


async def crawl_convenience():
    logger.info(">>> 편의점(GS25, CU) 크롤링")
    for C in [GS25Crawler, CUCrawler]:
        await run_crawler(C)
        await asyncio.sleep(3)


async def crawl_marts():
    logger.info(">>> 마트(이마트, 홈플러스) 크롤링")
    for C in [EmartCrawler, HomeplusCrawler]:
        await run_crawler(C)
        await asyncio.sleep(3)


async def crawl_online():
    logger.info(">>> 온라인(마켓컬리) 크롤링")
    await run_crawler(KurlyCrawler)


def deactivate_expired():
    """sale_end 지난 행사 비활성화"""
    s = Session()
    try:
        expired = s.query(WineDeal).filter(
            WineDeal.sale_end < datetime.utcnow(),
            WineDeal.is_active == True,
        ).all()
        for d in expired:
            d.is_active = False
        s.commit()
        if expired:
            logger.info(f"만료 처리: {len(expired)}개")
    except Exception as e:
        s.rollback(); logger.error(f"만료 처리 오류: {e}")
    finally:
        s.close()


def deactivate_stale():
    """48시간 이상 미갱신 → 행사 종료 간주"""
    s = Session()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=48)
        stale = s.query(WineDeal).filter(
            WineDeal.crawled_at < cutoff,
            WineDeal.is_active == True,
        ).all()
        for d in stale:
            d.is_active = False
        s.commit()
        if stale:
            logger.info(f"스테일 처리: {len(stale)}개")
    except Exception as e:
        s.rollback(); logger.error(f"스테일 처리 오류: {e}")
    finally:
        s.close()


async def main():
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    # 편의점: 09:00, 21:00
    scheduler.add_job(crawl_convenience, CronTrigger(hour="9,21", minute=0),
                      id="convenience", misfire_grace_time=600)
    # 마트: 10:00, 16:00
    scheduler.add_job(crawl_marts, CronTrigger(hour="10,16", minute=0),
                      id="marts", misfire_grace_time=600)
    # 온라인: 11:00, 23:00
    scheduler.add_job(crawl_online, CronTrigger(hour="11,23", minute=0),
                      id="online", misfire_grace_time=600)
    # 전체: 6시간마다
    scheduler.add_job(lambda: asyncio.create_task(run_all()),
                      IntervalTrigger(hours=6), id="full")
    # 만료 처리: 매일 00:05
    scheduler.add_job(deactivate_expired, CronTrigger(hour=0, minute=5), id="expire")
    # 스테일 처리: 매일 03:00
    scheduler.add_job(deactivate_stale, CronTrigger(hour=3, minute=0), id="stale")

    scheduler.start()
    logger.info("스케줄러 시작")
    for job in scheduler.get_jobs():
        logger.info(f"  {job.id}: {job.trigger}")

    # 시작 시 즉시 1회 실행
    await run_all()

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("스케줄러 종료")


if __name__ == "__main__":
    asyncio.run(main())
