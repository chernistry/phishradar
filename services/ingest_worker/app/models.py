from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AnyHttpUrl, BaseModel


class UrlItem(BaseModel):
    url: AnyHttpUrl
    domain: str
    ts: datetime


class EnrichIn(BaseModel):
    url: AnyHttpUrl


class EnrichOut(BaseModel):
    url: AnyHttpUrl
    title: str
    snapshot_hash: str | None


class EmbedIn(BaseModel):
    url: AnyHttpUrl
    title: str
    domain: str


class EmbedOut(BaseModel):
    vector: list[float]
    model: str
    ms: int
    url: AnyHttpUrl
    title: str
    domain: str


class DedupIn(BaseModel):
    url: AnyHttpUrl
    vector: list[float]
    payload: dict


class DedupOut(BaseModel):
    is_duplicate: bool
    similarity: float
    qdrant_id: str | None


class SlackNotifyIn(BaseModel):
    url: AnyHttpUrl
    title: str
    similarity: float
    evidence: str | None = None


class Receipt(BaseModel):
    provider: str
    model: str
    tokens: int
    ms: int
    cost: Decimal
