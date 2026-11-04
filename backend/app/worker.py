import asyncio
import os
import json
import time
from datetime import datetime
from sqlalchemy import select, desc
from redis.asyncio import Redis, ConnectionError
from .db import Session, Outbox, record_log

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

async def main():
    print("[Worker] Starting SocketScale Transactional Outbox Worker...")
    await record_log(
        event_type="SERVICE_LIFECYCLE",
        severity="INFO",
        component="worker",
        message="Transactional outbox worker started"
    )

    r = Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    redis_was_down = False
    
    while True:
        try:
            # Heartbeat check on Redis
            try:
                await r.set("socketscale:worker:heartbeat", str(time.time()), ex=15)
                if redis_was_down:
                    redis_was_down = False
                    print("[Worker] Redis reconnected! Resuming pending outbox event publishing.")
                    await record_log(
                        event_type="OUTBOX_WORKER",
                        severity="INFO",
                        component="worker",
                        message="Redis reconnected. Retrying pending outbox events."
                    )
            except Exception as r_err:
                if not redis_was_down:
                    redis_was_down = True
                    print(f"[Worker] Redis unreachable ({r_err}). Outbox will queue messages for retry.")
                    await record_log(
                        event_type="OUTBOX_WORKER",
                        severity="WARNING",
                        component="worker",
                        message=f"Redis unavailable: {str(r_err)[:100]}. Outbox events queued."
                    )
                await asyncio.sleep(1)
                continue

            # Process pending outbox entries
            async with Session() as session:
                stmt = (
                    select(Outbox)
                    .where(Outbox.published == False)
                    .order_by(Outbox.id)
                    .limit(100)
                )
                rows = (await session.scalars(stmt)).all()

                if rows:
                    published_batch = 0
                    for row in rows:
                        try:
                            payload_dict = json.loads(row.payload)
                            room_name = payload_dict.get("room", "general")
                            await r.publish(f"room:{room_name}", row.payload)
                            
                            row.published = True
                            row.published_at = datetime.utcnow()
                            row.last_error = None
                            published_batch += 1
                        except Exception as pub_exc:
                            row.retry_count += 1
                            row.last_error = str(pub_exc)[:400]
                            print(f"[Worker] Publish failed for outbox id {row.id}: {pub_exc}")
                            await r.incr("socketscale:worker:failed_publishes")
                            break # Redis connection issue, retry on next cycle

                    await session.commit()
                    if published_batch > 0:
                        await r.incrby("socketscale:worker:successful_publishes", published_batch)
                        # Process next batch without extra sleep if there was a full batch
                        if len(rows) == 100:
                            continue
        except asyncio.CancelledError:
            print("[Worker] Worker cancelled.")
            break
        except Exception as exc:
            # Could be database disconnect during fault injection
            await asyncio.sleep(1)
            continue

        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
