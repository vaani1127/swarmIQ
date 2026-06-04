import logging
import os
import uuid

logger = logging.getLogger("swarmiq")

COSMOS_CONNECTION_STRING = os.getenv("COSMOS_DB_CONNECTION_STRING", "")
DB_NAME = os.getenv("COSMOS_DB_DATABASE_NAME", "swarmiq")
DB_ENABLED = bool(COSMOS_CONNECTION_STRING)

_client = None
_db = None


async def init_db() -> None:
    global _client, _db
    if not DB_ENABLED:
        logger.info("[DB] COSMOS_DB_CONNECTION_STRING not set — analysis history disabled")
        return
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        _client = AsyncIOMotorClient(COSMOS_CONNECTION_STRING)
        _db = _client[DB_NAME]
        await _db.command("ping")
        await _db.analyses.create_index([("user_id", 1), ("created_at", -1)])
        logger.info(f"[DB] Cosmos DB connected — database={DB_NAME}")
    except Exception as exc:
        logger.warning(f"[DB] Cosmos DB connection failed — {exc}")
        _client = None
        _db = None


async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None
        logger.info("[DB] Cosmos DB connection closed")


async def save_analysis(doc: dict) -> str:
    if _db is None:
        return ""
    if "_id" not in doc:
        doc["_id"] = str(uuid.uuid4())
    try:
        await _db.analyses.insert_one(doc)
        logger.info(f"[DB] saved analysis _id={doc['_id']} user={doc.get('user_id')}")
        return str(doc["_id"])
    except Exception as exc:
        logger.warning(f"[DB] save_analysis failed — {exc}")
        return ""


async def get_user_analyses(user_id: str, limit: int = 10) -> list[dict]:
    if _db is None:
        return []
    try:
        cursor = _db.analyses.find(
            {"user_id": user_id},
            {"query": 1, "company": 1, "created_at": 1, "status": 1, "_id": 1},
        ).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [_serialize(d) for d in docs]
    except Exception as exc:
        logger.warning(f"[DB] get_user_analyses failed — {exc}")
        return []


async def get_analysis_by_id(analysis_id: str) -> dict | None:
    if _db is None:
        return None
    try:
        doc = await _db.analyses.find_one({"_id": analysis_id})
        return _serialize(doc) if doc else None
    except Exception as exc:
        logger.warning(f"[DB] get_analysis_by_id failed — {exc}")
        return None


def _serialize(doc: dict | None) -> dict:
    """Coerce BSON-specific types (ObjectId, Decimal128) to plain strings."""
    if not doc:
        return {}
    result = {}
    for k, v in doc.items():
        if type(v).__name__ in ("ObjectId", "Decimal128"):
            result[k] = str(v)
        elif isinstance(v, dict):
            result[k] = _serialize(v)
        else:
            result[k] = v
    return result
