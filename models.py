"""models.py — SQLAlchemy ORM 정의"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class WineDeal(Base):
    __tablename__ = "wine_deals"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    # 채널
    store            = Column(String(50),  nullable=False)   # gs25|cu|emart|homeplus|kurly
    store_label      = Column(String(50))                    # 표시용 이름
    # 상품
    product_id       = Column(String(200))                   # 채널 내부 SKU
    name             = Column(String(300), nullable=False)
    name_normalized  = Column(String(300))                   # 비교용 정규화
    # 가격
    price_original   = Column(Integer)
    price_sale       = Column(Integer,     nullable=False)
    discount_rate    = Column(Float)                         # 0~100
    discount_label   = Column(String(50))
    # 와인 정보
    wine_type        = Column(String(30))                    # red|white|sparkling|rose|unknown
    origin_country   = Column(String(100))
    origin_region    = Column(String(100))
    grape            = Column(String(200))
    vintage          = Column(String(10))
    volume_ml        = Column(Integer)
    abv              = Column(Float)
    # 행사
    event_name       = Column(String(200))
    sale_start       = Column(DateTime)
    sale_end         = Column(DateTime)
    condition        = Column(Text)                          # 카드조건, 앱전용 등
    stock_limited    = Column(Boolean, default=False)
    # 링크
    image_url        = Column(Text)
    product_url      = Column(Text)
    # 메타
    crawled_at       = Column(DateTime, default=datetime.utcnow)
    is_active        = Column(Boolean,  default=True)

    __table_args__ = (
        UniqueConstraint("store", "product_id",       name="uq_store_pid"),
        Index("ix_store_active",   "store", "is_active"),
        Index("ix_discount_rate",  "discount_rate"),
        Index("ix_price_sale",     "price_sale"),
        Index("ix_wine_type",      "wine_type"),
    )

    def to_dict(self):
        return {
            "id":             self.id,
            "store":          self.store,
            "store_label":    self.store_label,
            "name":           self.name,
            "price_sale":     self.price_sale,
            "price_original": self.price_original,
            "discount_rate":  self.discount_rate,
            "wine_type":      self.wine_type,
            "origin_country": self.origin_country,
            "event_name":     self.event_name,
            "condition":      self.condition,
            "sale_end":       self.sale_end.isoformat() if self.sale_end else None,
            "image_url":      self.image_url,
            "product_url":    self.product_url,
            "crawled_at":     self.crawled_at.isoformat() if self.crawled_at else None,
        }


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id          = Column(Integer,   primary_key=True, autoincrement=True)
    store       = Column(String(50), nullable=False)
    started_at  = Column(DateTime,  default=datetime.utcnow)
    finished_at = Column(DateTime)
    status      = Column(String(20))   # success|error|partial
    items_found = Column(Integer,   default=0)
    error_msg   = Column(Text)
