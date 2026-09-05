"""daemon 连接注册表：Redis hash + TTL 心跳判活（spec §3.2）。同用户仅一个活跃连接。

版本/平台地基（M2 终审 + M4 T3）：hash value 存下列形态之一——

- ``node_id``（M1 旧格式：未上报版本）；
- ``node_id|version``（M2：daemon connect URL 带 ``?version=``，channel 注册
  与心跳时写入，与仅版本的旧调用方字节形态保持一致）；
- ``node_id|version|platform``（M4 T3：URL 再带 ``?platform=``，第三段是
  ``sys.platform`` 归一值 linux/darwin/win32，服务端文件命令生成分支依据）。

``/api/sandbox/status`` 用 :func:`parse_daemon_version` /
:func:`parse_daemon_platform` 反解暴露；:func:`get_platform` 供命令生成侧
直接查询。段数不足的旧 value 解析出空平台——调用方按空归一 posix（现状）。
"""

from src.infra.storage.redis import get_redis_client

_TTL_SECONDS = 35


def _key(user_id: str) -> str:
    return f"sandbox:clients:{user_id}"


def encode_node_value(node_id: str, version: str = "", platform: str = "") -> str:
    """hash value 编码：按已知段数追加，旧调用方保持旧形态。

    - 版本+平台：``node_id|version|platform``；
    - 仅版本：``node_id|version``（M2 字节形态不变）；
    - 仅平台：``node_id||platform``（空版本段占位，第三段仍可解析）；
    - 都无：纯 ``node_id``（M1 形态）。
    """
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


class SandboxClientRegistry:
    def _redis(self):
        return get_redis_client()

    async def register(
        self, user_id: str, client_id: str, node_id: str, *, version: str = "", platform: str = ""
    ) -> None:
        redis = self._redis()
        await redis.delete(_key(user_id))  # 后连踢前连
        await redis.hset(_key(user_id), client_id, encode_node_value(node_id, version, platform))
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def heartbeat(
        self, user_id: str, client_id: str, node_id: str, *, version: str = "", platform: str = ""
    ) -> None:
        redis = self._redis()
        await redis.hset(_key(user_id), client_id, encode_node_value(node_id, version, platform))
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def unregister(self, user_id: str, client_id: str) -> None:
        redis = self._redis()
        await redis.hdel(_key(user_id), client_id)
        if not await redis.hgetall(_key(user_id)):
            await redis.delete(_key(user_id))

    async def is_online(self, user_id: str) -> bool:
        return bool(await self._redis().exists(_key(user_id)))

    async def get_active(self, user_id: str) -> tuple[str, str] | None:
        fields = await self._redis().hgetall(_key(user_id))
        if not fields:
            return None
        client_id = next(iter(fields))
        return client_id, fields[client_id]

    async def get_platform(self, user_id: str) -> str:
        """当前活跃 daemon 的上报平台（win32/linux/darwin）。

        离线或旧格式 value（段数不足）返回空串——调用方（local.py 文件命令
        生成平台分支）按空串归一 posix，即「无平台信息 → 现状零变化」。
        """
        active = await self.get_active(user_id)
        if active is None:
            return ""
        return parse_daemon_platform(active[1])
