"""
Native Memory Backend — MongoDB-backed, zero external dependencies.

Self-hosted memory system using MongoDB for storage with hybrid search
(text + optional vector). Inspired by Claude Code's memory architecture.
"""

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from src.infra.logging import get_logger
from src.infra.memory.client.base import MemoryBackend
from src.infra.memory.client.types import (
    EXCLUDED_CONTENT_PATTERNS,
    HIGH_SIGNAL_PATTERNS,
    MemoryType,
)
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

COLLECTION_NAME = "native_memories"

# ---------------------------------------------------------------------------
# Stop words for tag extraction
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    "the a an is are was were be been being have has had do does did will would "
    "could should may might can shall to of in for on with at by from as into "
    "through and but or not this that it its i my me you your we our they their "
    "he she his her also just very so if then when where what how which who "
    "there here about up out all some any no each every both few more most "
    "other some such only own same than too most".split()
)


# ============================================================================
# NativeMemoryBackend
# ============================================================================


class NativeMemoryBackend(MemoryBackend):
    """MongoDB-native memory backend. No external API dependencies."""

    def __init__(self):
        self._collection: Any = None
        self._embedding_fn: Optional[Callable] = None
        # In-memory cache for memory index: {user_id: (built_at, index_str)}
        self._index_cache: dict[str, tuple[float, str]] = {}

    @property
    def name(self) -> str:
        return "native"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Ensure indexes exist; set up optional embedding function."""
        self._ensure_collection()
        await self._create_indexes()
        self._setup_embedding_fn()

    async def close(self) -> None:
        self._collection = None
        self._embedding_fn = None
        self._index_cache.clear()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def retain(
        self,
        user_id: str,
        content: str,
        context: Optional[str] = None,
    ) -> dict[str, Any]:
        memory_type = self._classify_type(content, context)
        tags = self._extract_tags(content)
        summary = self._build_summary(content)
        memory_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)

        doc = {
            "memory_id": memory_id,
            "user_id": user_id,
            "content": content[:5000],
            "summary": summary,
            "memory_type": memory_type,
            "context": context,
            "tags": tags,
            "source": "manual",
            "embedding": await self._maybe_embed(content),
            "created_at": now,
            "updated_at": now,
            "accessed_at": now,
            "access_count": 0,
        }

        await self._collection.insert_one(doc)
        # Invalidate index cache
        self._index_cache.pop(user_id, None)

        return {
            "success": True,
            "memory_id": memory_id,
            "memory_type": memory_type,
            "message": "Memory stored successfully",
        }

    async def recall(
        self,
        user_id: str,
        query: str,
        max_results: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        text_results = await self._text_search(user_id, query, max_results * 2, memory_types)

        vector_results: list[dict] = []
        if self._embedding_fn:
            vector_results = await self._vector_search(
                user_id, query, max_results * 2, memory_types
            )

        memories = self._rrf_merge(text_results, vector_results, max_results)

        if memories:
            await self._update_access_stats([m["memory_id"] for m in memories])

        return {
            "success": True,
            "query": query,
            "memories": memories,
            "search_mode": "hybrid" if self._embedding_fn else "text",
        }

    async def delete(
        self,
        user_id: str,
        memory_id: str,
    ) -> dict[str, Any]:
        result = await self._collection.delete_one({"user_id": user_id, "memory_id": memory_id})
        if result.deleted_count > 0:
            self._index_cache.pop(user_id, None)
            return {"success": True, "message": f"Memory {memory_id} deleted"}
        return {"success": False, "error": "Memory not found"}

    # ------------------------------------------------------------------
    # Auto-retain (smart filtering)
    # ------------------------------------------------------------------

    async def auto_retain(
        self,
        user_id: str,
        conversation_summary: str,
        context: Optional[str] = None,
    ) -> None:
        memories = self._smart_filter_and_classify(conversation_summary)
        if not memories:
            return

        # Daily rate limit
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count = await self._collection.count_documents(
            {
                "user_id": user_id,
                "source": "auto_retained",
                "created_at": {"$gte": today},
            }
        )
        max_daily = getattr(settings, "NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY", 20)
        remaining = max_daily - daily_count
        if remaining <= 0:
            return

        now = datetime.now(timezone.utc)
        docs = []
        for mem in memories[: min(len(memories), remaining, 3)]:
            doc = {
                "memory_id": uuid.uuid4().hex,
                "user_id": user_id,
                "content": mem["content"][:5000],
                "summary": mem["summary"],
                "memory_type": mem["memory_type"],
                "context": context or "auto_retained",
                "tags": mem.get("tags", []),
                "source": "auto_retained",
                "embedding": await self._maybe_embed(mem["content"]),
                "created_at": now,
                "updated_at": now,
                "accessed_at": now,
                "access_count": 0,
            }
            docs.append(doc)

        if docs:
            await self._collection.insert_many(docs)
            self._index_cache.pop(user_id, None)
            logger.debug(f"[NativeMemory] Auto-retained {len(docs)} memories for {user_id}")

    # ------------------------------------------------------------------
    # Memory index (for system prompt injection)
    # ------------------------------------------------------------------

    async def build_memory_index(self, user_id: str) -> str:
        """
        Build lightweight memory index string for system prompt.
        Grouped by type, capped at 10 per type, with staleness warnings.
        """
        # Check cache (5 min TTL)
        cache_ttl = getattr(settings, "NATIVE_MEMORY_INDEX_CACHE_TTL", 300)
        cached = self._index_cache.get(user_id)
        if cached:
            built_at, cached_str = cached
            if (asyncio.get_event_loop().time() - built_at) < cache_ttl:
                return cached_str

        staleness_days = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)

        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$sort": {"updated_at": -1}},
            {
                "$group": {
                    "_id": "$memory_type",
                    "items": {
                        "$push": {
                            "summary": "$summary",
                            "updated_at": "$updated_at",
                        }
                    },
                }
            },
            {
                "$project": {
                    "items": {"$slice": ["$items", 10]},
                }
            },
        ]

        try:
            cursor = self._collection.aggregate(pipeline)
            groups = await cursor.to_list(length=4)
        except Exception as e:
            logger.warning(f"[NativeMemory] Failed to build index: {e}")
            return ""

        if not groups:
            return ""

        now = datetime.now(timezone.utc)
        type_order = {
            MemoryType.USER: 0,
            MemoryType.FEEDBACK: 1,
            MemoryType.PROJECT: 2,
            MemoryType.REFERENCE: 3,
        }
        groups.sort(key=lambda g: type_order.get(g["_id"], 99))

        lines = ["<memory_index>"]
        for group in groups:
            mtype = group["_id"]
            lines.append(f"\n## [{mtype}]")
            for item in group["items"]:
                age_days = (now - item["updated_at"]).days
                staleness = f" (stale: {age_days}d old)" if age_days > staleness_days else ""
                lines.append(f"- {item['summary']}{staleness}")

        lines.append("\n</memory_index>")
        result = "\n".join(lines)

        # Cache it
        self._index_cache[user_id] = (asyncio.get_event_loop().time(), result)
        return result

    # ------------------------------------------------------------------
    # Search implementations
    # ------------------------------------------------------------------

    async def _text_search(
        self,
        user_id: str,
        query: str,
        limit: int,
        memory_types: Optional[list[str]],
    ) -> list[dict]:
        base: dict[str, Any] = {"user_id": user_id}
        if memory_types:
            base["memory_type"] = {"$in": memory_types}
        base["$text"] = {"$search": query}

        try:
            cursor = (
                self._collection.find(
                    base,
                    {"score": {"$meta": "textScore"}},
                )
                .sort([("score", {"$meta": "textScore"})])
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
        except Exception:
            # Fallback: text index might not exist yet, do keyword match
            logger.debug("[NativeMemory] Text search failed, falling back to keyword match")
            docs = await self._keyword_fallback(user_id, query, limit, memory_types)

        return [self._format_memory(doc, doc.get("score", 0)) for doc in docs]

    async def _keyword_fallback(
        self,
        user_id: str,
        query: str,
        limit: int,
        memory_types: Optional[list[str]],
    ) -> list[dict]:
        """Simple keyword matching fallback when text index is unavailable."""
        words = [w for w in query.lower().split() if len(w) >= 2 and w not in _STOPWORDS][:5]
        if not words:
            return []

        base: dict[str, Any] = {"user_id": user_id}
        if memory_types:
            base["memory_type"] = {"$in": memory_types}
        base["$or"] = [{"content": {"$regex": re.escape(w), "$options": "i"}} for w in words]

        cursor = self._collection.find(base).sort("updated_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def _vector_search(
        self,
        user_id: str,
        query: str,
        limit: int,
        memory_types: Optional[list[str]],
    ) -> list[dict]:
        query_vec = await self._maybe_embed(query)
        if not query_vec:
            return []

        base: dict[str, Any] = {
            "user_id": user_id,
            "embedding": {"$exists": True, "$ne": None},
        }
        if memory_types:
            base["memory_type"] = {"$in": memory_types}

        # Try Atlas Vector Search
        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "native_mem_vector_idx",
                        "path": "embedding",
                        "queryVector": query_vec,
                        "numCandidates": limit * 5,
                        "limit": limit,
                    }
                },
                {"$match": base},
            ]
            cursor = self._collection.aggregate(pipeline)
            docs = await cursor.to_list(length=limit)
            return [self._format_memory(doc, doc.get("score", 1.0)) for doc in docs]
        except Exception:
            pass

        # Fallback: Python cosine similarity
        logger.debug("[NativeMemory] Atlas $vectorSearch unavailable, using Python cosine fallback")
        cursor = self._collection.find(base).limit(200)
        docs = await cursor.to_list(length=200)
        scored = []
        for d in docs:
            emb = d.get("embedding")
            if emb:
                sim = _cosine_similarity(query_vec, emb)
                scored.append((sim, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._format_memory(d, sim) for sim, d in scored[:limit]]

    # ------------------------------------------------------------------
    # Type classification
    # ------------------------------------------------------------------

    def _classify_type(self, content: str, context: Optional[str] = None) -> str:
        """Rule-based memory type classification."""
        content_lower = content.lower()

        # If context explicitly specifies a type, use it
        if context:
            ctx_lower = context.lower()
            for mt in MemoryType:
                if mt.value in ctx_lower:
                    return mt.value

        # Score each type by matching high-signal patterns
        scores: dict[str, float] = {}
        for mtype, patterns in HIGH_SIGNAL_PATTERNS.items():
            score = 0
            for pat in patterns:
                if re.search(pat, content_lower):
                    score += 1
            if score > 0:
                scores[mtype] = score

        if scores:
            # Tie-break: prefer first match in priority order
            max_score = max(scores.values())
            for mt in [
                MemoryType.FEEDBACK,
                MemoryType.REFERENCE,
                MemoryType.PROJECT,
                MemoryType.USER,
            ]:
                if mt.value in scores and scores[mt.value] == max_score:
                    return mt.value

        return MemoryType.USER

    # ------------------------------------------------------------------
    # Smart auto-retain filtering
    # ------------------------------------------------------------------

    def _smart_filter_and_classify(self, summary: str) -> list[dict]:
        """Multi-layer filter: noise, dedup, classify."""
        stripped = summary.strip()

        # Layer 1: length filter
        if len(stripped) < 20:
            return []

        # Layer 2: generic pattern filter
        first_line = stripped.split("\n")[0].lower()
        generic_starts = (
            "hello",
            "hi ",
            "hey",
            "thanks",
            "thank you",
            "ok",
            "okay",
            "sure",
            "yes",
            "no",
            "bye",
            "great",
        )
        if any(first_line.startswith(p) for p in generic_starts) and len(stripped) < 100:
            return []

        # Layer 3: noise filter (code patterns, file paths, etc.)
        for pat in EXCLUDED_CONTENT_PATTERNS:
            if re.search(pat, stripped, re.IGNORECASE):
                return []

        # Layer 4: signal matching — only retain if high-signal pattern matched
        has_signal = False
        for patterns in HIGH_SIGNAL_PATTERNS.values():
            for pat in patterns:
                if re.search(pat, stripped, re.IGNORECASE):
                    has_signal = True
                    break
            if has_signal:
                break

        if not has_signal:
            return []

        # Split into chunks (paragraphs)
        chunks = [p.strip() for p in stripped.split("\n\n") if len(p.strip()) > 30]
        if not chunks:
            chunks = [stripped]

        memories = []
        for chunk in chunks:
            mtype = self._classify_type(chunk)
            memories.append(
                {
                    "content": chunk,
                    "summary": self._build_summary(chunk),
                    "memory_type": mtype,
                    "tags": self._extract_tags(chunk),
                }
            )

        return memories[:3]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_tags(self, content: str) -> list[str]:
        words = content.lower().split()
        tags: list[str] = []
        seen: set[str] = set()
        for w in words:
            clean = w.strip(".,!?;:()[]{}\"'").lower()
            if len(clean) >= 3 and clean not in _STOPWORDS and clean not in seen:
                tags.append(clean)
                seen.add(clean)
        return tags[:5]

    def _build_summary(self, content: str, max_len: int = 100) -> str:
        # Take first sentence or truncate
        flat = content.replace("\n", " ").strip()
        sentences = flat.split(". ")
        if sentences and len(sentences[0]) <= max_len:
            return sentences[0].strip()
        if len(flat) > max_len:
            return flat[:max_len].strip() + "..."
        return flat

    @staticmethod
    def _format_memory(doc: dict, score: float) -> dict:
        now = datetime.now(timezone.utc)
        staleness_days = (now - doc["updated_at"]).days
        staleness_days_cfg = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)

        result: dict[str, Any] = {
            "memory_id": doc["memory_id"],
            "text": doc["content"],
            "summary": doc["summary"],
            "type": doc["memory_type"],
            "source": doc.get("source", "manual"),
            "created_at": doc["created_at"].isoformat()
            if isinstance(doc["created_at"], datetime)
            else str(doc["created_at"]),
            "score": score,
        }
        if staleness_days > staleness_days_cfg:
            result["staleness_warning"] = (
                f"This memory is {staleness_days} days old and may be outdated"
            )
        return result

    async def _update_access_stats(self, memory_ids: list[str]) -> None:
        await self._collection.update_many(
            {"memory_id": {"$in": memory_ids}},
            {
                "$set": {"accessed_at": datetime.now(timezone.utc)},
                "$inc": {"access_count": 1},
            },
        )

    async def _maybe_embed(self, text: str) -> Optional[list[float]]:
        if not self._embedding_fn:
            return None
        try:
            result = self._embedding_fn(text)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            logger.warning(f"[NativeMemory] Embedding failed: {e}")
            return None

    @staticmethod
    def _rrf_merge(
        text_results: list[dict],
        vector_results: list[dict],
        max_results: int,
        k: int = 60,
    ) -> list[dict]:
        scores: dict[str, dict] = {}

        for rank, item in enumerate(text_results):
            mid = item["memory_id"]
            if mid not in scores:
                scores[mid] = {"data": item, "rrf_score": 0.0}
            scores[mid]["rrf_score"] += 1.0 / (k + rank + 1)

        for rank, item in enumerate(vector_results):
            mid = item["memory_id"]
            if mid not in scores:
                scores[mid] = {"data": item, "rrf_score": 0.0}
            scores[mid]["rrf_score"] += 1.0 / (k + rank + 1)

        merged = sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)
        return [entry["data"] for entry in merged[:max_results]]

    # ------------------------------------------------------------------
    # MongoDB setup
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        client = get_mongo_client()
        db = client[settings.MONGODB_DB]
        self._collection = db[COLLECTION_NAME]

    async def _create_indexes(self) -> None:
        sync_col = get_mongo_client().delegate[settings.MONGODB_DB][COLLECTION_NAME]
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._create_indexes_sync, sync_col)

    @staticmethod
    def _create_indexes_sync(col: Any) -> None:
        col.create_index(
            [("user_id", 1), ("memory_type", 1), ("created_at", -1)],
            name="native_mem_user_type_idx",
        )
        col.create_index(
            [("memory_id", 1)],
            name="native_mem_id_idx",
            unique=True,
        )
        col.create_index(
            [("user_id", 1), ("updated_at", -1), ("access_count", -1)],
            name="native_mem_recency_idx",
        )
        try:
            col.create_index(
                [("user_id", 1), ("content", "text"), ("summary", "text"), ("tags", "text")],
                name="native_mem_text_idx",
                weights={"content": 10, "summary": 5, "tags": 2},
            )
        except Exception as e:
            # Text index creation can fail on existing collections with conflicts
            logger.warning(f"[NativeMemory] Text index creation skipped: {e}")

    def _setup_embedding_fn(self) -> None:
        """Set up optional embedding function from config."""
        api_base = getattr(settings, "NATIVE_MEMORY_EMBEDDING_API_BASE", "")
        api_key = getattr(settings, "NATIVE_MEMORY_EMBEDDING_API_KEY", "")
        model = getattr(settings, "NATIVE_MEMORY_EMBEDDING_MODEL", "text-embedding-3-small")

        if not api_base or not api_key:
            logger.debug("[NativeMemory] No embedding API configured, text-only mode")
            return

        try:
            import httpx

            client = httpx.AsyncClient(
                base_url=api_base.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0),
            )

            async def embed_fn(text: str) -> list[float]:
                resp = await client.post(
                    "/v1/embeddings",
                    json={"input": text, "model": model},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]

            self._embedding_fn = embed_fn
            logger.info(f"[NativeMemory] Embedding enabled: {api_base} ({model})")
        except ImportError:
            logger.warning("[NativeMemory] httpx not available, embedding disabled")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
