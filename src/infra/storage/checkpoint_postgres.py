"""Batched delta reads for the explicitly supported PostgreSQL saver releases."""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import DeltaChannelHistory, get_checkpoint_id
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.postgres.base import (
    _DELTA_PAGE_SIZE,
    _build_delta_stage2_sql,
    _DeltaStage2Row,
)

_SEED_MEMBERSHIP_SQL = """
SELECT channel, version FROM checkpoint_blobs
WHERE thread_id = %s AND checkpoint_ns = %s AND type <> 'empty'
  AND (channel, version) IN (SELECT * FROM unnest(%s::text[], %s::text[]))
"""


class BatchedDeltaPostgresSaver(AsyncPostgresSaver):
    """Keep upstream reconstruction; probe each page's distinct seed keys once."""

    async def aget_delta_channel_history(
        self, *, config: RunnableConfig, channels: Sequence[str]
    ) -> Mapping[str, DeltaChannelHistory]:
        if not channels:
            return {}
        channels = list(channels)
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)
        if not checkpoint_id:
            target = await self.aget_tuple(config)
            if target is None:
                return {channel: {"writes": []} for channel in channels}
            checkpoint_id = target.config["configurable"]["checkpoint_id"]

        columns = [
            f"checkpoint -> 'channel_versions' ->> %s AS ver_{index}, "
            f"checkpoint -> 'channel_values' -> %s AS inline_{index}"
            for index in range(len(channels))
        ]
        stage1_prefix = (
            "SELECT checkpoint_id, parent_checkpoint_id, "
            + ", ".join(columns)
            + " FROM checkpoints WHERE thread_id = %s AND checkpoint_ns = %s"
        )
        parent_of: dict[str, str | None] = {}
        versions: list[dict[str, str | None]] = [{} for _ in channels]
        has_blobs: list[dict[str, bool]] = [{} for _ in channels]
        inline_values: list[dict[str, Any]] = [{} for _ in channels]
        chains: dict[str, list[str]] = {channel: [] for channel in channels}
        seed_versions: dict[str, str | None] = {channel: None for channel in channels}
        seed_inline: dict[str, Any] = {}
        walk_cursors: dict[str, str | None] = {}
        seeded: set[str] = set()
        cursor: str | None = checkpoint_id
        include_cursor = True

        async with self._cursor() as cur:
            while True:
                params: list[Any] = [value for channel in channels for value in (channel, channel)]
                stage1_sql = (
                    stage1_prefix + f" AND checkpoint_id {'<=' if include_cursor else '<'} %s"
                    " ORDER BY checkpoint_id DESC LIMIT %s"
                )
                params.extend([thread_id, checkpoint_ns, cursor, _DELTA_PAGE_SIZE])
                await cur.execute(stage1_sql, params)
                page = await cur.fetchall()
                if not page:
                    break
                keys = list(
                    dict.fromkeys(
                        (channel, row[f"ver_{index}"])
                        for row in page
                        for index, channel in enumerate(channels)
                        if row[f"ver_{index}"] is not None
                    )
                )
                present: set[tuple[str, str]] = set()
                if keys:
                    await cur.execute(
                        _SEED_MEMBERSHIP_SQL,
                        [
                            thread_id,
                            checkpoint_ns,
                            [channel for channel, _version in keys],
                            [version for _channel, version in keys],
                        ],
                    )
                    present = {(row["channel"], row["version"]) for row in await cur.fetchall()}
                for row in page:
                    for index, channel in enumerate(channels):
                        row[f"hb_{index}"] = (channel, row[f"ver_{index}"]) in present
                oldest = self._ingest_stage1_page(
                    page, channels, parent_of, versions, has_blobs, inline_values
                )
                self._try_advance_walks(
                    checkpoint_id,
                    channels,
                    parent_of,
                    versions,
                    has_blobs,
                    inline_values,
                    chains,
                    seed_versions,
                    seed_inline,
                    walk_cursors,
                    seeded,
                )
                if len(seeded) == len(channels) or len(page) < _DELTA_PAGE_SIZE:
                    break
                cursor = oldest
                include_cursor = False

        channels_with_chain = [channel for channel in channels if chains[channel]]
        channels_with_seed = [channel for channel in channels if seed_versions[channel] is not None]
        stage2_sql = _build_delta_stage2_sql(
            channels_with_chain=channels_with_chain,
            channels_with_seed=channels_with_seed,
        )
        rows = []
        if stage2_sql:
            params = []
            for channel in channels_with_chain:
                params.extend([thread_id, checkpoint_ns, channel, chains[channel]])
            for channel in channels_with_seed:
                params.extend([thread_id, checkpoint_ns, channel, seed_versions[channel]])
            async with self._cursor() as cur:
                await cur.execute(stage2_sql, params)
                rows = await cur.fetchall()
        return self._build_delta_channels_writes_history(
            channels=channels,
            chain_by_ch=chains,
            seed_ver_by_ch=seed_versions,
            seed_inline_by_ch=seed_inline,
            stage2_rows=cast("list[_DeltaStage2Row]", rows),
        )
