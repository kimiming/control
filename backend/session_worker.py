import asyncio
import signal

from app.services.incoming_listener import incoming_message_listener
from app.services.task_queue import task_queue


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    incoming_message_listener.start()
    await task_queue.start()
    try:
        await stop_event.wait()
    finally:
        await task_queue.stop()
        await incoming_message_listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
