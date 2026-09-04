"""
启动存储索引初始化器

从 main.py 抽取的启动索引 initializer 清单；lifespan 启动时并发执行，
确保各存储的 ensure_indexes 在服务流量前就绪。
"""

from collections.abc import Awaitable, Callable

from src.infra.logging import get_logger

logger = get_logger(__name__)


def get_startup_index_initializers() -> list[tuple[str, Callable[[], Awaitable[None]]]]:
    async def _init_agent_config_storage() -> None:
        from src.infra.agent.config_storage import get_agent_config_storage

        await get_agent_config_storage().ensure_indexes()
        logger.info("Agent config storage indexes initialized")

    async def _init_model_storage() -> None:
        from src.infra.agent.model_storage import get_model_storage

        await get_model_storage().ensure_indexes()
        logger.info("Model storage indexes initialized")

    async def _init_channel_storage() -> None:
        from src.infra.channel.channel_storage import ChannelStorage

        await ChannelStorage().ensure_indexes_if_needed()
        logger.info("Channel storage indexes initialized")

    async def _init_skill_indexes() -> None:
        from src.infra.skill import init_skill_indexes

        await init_skill_indexes()
        logger.info("Skill indexes initialized")

    async def _init_trace_storage() -> None:
        from src.infra.session.trace_storage import get_trace_storage

        await get_trace_storage().ensure_indexes_if_needed()
        logger.info("TraceStorage initialized")

    async def _init_session_storage() -> None:
        from src.infra.session.storage import SessionStorage

        await SessionStorage().ensure_indexes_if_needed()
        logger.info("SessionStorage indexes initialized")

    async def _init_revealed_file_storage() -> None:
        from src.infra.revealed_file.storage import get_revealed_file_storage

        await get_revealed_file_storage().ensure_indexes_if_needed()
        logger.info("RevealedFileStorage indexes initialized")

    async def _init_notification_storage() -> None:
        from src.infra.notification.storage import NotificationStorage

        await NotificationStorage().create_indexes()
        logger.info("NotificationStorage indexes initialized")

    async def _init_push_subscription_storage() -> None:
        from src.infra.push.storage import PushSubscriptionStorage

        await PushSubscriptionStorage().create_indexes()
        logger.info("PushSubscription indexes initialized")

    async def _init_user_storage() -> None:
        from src.infra.user.storage import UserStorage

        await UserStorage().ensure_indexes_if_needed()
        logger.info("UserStorage indexes initialized")

    async def _init_usage_storage() -> None:
        from src.infra.usage.storage import get_usage_storage

        await get_usage_storage().ensure_indexes()
        logger.info("UsageStorage indexes initialized")

    async def _init_bookmark_storage() -> None:
        from src.infra.bookmark.storage import BookmarkStorage

        await BookmarkStorage().create_indexes()
        logger.info("BookmarkStorage indexes initialized")

    async def _init_pricing_storage() -> None:
        from src.infra.pricing.storage import get_pricing_storage

        await get_pricing_storage().ensure_indexes()
        logger.info("PricingStorage indexes initialized")

    async def _init_team_storage() -> None:
        from src.infra.team.storage import TeamStorage

        await TeamStorage().ensure_indexes()
        logger.info("TeamStorage indexes initialized")

    async def _init_project_storage() -> None:
        from src.infra.folder.storage import ProjectStorage

        await ProjectStorage().ensure_indexes()
        logger.info("ProjectStorage indexes initialized")

    async def _init_persona_preset_storage() -> None:
        from src.infra.persona_preset.storage import PersonaPresetStorage

        await PersonaPresetStorage().ensure_indexes()
        logger.info("PersonaPresetStorage indexes initialized")

    async def _init_role_storage() -> None:
        from src.infra.role.storage import RoleStorage

        await RoleStorage().ensure_indexes()
        logger.info("RoleStorage indexes initialized")

    async def _init_mcp_storage() -> None:
        from src.infra.mcp.storage import MCPStorage

        await MCPStorage().ensure_indexes()
        logger.info("MCPStorage indexes initialized")

    async def _init_file_record_storage() -> None:
        from src.infra.upload.file_record import FileRecordStorage

        await FileRecordStorage().initialize_indexes()
        logger.info("FileRecordStorage indexes initialized")

    async def _init_pat_storage() -> None:
        from src.infra.auth.pat import PATStorage

        await PATStorage().ensure_indexes()
        logger.info("PATStorage indexes initialized")

    return [
        ("agent_config_storage", _init_agent_config_storage),
        ("model_storage", _init_model_storage),
        ("channel_storage", _init_channel_storage),
        ("skill_indexes", _init_skill_indexes),
        ("trace_storage", _init_trace_storage),
        ("session_storage", _init_session_storage),
        ("revealed_file_storage", _init_revealed_file_storage),
        ("notification_storage", _init_notification_storage),
        ("push_subscription_storage", _init_push_subscription_storage),
        ("user_storage", _init_user_storage),
        ("usage_storage", _init_usage_storage),
        ("team_storage", _init_team_storage),
        ("project_storage", _init_project_storage),
        ("persona_preset_storage", _init_persona_preset_storage),
        ("role_storage", _init_role_storage),
        ("mcp_storage", _init_mcp_storage),
        ("file_record_storage", _init_file_record_storage),
        ("pricing_storage", _init_pricing_storage),
        ("bookmark_storage", _init_bookmark_storage),
        ("pat_storage", _init_pat_storage),
    ]
