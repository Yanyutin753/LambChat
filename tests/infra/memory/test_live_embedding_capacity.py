"""Opt-in real-provider, synthetic 180-day/50k-memory capacity evidence.

Credentials and all evidence stay outside the repository. Never resume a started
cohort. Large runs require LAMBCHAT_MEMORY_QDRANT_BINARY for an isolated server;
small unit runs use embedded Qdrant. Timings are not production hardware proof.
"""

import asyncio
import hashlib
import json
import math
import os
import re
import time
from contextlib import AsyncExitStack
from contextvars import ContextVar
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.infra.memory.live_qdrant import capacity_qdrant_binary, isolated_qdrant
from tests.infra.memory.test_live_embedding import CORPUS, ROOT, read_embedding_profile

CAPACITY_SCALES = (1000, 10000, 50000)


def read_capacity_seed(path, model, dimensions):
    path = Path(path).resolve()
    if ROOT == path or ROOT in path.parents or path.stat().st_mode & 0o077:
        raise ValueError("Capacity seed must be private and external")
    seed = json.loads(path.read_text())
    report = json.loads(Path(seed["source_report"]).read_text())
    if (
        not re.fullmatch(r"memory_real_capacity_[a-f0-9]{32}", report.get("database", ""))
        or report.get("model") != model
        or report.get("dimensions") != dimensions
        or type(seed.get("next_input_index")) is not int
        or seed["next_input_index"] < 0
    ):
        raise ValueError("Invalid capacity seed")
    minimum = report.get("next_input_index")
    if minimum is None:
        events = [
            json.loads(line)
            for line in Path(seed["source_report"])
            .with_name("provider-calls.jsonl")
            .read_text()
            .splitlines()
        ]
        minimum = sum(event["count"] for event in events if event["state"] == "started") - len(
            json.loads(CORPUS.read_text())["queries"]
        )
    if type(minimum) is not int or seed["next_input_index"] < minimum:
        raise ValueError("Capacity seed would repeat started inputs")
    return seed, report


def capacity_fact(index):
    topics = (
        "花园养护: 植物分区的浇水周期为 {n} 天，编号 {i} 的花盆使用陶粒覆盖，浇水前先检查土壤湿度。",
        "Workshop supplies: rack {i} holds {n} reusable clamps for furniture repairs.",
        "語学学習: ノート {i} の復習間隔は {n} 日で、発音練習を朝に行い、学習後に進捗を記録する。",
        "주방 계획: 조리대 {i}의 수납함에는 재사용 용기 {n}개를 보관하고 뚜껑은 같은 칸에 둔다.",
        "Домашние растения: участок {i} требует {n} мерных стаканов воды за неделю.",
        "家庭维修: 零件柜 {i} 存有 {n} 枚备用螺丝，每周五核对库存，使用后归还到对应的标号位置。",
        "Music practice: exercise {i} uses a metronome at {n} beats per minute.",
        "読書記録: 棚 {i} の本は毎回 {n} ページずつ読み、紙に感想を書き、次に読む章を確認する。",
        "운동 습관: 코스 {i}에서는 매일 {n}분 동안 걷고 물을 준비하며 마친 뒤 시간을 기록한다.",
        "Кулинарные заметки: рецепт {i} использует {n} граммов чечевицы и овощной бульон.",
        "摄影器材: 镜头柜 {i} 的干燥剂每隔 {n} 天更换，存放时盖好镜头盖，并在下次拍摄前检查湿度。",
        "Ceramic studio: kiln shelf {i} needs {n} test tiles before the next glaze firing.",
        "裁縫道具: 引き出し {i} に布見本 {n} 枚を保管し、色別に分類して、使用後は元の場所へ戻す。",
        "자전거 정비: 부품함 {i}의 체인은 {n}킬로미터마다 윤활 상태를 점검하고 주행 기록에 적는다.",
        "Походное снаряжение: ящик {i} содержит {n} запасных колышков для палатки.",
    )
    return topics[index % len(topics)].format(i=index, n=index * 17 % 211 + 15)


def batch_vectors(payload, count, dimensions):
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError("Invalid embedding batch size")
    result = [None] * count
    for row in rows:
        index = row.get("index") if isinstance(row, dict) else None
        vector = row.get("embedding") if isinstance(row, dict) else None
        if (
            type(index) is not int
            or not 0 <= index < count
            or result[index] is not None
            or not isinstance(vector, list)
            or len(vector) != dimensions
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
            or not any(vector)
        ):
            raise ValueError("Invalid embedding batch vector")
        result[index] = vector
    return result


@pytest.mark.skipif(
    os.environ.get("LAMBCHAT_MEMORY_EMBEDDING_CAPACITY") != "1",
    reason="Opt-in 50k real-provider embeddings; paid non-replayable cohort",
)
async def test_real_embedding_six_month_capacity(monkeypatch):
    import httpx
    from pymongo import AsyncMongoClient
    from qdrant_client.models import PointStruct

    from src.infra.llm.quota import bind_quota_user, unpriced_usage
    from src.infra.memory.client.native import search, vector_store
    from src.infra.memory.client.native.backend import NativeMemoryBackend
    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.infra.utils.datetime import utc_now
    from src.kernel.config import settings

    binary = capacity_qdrant_binary(CAPACITY_SCALES[-1])
    stack = AsyncExitStack()
    profile = read_embedding_profile(Path(os.environ["LAMBCHAT_MEMORY_EMBEDDING_PROFILE"]))
    seed_path = os.environ.get("LAMBCHAT_MEMORY_CAPACITY_SEED")
    seed, seed_report = (
        read_capacity_seed(
            seed_path,
            profile["NATIVE_MEMORY_EMBEDDING_MODEL"],
            profile["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"],
        )
        if seed_path
        else (None, None)
    )
    output = Path(os.environ["LAMBCHAT_MEMORY_EMBEDDING_OUTPUT"]).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Embedding evidence must stay outside the repository")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)

    def fingerprint():
        digest = hashlib.sha256()
        for path in [
            *sorted((ROOT / "src").rglob("*.py")),
            Path(__file__),
            Path(__file__).with_name("test_live_embedding.py"),
            Path(__file__).with_name("live_qdrant.py"),
            CORPUS,
        ]:
            digest.update(path.read_bytes())
        return digest.hexdigest()

    frozen = fingerprint()

    def save(name, value):
        with (output / name).open("w") as handle:
            os.chmod(handle.name, 0o600)
            json.dump(value, handle, ensure_ascii=False, indent=2, default=str)

    with (output / "started.json").open("x") as handle:
        os.chmod(handle.name, 0o600)
        json.dump(
            {
                "source_sha256": frozen,
                "scales": CAPACITY_SCALES,
                "model": profile["NATIVE_MEMORY_EMBEDDING_MODEL"],
                "qdrant_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()
                if binary
                else None,
            },
            handle,
        )
    client = AsyncMongoClient(build_mongo_connection_string(), timeoutMS=120000, tz_aware=True)
    stack.push_async_callback(client.close)
    database = f"memory_real_capacity_{uuid4().hex}"
    monkeypatch.setattr(settings, "MONGODB_DB", database)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)
    monkeypatch.setattr("src.infra.usage.storage.get_mongo_client", lambda: client)
    db = client[database]
    owner = str(
        (
            await db.users.insert_one(
                {
                    "username": "desktop_dev",
                    "email": "desktop_dev@example.com",
                    "password_hash": "unused",
                    "roles": ["memory_eval"],
                    "is_active": True,
                }
            )
        ).inserted_id
    )
    await db.roles.insert_one({"name": "memory_eval", "limits": {}})
    backend = NativeMemoryBackend()
    stack.push_async_callback(backend.close)
    backend._collection = db.native_memories
    index = vector_store.QdrantVectorIndex(
        location=":memory:", dims=profile["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"]
    )
    stack.push_async_callback(index.close)
    monkeypatch.setattr(vector_store, "_vector_index", index)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo")
    actual_search = index.search
    vector_searches = []
    mongo_scans = []
    query_scans = ContextVar("capacity_query_scans", default=None)
    actual_cosine_search = search._mongo_cosine_search

    async def observed_cosine(backend, base, query_vec, limit):
        full = base.get("_vector_pending") != {"$exists": True}
        mongo_scans.append(full)
        if query_scans.get() is not None:
            query_scans.get().append(full)
        return await actual_cosine_search(backend, base, query_vec, limit)

    monkeypatch.setattr(search, "_mongo_cosine_search", observed_cosine)

    async def observed_search(**kwargs):
        result = await actual_search(**kwargs)
        vector_searches.append(bool(result))
        return result

    monkeypatch.setattr(index, "search", observed_search)
    report = {
        "state": "started",
        "source_sha256": frozen,
        "database": database,
        "model": profile["NATIVE_MEMORY_EMBEDDING_MODEL"],
        "dimensions": profile["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"],
        "provider_calls": 0,
        "prompt_tokens": 0,
        "missing_token_receipts": 0,
        "cost_usd": None,
        "stages": [],
        "provider_failures": [],
        "qdrant_scoring": "Exact scoring inside Mongo-authorized IDs, with final Mongo hydration",
        "scope": "Real production-provider vectors, synthetic ages 0-180 days and isolated Mongo/local in-memory Qdrant; precomputed query vectors; not production ANN/hardware/elapsed-six-month proof.",
    }
    corpus = json.loads(CORPUS.read_text())
    aliases = {fact["id"]: uuid4().hex for fact in corpus["memories"]}
    journal = (output / "provider-calls.jsonl").open("x")
    os.chmod(journal.name, 0o600)

    def receipt(event):
        journal.write(json.dumps(event) + "\n")
        journal.flush()
        os.fsync(journal.fileno())

    async def quota_totals():
        ledger = await db.user_usage_quotas.find_one({"_id": owner})
        calls = (ledger or {}).get("calls", {})
        report["quota_calls"] = len(calls)
        report["quota_settled_unknown"] = sum(
            call.get("unknown") is True and call.get("pending") is False for call in calls.values()
        )
        report["auxiliary_usage_logs"] = await db[
            settings.MONGODB_USAGE_LOGS_COLLECTION
        ].count_documents({"user_id": owner})

    async with httpx.AsyncClient(
        base_url=profile["NATIVE_MEMORY_EMBEDDING_API_BASE"].rstrip("/"),
        headers={"Authorization": f"Bearer {profile['NATIVE_MEMORY_EMBEDDING_API_KEY']}"},
        timeout=60,
    ) as http:

        @bind_quota_user
        async def embed_batch(texts, user_id):
            call_id = uuid4().hex
            start = time.monotonic()
            receipt(
                {
                    "id": call_id,
                    "state": "started",
                    "count": len(texts),
                    "input_sha256": hashlib.sha256(
                        json.dumps(texts, ensure_ascii=False).encode()
                    ).hexdigest(),
                }
            )
            report["provider_calls"] += 1
            tokens = None
            status = None
            try:
                async with unpriced_usage():
                    response = await http.post(
                        "/v1/embeddings", json={"input": texts, "model": report["model"]}
                    )
                status = response.status_code
                try:
                    payload = response.json()
                except ValueError:
                    response.raise_for_status()
                    raise
                usage = payload.get("usage") if isinstance(payload, dict) else None
                raw_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
                tokens = raw_tokens if type(raw_tokens) is int and raw_tokens >= 0 else None
                response.raise_for_status()
                vectors = batch_vectors(payload, len(texts), report["dimensions"])
                receipt(
                    {
                        "id": call_id,
                        "state": "complete",
                        "http_status": response.status_code,
                        "prompt_tokens": tokens,
                        "elapsed_ms": (time.monotonic() - start) * 1000,
                    }
                )
                return vectors
            except BaseException as exc:
                receipt(
                    {
                        "id": call_id,
                        "state": "failed",
                        "failure_type": type(exc).__name__,
                        "http_status": status,
                        "prompt_tokens": tokens,
                        "elapsed_ms": (time.monotonic() - start) * 1000,
                    }
                )
                raise
            finally:
                if tokens is None:
                    report["missing_token_receipts"] += 1
                else:
                    report["prompt_tokens"] += tokens

        try:
            if binary:
                url, key = await stack.enter_async_context(isolated_qdrant(binary, output))
                await index.close()
                monkeypatch.setattr(settings, "NATIVE_MEMORY_QDRANT_API_KEY", key)
                index = vector_store.QdrantVectorIndex(location=url, dims=report["dimensions"])
                stack.push_async_callback(index.close)
                actual_search = index.search
                monkeypatch.setattr(vector_store, "_vector_index", index)
                monkeypatch.setattr(index, "search", observed_search)
                report["scope"] = report["scope"].replace(
                    "local in-memory Qdrant", "isolated local Qdrant server"
                )
            await db.native_memories.create_index([("user_id", 1), ("scope", 1), ("project_id", 1)])
            await index.ensure_collection()
            # Bulk input amortizes provider overhead; quota still reserves every HTTP call.
            query_vectors = (
                json.loads(Path(seed["query_vectors"]).read_text())
                if seed
                else dict(
                    zip(
                        [case["query"] for case in corpus["queries"]],
                        await embed_batch([case["query"] for case in corpus["queries"]], owner),
                    )
                )
            )
            if seed:
                query_vectors = query_vectors.get("queries", query_vectors)
                batch_vectors(
                    {
                        "data": [
                            {"index": i, "embedding": query_vectors[case["query"]]}
                            for i, case in enumerate(corpus["queries"])
                        ]
                    },
                    len(corpus["queries"]),
                    report["dimensions"],
                )
            save("query-vectors.json", query_vectors)

            async def precomputed(query):
                return query_vectors[query]

            backend._embedding_fn = precomputed
            now = utc_now()
            position = 0
            input_position = 0
            if seed:
                source = client[seed_report["database"]]
                source_owner = str(
                    (await source.users.find_one({"username": "desktop_dev"}))["_id"]
                )
                docs = await source.native_memories.find(
                    {"user_id": source_owner}, {"_id": 0}
                ).to_list(length=50001)
                assert len(docs) < CAPACITY_SCALES[-1]
                for doc in docs:
                    doc["user_id"] = owner
                    for fact in corpus["memories"]:
                        if fact["content"] == doc["content"]:
                            aliases[fact["id"]] = doc["memory_id"]
                assert all(any(doc["memory_id"] == mid for doc in docs) for mid in aliases.values())
                await db.native_memories.insert_many(docs)
                await index._client.upsert(
                    collection_name=vector_store.COLLECTION,
                    points=[
                        PointStruct(
                            id=UUID(hex=doc["memory_id"]),
                            vector=doc["embedding"],
                            payload={
                                key: doc[key]
                                for key in (
                                    "memory_id",
                                    "user_id",
                                    "scope",
                                    "project_id",
                                    "memory_type",
                                    "context",
                                )
                            },
                        )
                        for doc in docs
                    ],
                )
                foreign = [
                    {
                        **{key: value for key, value in doc.items() if key != "_id"},
                        "memory_id": uuid4().hex,
                        "user_id": "foreign",
                    }
                    for doc in docs[:8]
                ]
                await db.native_memories.insert_many(foreign)
                await index._client.upsert(
                    collection_name=vector_store.COLLECTION,
                    points=[
                        PointStruct(
                            id=UUID(hex=doc["memory_id"]),
                            vector=doc["embedding"],
                            payload={
                                key: doc[key]
                                for key in (
                                    "memory_id",
                                    "user_id",
                                    "scope",
                                    "project_id",
                                    "memory_type",
                                    "context",
                                )
                            },
                        )
                        for doc in foreign
                    ],
                )
                position = len(docs)
                input_position = seed["next_input_index"]
                report["reused_memories"] = position
                report["seed_source_report"] = seed["source_report"]
                save("report.json", report)
            for scale in CAPACITY_SCALES:
                assert fingerprint() == frozen, "Capacity evaluation source changed"
                started = time.monotonic()
                while position < scale:
                    facts = []
                    for offset in range(input_position, input_position + min(32, scale - position)):
                        if offset < len(corpus["memories"]):
                            fact = dict(corpus["memories"][offset])
                            fact["memory_id"] = aliases[fact["id"]]
                        else:
                            project = offset % 3 != 0
                            fact = {
                                "content": capacity_fact(offset),
                                "memory_id": uuid4().hex,
                                "scope": "project" if project else "user",
                                "project_id": f"capacity-project-{offset % 10}"
                                if project
                                else None,
                            }
                        facts.append(fact)
                    input_position += len(facts)
                    report["next_input_index"] = input_position
                    try:
                        vectors = await embed_batch([fact["content"] for fact in facts], owner)
                    except httpx.HTTPStatusError as exc:
                        # Never resend a started input; transient failures consume a new synthetic range.
                        if not seed or not 500 <= exc.response.status_code < 600:
                            raise
                        report["provider_failures"].append(
                            {"http_status": exc.response.status_code, "skipped_inputs": len(facts)}
                        )
                        save("report.json", report)
                        if len(report["provider_failures"]) >= 10:
                            raise
                        continue
                    docs = []
                    for offset, (fact, vector) in enumerate(zip(facts, vectors), position):
                        stamp = now - timedelta(days=180 if offset < len(aliases) else offset % 180)
                        docs.append(
                            {
                                "memory_id": fact["memory_id"],
                                "user_id": owner,
                                "content": fact["content"],
                                "title": fact["content"][:25],
                                "summary": fact["content"][:100],
                                "scope": fact["scope"],
                                "project_id": fact["project_id"],
                                "memory_type": "user",
                                "context": "user",
                                "source": "manual",
                                "tags": [],
                                "content_storage_mode": "inline",
                                "embedding": vector,
                                "created_at": stamp,
                                "updated_at": stamp,
                            }
                        )
                    if position == 0:
                        docs += [
                            {**doc, "user_id": "foreign", "memory_id": uuid4().hex}
                            for doc in docs[: len(aliases)]
                        ]
                    await db.native_memories.insert_many(docs)
                    await index._client.upsert(
                        collection_name=vector_store.COLLECTION,
                        points=[
                            PointStruct(
                                id=UUID(hex=doc["memory_id"]),
                                vector=doc["embedding"],
                                payload={
                                    key: doc[key]
                                    for key in (
                                        "memory_id",
                                        "user_id",
                                        "scope",
                                        "project_id",
                                        "memory_type",
                                        "context",
                                    )
                                },
                            )
                            for doc in docs
                        ],
                    )
                    position += len(facts)
                    if position % 1024 < 32 or position == scale:
                        report["embedded_memories"] = position
                        save("report.json", report)
                stage = {
                    "count": scale,
                    "ingest_seconds": time.monotonic() - started,
                    "queries": [],
                }
                report["stages"].append(stage)
                for engine in ("mongo", "qdrant"):
                    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", engine)
                    before_searches = len(vector_searches)
                    before_scans = len(mongo_scans)

                    async def recall(case):
                        start = time.monotonic()
                        scans = []
                        token = query_scans.set(scans)
                        try:
                            result = await backend.recall(
                                owner,
                                case["query"],
                                max_results=3,
                                project_id=case["project_id"],
                                touch_access=False,
                                enable_rerank=False,
                            )
                        finally:
                            query_scans.reset(token)
                        hits = result.get("memories", [])
                        return {
                            "engine": engine,
                            "actual_path": "qdrant+mongo_fallback"
                            if engine == "qdrant" and any(scans)
                            else engine,
                            "case": case["expected_id"],
                            "found": aliases[case["expected_id"]]
                            in [hit["memory_id"] for hit in hits],
                            "leaks": [
                                hit["memory_id"]
                                for hit in hits
                                if hit.get("user_id") != owner
                                or (
                                    hit.get("scope") == "project"
                                    and hit.get("project_id") != case["project_id"]
                                )
                            ],
                            "elapsed_ms": (time.monotonic() - start) * 1000,
                        }

                    for concurrency in (1, 8):
                        for begin in range(0, len(corpus["queries"]), concurrency):
                            results = await asyncio.gather(
                                *(
                                    recall(case)
                                    for case in corpus["queries"][begin : begin + concurrency]
                                )
                            )
                            stage["queries"].extend(
                                {**result, "concurrency": concurrency} for result in results
                            )
                    engine_searches = vector_searches[before_searches:]
                    stage[f"{engine}_qdrant_attempts"] = len(engine_searches)
                    stage[f"{engine}_mongo_full_scans"] = sum(mongo_scans[before_scans:])
                    assert len(engine_searches) == (
                        len(corpus["queries"]) * 2 if engine == "qdrant" else 0
                    )
                    assert all(engine_searches), "Qdrant fallback cannot pass as Qdrant evidence"
                save("report.json", report)
            await quota_totals()
            assert (
                report["quota_calls"]
                == report["quota_settled_unknown"]
                == report["auxiliary_usage_logs"]
                == report["provider_calls"]
            )
            assert fingerprint() == frozen, "Capacity evaluation source changed"
            assert all(
                query["found"] and not query["leaks"]
                for stage in report["stages"]
                for query in stage["queries"]
            )
            report["state"] = (
                "quality_pass_with_provider_failures" if report["provider_failures"] else "pass"
            )
        except BaseException as exc:
            report.update(state="fail", failure_type=type(exc).__name__)
            raise
        finally:
            try:
                await quota_totals()
            except BaseException as exc:
                report.update(state="fail", accounting_failure_type=type(exc).__name__)
                raise
            finally:
                try:
                    save("report.json", report)
                finally:
                    try:
                        journal.close()
                    except BaseException as exc:
                        report.update(state="fail", journal_failure_type=type(exc).__name__)
                        save("report.json", report)
                        raise
                    finally:
                        # Close every owned resource even if evidence or another close fails.
                        await stack.aclose()


def test_capacity_corpus_is_unique_multilingual_and_excludes_gold_facts():
    records = [capacity_fact(index) for index in range(50000)]
    assert len(set(records)) == 50000
    assert all(40 < len(record) < 500 for record in records), min(records, key=len)
    assert len({record.split(":", 1)[0] for record in records}) >= 10
    assert not any("bamboo benches" in record or "Cedar" in record for record in records)


def test_seed_cannot_repeat_an_already_started_input_range(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "database": "memory_real_capacity_" + "a" * 32,
                "model": "synthetic",
                "dimensions": 2,
                "next_input_index": 64,
            }
        )
    )
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"source_report": str(report), "next_input_index": 32}))
    seed.chmod(0o600)
    with pytest.raises(ValueError, match="started"):
        read_capacity_seed(seed, "synthetic", 2)


async def test_large_capacity_requires_server_before_database_or_paid_marker(monkeypatch, tmp_path):
    monkeypatch.delenv("LAMBCHAT_MEMORY_QDRANT_BINARY", raising=False)
    monkeypatch.setenv("LAMBCHAT_MEMORY_EMBEDDING_OUTPUT", str(tmp_path / "unused"))
    with pytest.raises(ValueError, match="Qdrant server binary"):
        await test_real_embedding_six_month_capacity(monkeypatch)
    assert not (tmp_path / "unused").exists()


def test_embedding_batch_validates_indices_dimensions_and_numeric_values():
    valid = {"data": [{"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]}]}
    assert batch_vectors(valid, 2, 2) == [[1.0, 0.0], [0.0, 1.0]]
    for payload in (
        {},
        {"data": valid["data"][:1]},
        {"data": [valid["data"][0]] * 2},
        {"data": [{"index": False, "embedding": [1.0, 0.0]}]},
        {"data": [{"index": 0, "embedding": [math.nan, 0.0]}]},
        {"data": [{"index": 0, "embedding": [True, 0.0]}]},
        {"data": [{"index": 0, "embedding": [0.0, 0.0]}]},
        {"data": [{"index": 0, "embedding": [1.0]}]},
    ):
        with pytest.raises(ValueError, match="embedding batch"):
            batch_vectors(payload, 1 if payload != {} else 2, 2)


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in MongoDB")
@pytest.mark.parametrize(
    "failure_mode",
    [
        "none",
        "seed",
        "seed_limit",
        "qdrant",
        "empty_qdrant",
        "vector",
        "http",
        "report_io",
        "journal_io",
    ],
)
async def test_capacity_runner_mock_provider_keeps_real_quota_and_refuses_replay(
    tmp_path, monkeypatch, failure_mode
):
    import sys

    import httpx
    from pymongo import AsyncMongoClient

    from src.infra.memory.client.native.vector_store import QdrantVectorIndex
    from src.infra.storage.mongodb import build_mongo_connection_string

    if failure_mode in ("qdrant", "empty_qdrant"):
        from unittest.mock import AsyncMock

        monkeypatch.setattr(
            QdrantVectorIndex,
            "search",
            AsyncMock(return_value=None if failure_mode == "qdrant" else []),
        )

    monkeypatch.setattr(sys.modules[__name__], "CAPACITY_SCALES", (40,))
    corpus = json.loads(CORPUS.read_text())
    vectors = {}
    for number, fact in enumerate(corpus["memories"]):
        vector = [float(i == number) for i in range(9)]
        vectors[fact["content"]] = vector
        vectors[
            next(case["query"] for case in corpus["queries"] if case["expected_id"] == fact["id"])
        ] = vector
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if (failure_mode == "seed" and len(requests) == 4) or (
            failure_mode == "seed_limit" and len(requests) > 3
        ):
            return httpx.Response(502, text="<html>synthetic upstream failure</html>")
        if failure_mode == "http":
            return httpx.Response(503, json={"error": "synthetic failure"})
        if failure_mode == "vector":
            return httpx.Response(200, json={"data": [], "usage": {"prompt_tokens": 80}})
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": vectors.get(text, [0.0] * 8 + [1.0])}
                    for index, text in reversed(list(enumerate(body["input"])))
                ],
                "usage": {"prompt_tokens": len(body["input"]) * 10},
            },
        )

    class MockClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "NATIVE_MEMORY_EMBEDDING_API_BASE": "https://example.invalid",
                "NATIVE_MEMORY_EMBEDDING_API_KEY": "synthetic",
                "NATIVE_MEMORY_EMBEDDING_MODEL": "synthetic",
                "NATIVE_MEMORY_EMBEDDING_DIMENSIONS": 9,
            }
        )
    )
    profile.chmod(0o600)
    output = tmp_path / "evidence"
    monkeypatch.setenv("LAMBCHAT_MEMORY_EMBEDDING_PROFILE", str(profile))
    monkeypatch.setenv("LAMBCHAT_MEMORY_EMBEDDING_OUTPUT", str(output))
    client = AsyncMongoClient(build_mongo_connection_string(), timeoutMS=10000)
    try:
        if failure_mode in ("report_io", "journal_io"):
            from contextlib import asynccontextmanager

            events = []
            databases = set()
            binary = tmp_path / "binary"
            binary.write_bytes(b"synthetic test runtime")
            monkeypatch.setattr(
                sys.modules[__name__], "capacity_qdrant_binary", lambda scale: binary
            )

            @asynccontextmanager
            async def fake_runtime(binary, output):
                events.append("started")
                try:
                    yield ":memory:", "synthetic"
                finally:
                    events.append("stopped")

            monkeypatch.setattr(sys.modules[__name__], "isolated_qdrant", fake_runtime)
            real_dump = json.dump

            def unavailable_report(value, handle, **kwargs):
                if failure_mode == "report_io" and handle.name.endswith("/report.json"):
                    databases.add(value["database"])
                    raise OSError("Report disk unavailable")
                return real_dump(value, handle, **kwargs)

            monkeypatch.setattr(json, "dump", unavailable_report)
            if failure_mode == "journal_io":
                real_open = Path.open

                class JournalFailure:
                    def __init__(self, handle):
                        self.handle = handle

                    def __getattr__(self, name):
                        return getattr(self.handle, name)

                    def close(self):
                        self.handle.close()
                        raise OSError("Journal disk unavailable")

                def unavailable_journal(path, mode="r", *args, **kwargs):
                    handle = real_open(path, mode, *args, **kwargs)
                    return (
                        JournalFailure(handle)
                        if path.name == "provider-calls.jsonl" and mode == "x"
                        else handle
                    )

                monkeypatch.setattr(Path, "open", unavailable_journal)
            try:
                with pytest.raises(OSError, match="Report disk|Journal disk"):
                    await test_real_embedding_six_month_capacity(monkeypatch)
                assert events == ["started", "stopped"]
                if failure_mode == "journal_io":
                    assert json.loads((output / "report.json").read_text())["state"] == "fail"
            finally:
                for database in databases:
                    await client.drop_database(database)
            return
        if failure_mode in ("qdrant", "empty_qdrant"):
            with pytest.raises(AssertionError, match="fallback"):
                await test_real_embedding_six_month_capacity(monkeypatch)
        elif failure_mode in ("http", "vector"):
            with pytest.raises(httpx.HTTPStatusError if failure_mode == "http" else ValueError):
                await test_real_embedding_six_month_capacity(monkeypatch)
        else:
            await test_real_embedding_six_month_capacity(monkeypatch)
        report = json.loads((output / "report.json").read_text())
        assert report["state"] == (
            "pass" if failure_mode in ("none", "seed", "seed_limit") else "fail"
        )
        count = 1 if failure_mode in ("http", "vector") else 3
        assert len(requests) == count
        assert (
            report["quota_calls"]
            == report["quota_settled_unknown"]
            == report["auxiliary_usage_logs"]
            == count
        )
        assert report["prompt_tokens"] == {"http": 0, "vector": 80}.get(failure_mode, 480)
        assert report["missing_token_receipts"] == int(failure_mode == "http")
        if failure_mode in ("none", "seed", "seed_limit", "qdrant", "empty_qdrant"):
            assert len(report["stages"][0]["queries"]) == 32
        with pytest.raises(FileExistsError):
            await test_real_embedding_six_month_capacity(monkeypatch)
        assert len(requests) == count
        if failure_mode in ("seed", "seed_limit"):
            seed = tmp_path / "seed.json"
            seed.write_text(
                json.dumps(
                    {
                        "source_report": str(output / "report.json"),
                        "query_vectors": str(output / "query-vectors.json"),
                        "next_input_index": 40,
                    }
                )
            )
            seed.chmod(0o600)
            monkeypatch.setenv("LAMBCHAT_MEMORY_CAPACITY_SEED", str(seed))
            monkeypatch.setenv("LAMBCHAT_MEMORY_EMBEDDING_OUTPUT", str(tmp_path / "continued"))
            monkeypatch.setattr(sys.modules[__name__], "CAPACITY_SCALES", (80,))
            if failure_mode == "seed_limit":
                with pytest.raises(httpx.HTTPStatusError):
                    await test_real_embedding_six_month_capacity(monkeypatch)
            else:
                await test_real_embedding_six_month_capacity(monkeypatch)
            continued = json.loads((tmp_path / "continued/report.json").read_text())
            try:
                if failure_mode == "seed_limit":
                    assert len(requests) == 13
                    assert len(continued["provider_failures"]) == 10
                    assert continued["quota_calls"] == continued["auxiliary_usage_logs"] == 10
                    return
                assert continued["state"] == "quality_pass_with_provider_failures"
                assert continued["reused_memories"] == 40 and continued["next_input_index"] == 112
                assert continued["quota_calls"] == continued["auxiliary_usage_logs"] == 3
                assert continued["missing_token_receipts"] == 1
                assert len(requests) == 6
                sent = [text for request in requests[1:] for text in request["input"]]
                assert len(sent) == len(set(sent)), "Started input was sent again"
            finally:
                await client.drop_database(continued["database"])
    finally:
        if (output / "report.json").exists() and (output / "report.json").stat().st_size:
            await client.drop_database(json.loads((output / "report.json").read_text())["database"])
        await client.close()
