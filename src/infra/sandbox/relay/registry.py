"""daemon 连接注册表：Redis + TTL 心跳判活（spec §3.2）。

多机形态（每用户多台机器共存）：

- ``sandbox:machine:{uid}:{mid}``  string  TTL 35s 判活，value 第五段 machine_name；
- ``sandbox:machset:{uid}``        set     在册 machine_id（懒清理失效成员）；
- ``sandbox:machname:{uid}``       hash    mid → 自定义展示名（rename 覆盖层，
  daemon 重连上报的 hostname 不会冲掉用户起的名字）；
- ``sandbox:machdefault:{uid}``    string  用户默认机。

legacy（未上报 machine_id 的 0.2.0 daemon）沿用旧 ``sandbox:clients:{uid}``
hash + 后连踢前连语义 + ``sandbox:req:{uid}`` 队列，在机器列表中以
:data:`LEGACY_MACHINE_ID` 伪机器出现——选择它时 :meth:`queue_key` 路由回
旧队列，老客户端零变化。

单机 value 形态（legacy hash 与多机 string 同构，按已知段数追加）：

- ``node_id``（M1 旧格式：未上报版本）；
- ``node_id|version``（M2）；
- ``node_id|version|platform``（M4 T3）；
- ``node_id|version|platform|confirm_policy``（服务端确认门）；
- ``node_id|version|platform|confirm_policy|machine_name``（多机）。
"""

from src.infra.storage.redis import get_redis_client

_TTL_SECONDS = 35

#: 旧 daemon（无 machine_id）的伪机器标识：机器列表占位 + 旧队列路由。
LEGACY_MACHINE_ID = "legacy"


def _key(user_id: str) -> str:
    return f"sandbox:clients:{user_id}"


def _machine_key(user_id: str, machine_id: str) -> str:
    return f"sandbox:machine:{user_id}:{machine_id}"


def _machset_key(user_id: str) -> str:
    return f"sandbox:machset:{user_id}"


def _machname_key(user_id: str) -> str:
    return f"sandbox:machname:{user_id}"


def _machdefault_key(user_id: str) -> str:
    return f"sandbox:machdefault:{user_id}"


def encode_node_value(
    node_id: str,
    version: str = "",
    platform: str = "",
    confirm_policy: str = "",
    machine_name: str = "",
) -> str:
    """hash value 编码：按已知段数追加，旧调用方保持旧形态。

    - 版本+平台+策略+机器名：``node_id|version|platform|confirm_policy|machine_name``；
    - 版本+平台+策略：``node_id|version|platform|confirm_policy``；
    - 版本+平台：``node_id|version|platform``；
    - 仅版本：``node_id|version``（M2 字节形态不变）；
    - 仅平台：``node_id||platform``（空版本段占位，第三段仍可解析）；
    - 都无：纯 ``node_id``（M1 形态）。
    """
    if machine_name:
        return f"{node_id}|{version}|{platform}|{confirm_policy}|{machine_name}"
    if confirm_policy:
        return f"{node_id}|{version}|{platform}|{confirm_policy}"
    if platform:
        return f"{node_id}|{version}|{platform}"
    return f"{node_id}|{version}" if version else node_id


def parse_daemon_version(value: str) -> str:
    """hash value 反解 daemon 版本（第二段）；段数不足（旧格式）返回空串。"""
    parts = value.split("|")
    return parts[1] if len(parts) > 1 else ""


def parse_daemon_platform(value: str) -> str:
    """hash value 反解 daemon 平台（第三段）；段数不足（旧格式）返回空串。"""
    parts = value.split("|")
    return parts[2] if len(parts) > 2 else ""


def parse_confirm_policy(value: str) -> str:
    """hash value 反解确认策略（第四段）；段数不足（旧格式）返回空串。"""
    parts = value.split("|")
    return parts[3] if len(parts) > 3 else ""


def parse_machine_name(value: str) -> str:
    """hash value 反解机器名（第五段）；段数不足（旧格式）返回空串。"""
    parts = value.split("|")
    return parts[4] if len(parts) > 4 else ""


class SandboxClientRegistry:
    def _redis(self):
        return get_redis_client()

    async def register(
        self,
        user_id: str,
        client_id: str,
        node_id: str,
        *,
        version: str = "",
        platform: str = "",
        confirm_policy: str = "",
        machine_id: str = "",
        machine_name: str = "",
    ) -> None:
        """注册连接。带 machine_id 走多机路径（同机重连只替换自身字段，其他
        机器不受影响）；缺 machine_id 走 legacy 路径（清空旧 hash 后连踢前连）。"""
        value = encode_node_value(node_id, version, platform, confirm_policy, machine_name)
        redis = self._redis()
        if machine_id:
            await redis.sadd(_machset_key(user_id), machine_id)
            await redis.set(_machine_key(user_id, machine_id), value, ex=_TTL_SECONDS)
            return
        await redis.delete(_key(user_id))  # 后连踢前连（legacy 单机语义）
        await redis.hset(_key(user_id), client_id, value)
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def heartbeat(
        self,
        user_id: str,
        client_id: str,
        node_id: str,
        *,
        version: str = "",
        platform: str = "",
        confirm_policy: str = "",
        machine_id: str = "",
        machine_name: str = "",
    ) -> None:
        value = encode_node_value(node_id, version, platform, confirm_policy, machine_name)
        redis = self._redis()
        if machine_id:
            await redis.sadd(_machset_key(user_id), machine_id)
            await redis.set(_machine_key(user_id, machine_id), value, ex=_TTL_SECONDS)
            return
        await redis.hset(_key(user_id), client_id, value)
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def unregister(self, user_id: str, client_id: str, machine_id: str = "") -> None:
        redis = self._redis()
        if machine_id:
            await redis.delete(_machine_key(user_id, machine_id))
            await redis.srem(_machset_key(user_id), machine_id)
            return
        await redis.hdel(_key(user_id), client_id)
        if not await redis.hgetall(_key(user_id)):
            await redis.delete(_key(user_id))

    async def is_online(self, user_id: str) -> bool:
        """任一机器在线（多机或 legacy）即在线。"""
        redis = self._redis()
        if await redis.exists(_key(user_id)):
            return True
        for mid in await redis.smembers(_machset_key(user_id)):
            if await redis.exists(_machine_key(user_id, mid)):
                return True
        return False

    async def get_active(self, user_id: str) -> tuple[str, str] | None:
        """legacy 活跃连接（旧 hash 首字段）。多机路径不经过此方法。"""
        fields = await self._redis().hgetall(_key(user_id))
        if not fields:
            return None
        client_id = next(iter(fields))
        return client_id, fields[client_id]

    # ------------------------------------------------------------------
    # 多机：列表 / 默认 / 重命名 / 移除 / 目标解析
    # ------------------------------------------------------------------

    async def list_machines(self, user_id: str) -> list[dict]:
        """在线机器列表（TTL 过期即离线、从集合懒清理）。

        返回 [{machine_id, name, platform, version, confirm_policy, online}]，
        ``online`` 恒 True（列表只含在册在线机；离线机 TTL 后自然消失，
        rename 覆盖层保留、机器重连时恢复展示）。
        """
        redis = self._redis()
        names = await redis.hgetall(_machname_key(user_id))
        machines: list[dict] = []
        for mid in sorted(await redis.smembers(_machset_key(user_id))):
            value = await redis.get(_machine_key(user_id, mid))
            if value is None:
                await redis.srem(_machset_key(user_id), mid)
                continue
            machines.append(
                {
                    "machine_id": mid,
                    "name": names.get(mid) or parse_machine_name(value) or mid,
                    "platform": parse_daemon_platform(value),
                    "version": parse_daemon_version(value),
                    "confirm_policy": parse_confirm_policy(value),
                    "online": True,
                }
            )
        active = await self.get_active(user_id)
        if active is not None:
            machines.append(
                {
                    "machine_id": LEGACY_MACHINE_ID,
                    "name": parse_daemon_platform(active[1]) or "Daemon",
                    "platform": parse_daemon_platform(active[1]),
                    "version": parse_daemon_version(active[1]),
                    "confirm_policy": parse_confirm_policy(active[1]),
                    "online": True,
                }
            )
        return machines

    async def set_default_machine(self, user_id: str, machine_id: str) -> None:
        await self._redis().set(_machdefault_key(user_id), machine_id)

    async def get_default_machine(self, user_id: str) -> str | None:
        return await self._redis().get(_machdefault_key(user_id))

    async def rename_machine(self, user_id: str, machine_id: str, name: str) -> None:
        await self._redis().hset(_machname_key(user_id), machine_id, name)

    async def forget_machine(self, user_id: str, machine_id: str) -> bool:
        """移除机器（仅离线可移除——在线机器先断连）。清默认机指向。"""
        if machine_id == LEGACY_MACHINE_ID:
            return False
        redis = self._redis()
        if await redis.exists(_machine_key(user_id, machine_id)):
            return False
        await redis.srem(_machset_key(user_id), machine_id)
        await redis.hdel(_machname_key(user_id), machine_id)
        if await redis.get(_machdefault_key(user_id)) == machine_id:
            await redis.delete(_machdefault_key(user_id))
        return True

    def queue_key(self, user_id: str, machine_id: str) -> str:
        """下发队列键：legacy 保持旧格式（无后缀），多机按机器分队列。"""
        if machine_id == LEGACY_MACHINE_ID:
            return f"sandbox:req:{user_id}"
        return f"sandbox:req:{user_id}:{machine_id}"

    async def resolve_target(self, user_id: str, machine_id: str | None = None) -> str | None:
        """解析执行目标机：显式指定 → 校验在线；缺省 → 默认机 → 唯一在线机
        → legacy。无可用机器返回 None（调用方按 DAEMON_OFFLINE 收敛）。"""
        redis = self._redis()
        if machine_id:
            if machine_id == LEGACY_MACHINE_ID:
                return machine_id if await redis.exists(_key(user_id)) else None
            return machine_id if await redis.exists(_machine_key(user_id, machine_id)) else None
        default = await self.get_default_machine(user_id)
        if default and await self._machine_online(user_id, default):
            return default
        online = [
            mid
            for mid in await redis.smembers(_machset_key(user_id))
            if await redis.exists(_machine_key(user_id, mid))
        ]
        if len(online) == 1:
            return online[0]
        if await redis.exists(_key(user_id)):
            return LEGACY_MACHINE_ID
        return None

    async def _machine_online(self, user_id: str, machine_id: str) -> bool:
        if machine_id == LEGACY_MACHINE_ID:
            return await self._redis().exists(_key(user_id)) > 0
        return await self._redis().exists(_machine_key(user_id, machine_id)) > 0

    async def _machine_value(self, user_id: str, machine_id: str) -> str:
        """目标机的注册 value（resolve 后调用；离线返回空串）。"""
        redis = self._redis()
        if machine_id == LEGACY_MACHINE_ID:
            active = await self.get_active(user_id)
            return active[1] if active else ""
        value = await redis.get(_machine_key(user_id, machine_id))
        return value or ""

    async def get_platform(self, user_id: str, machine_id: str | None = None) -> str:
        """目标机的上报平台（win32/linux/darwin）。

        离线或旧格式 value（段数不足）返回空串——调用方（local.py 文件命令
        生成平台分支）按空串归一 posix，即「无平台信息 → 现状零变化」。
        """
        target = await self.resolve_target(user_id, machine_id)
        if target is None:
            return ""
        return parse_daemon_platform(await self._machine_value(user_id, target))

    async def get_confirm_policy(self, user_id: str, machine_id: str | None = None) -> str:
        """目标机的上报确认策略（all/commands/none）。

        离线或旧格式 value（段数不足）返回空串——调用方（local.py 确认门）
        按空串归一 all 保守确认。daemon 离线时门根本走不到（dispatch 先报
        DAEMON_OFFLINE），此查询只在在线会话的执行路径上发生。
        """
        target = await self.resolve_target(user_id, machine_id)
        if target is None:
            return ""
        return parse_confirm_policy(await self._machine_value(user_id, target))
