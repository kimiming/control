import json
import uuid
from typing import Any

from app.core.cache import redis_client
from app.core.config import get_settings


settings = get_settings()


class SessionCommandError(RuntimeError):
    pass


class SessionCommandBus:
    def queue_key(self, session_id: int) -> str:
        shard = session_id % max(settings.session_worker_count, 1)
        return f"telegram:worker:{shard}:commands"

    async def execute(
        self,
        session_id: int,
        command: str,
        payload: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        command_id = uuid.uuid4().hex
        response_key = f"telegram:command:response:{command_id}"
        body = {
            "id": command_id,
            "session_id": session_id,
            "command": command,
            "payload": payload or {},
            "response_key": response_key,
        }
        await redis_client.rpush(self.queue_key(session_id), json.dumps(body, ensure_ascii=False))
        await redis_client.expire(self.queue_key(session_id), 86400)
        response = await redis_client.blpop(response_key, timeout=max(timeout, 1))
        if not response:
            raise SessionCommandError("Session Worker 响应超时，请检查真实在线状态")
        result = json.loads(response[1])
        if not result.get("ok"):
            raise SessionCommandError(str(result.get("error") or "Session命令执行失败"))
        return dict(result.get("result") or {})

    async def respond(self, key: str, result: dict[str, Any]) -> None:
        await redis_client.rpush(key, json.dumps(result, ensure_ascii=False))
        await redis_client.expire(key, 60)


session_command_bus = SessionCommandBus()
