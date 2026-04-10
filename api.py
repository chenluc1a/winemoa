"""
api.py — 와인딜 FastAPI 서버

실행: uvicorn api:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker, Session as SASession
from dotenv import load_dotenv

load_dotenv()

from models import WineDeal, CrawlLog

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wine:wine@localhost:5432/winedeals")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# Redis 캐시
try:
    import redis as _redis
    _rc = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    _rc.ping()
    CACHE_ON = True
except Exception:
    _rc = None
    CACHE_ON = False

app = FastAPI(title="WineDeal API", version="1.0.0", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _cache_get(key):
    if _rc:
        v = _rc.get(key)
        return json.loads(v) if v else None
    return None


def _cache_set(key, data, ttl=120):
    if _rc:
        _rc.setex(key, ttl, json.dumps(data, ensure_ascii=False, default=str))


# ── 엔드포인트 ─────────────────────────────────────────────────

@app.get("/deals", summary="할인 와인 목록")
def get_deals(
    store:        Optional[str]   = Query(None, description="emart|gs25|cu|homeplus|kurly"),
    wine_type:    Optional[str]   = Query(None, description="red|white|sparkling|rose"),
    max_price:    Optional[int]   = Query(None, description="최대 가격(원)"),
    min_discount: Optional[float] = Query(None, description="최소 할인율(0~100)"),
    sort:         str             = Query("discount_rate", description="discount_rate|price_sale|crawled_at"),
    order:        str             = Query("desc", description="desc|asc"),
    limit:        int             = Query(50, le=200),
    offset:       int             = Query(0),
    db:           SASession       = Depends(get_db),
):
    ck = f"deals:{store}:{wine_type}:{max_price}:{min_discount}:{sort}:{order}:{limit}:{offset}"
    if cached := _cache_get(ck):
        return cached

    q = db.query(WineDeal).filter(WineDeal.is_active == True)
    if store:        q = q.filter(WineDeal.store == store)
    if wine_type:    q = q.filter(WineDeal.wine_type == wine_type)
    if max_price:    q = q.filter(WineDeal.price_sale <= max_price)
    if min_discount: q = q.filter(WineDeal.discount_rate >= min_discount)

    col = getattr(WineDeal, sort, WineDeal.discount_rate)
    q = q.order_by(col.desc() if order == "desc" else col.asc())

    total = q.count()
    items = [i.to_dict() for i in q.offset(offset).limit(limit).all()]
    result = {"total": total, "items": items}
    _cache_set(ck, result)
    return result


@app.get("/deals/best", summary="할인율 TOP N")
def best_deals(limit: int = Query(5, le=20), db: SASession = Depends(get_db)):
    ck = f"best:{limit}"
    if cached := _cache_get(ck):
        return cached
    items = (
        db.query(WineDeal)
        .filter(WineDeal.is_active == True, WineDeal.discount_rate.isnot(None))
        .order_by(WineDeal.discount_rate.desc())
        .limit(limit).all()
    )
    result = [i.to_dict() for i in items]
    _cache_set(ck, result, ttl=300)
    return result


@app.get("/deals/ending-soon", summary="마감 임박")
def ending_soon(days: int = Query(3), db: SASession = Depends(get_db)):
    cutoff = datetime.utcnow() + timedelta(days=days)
    items = (
        db.query(WineDeal)
        .filter(
            WineDeal.is_active == True,
            WineDeal.sale_end.isnot(None),
            WineDeal.sale_end <= cutoff,
        )
        .order_by(WineDeal.sale_end.asc())
        .limit(20).all()
    )
    return [i.to_dict() for i in items]


@app.get("/deals/search", summary="상품명 검색")
def search(q: str = Query(..., min_length=1), db: SASession = Depends(get_db)):
    items = (
        db.query(WineDeal)
        .filter(
            WineDeal.is_active == True,
            or_(
                WineDeal.name.ilike(f"%{q}%"),
                WineDeal.name_normalized.ilike(f"%{q}%"),
                WineDeal.grape.ilike(f"%{q}%"),
                WineDeal.origin_country.ilike(f"%{q}%"),
            ),
        )
        .order_by(WineDeal.discount_rate.desc())
        .limit(30).all()
    )
    return [i.to_dict() for i in items]


@app.get("/deals/{deal_id}", summary="상품 상세")
def get_deal(deal_id: int, db: SASession = Depends(get_db)):
    deal = db.query(WineDeal).filter_by(id=deal_id).first()
    if not deal:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")
    return deal.to_dict()


@app.get("/status", summary="채널별 크롤링 상태")
def status(db: SASession = Depends(get_db)):
    if cached := _cache_get("status"):
        return cached
    stores = ["emart", "gs25", "cu", "homeplus", "kurly"]
    result = []
    for store in stores:
        last = (
            db.query(CrawlLog)
            .filter_by(store=store)
            .order_by(CrawlLog.finished_at.desc())
            .first()
        )
        count = db.query(WineDeal).filter_by(store=store, is_active=True).count()
        result.append({
            "store":         store,
            "active_deals":  count,
            "last_crawled":  last.finished_at.isoformat() if last else None,
            "last_status":   last.status if last else "never",
            "last_items":    last.items_found if last else 0,
        })
    _cache_set("status", result, ttl=60)
    return result


@app.get("/stats", summary="전체 통계")
def stats(db: SASession = Depends(get_db)):
    total = db.query(WineDeal).filter_by(is_active=True).count()
    max_dr = (
        db.query(WineDeal.discount_rate)
        .filter(WineDeal.is_active == True, WineDeal.discount_rate.isnot(None))
        .order_by(WineDeal.discount_rate.desc())
        .first()
    )
    return {
        "total_active_deals": total,
        "max_discount_rate":  max_dr[0] if max_dr else None,
        "updated_at":         datetime.utcnow().isoformat(),
    }
