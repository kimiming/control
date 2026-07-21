import asyncio
import signal

from app.core.config import get_settings
from app.services.incoming_listener import incoming_message_listener
from app.services.task_queue import task_queue


settings = get_settings()


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    incoming_message_listener.start()
    if settings.enable_task_queue:
        await task_queue.start()
    try:
        await stop_event.wait()
    finally:
        if settings.enable_task_queue:
            await task_queue.stop()
        await incoming_message_listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
