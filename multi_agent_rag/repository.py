from __future__ import annotations

# DynamoRepository로 완전 대체 — 기존 import 호환성 유지
from .dynamo_repository import DynamoRepository

MongoRepository = DynamoRepository

__all__ = ["DynamoRepository", "MongoRepository"]
