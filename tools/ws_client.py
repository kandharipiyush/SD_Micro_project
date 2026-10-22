import argparse, asyncio, json
import websockets

async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--token", required=True)
    p.add_argument("--room", default="general")
    p.add_argument("--url", default="ws://localhost:8080/ws")
    a = p.parse_args()
    async with websockets.connect(f"{a.url}?token={a.token}&room={a.room}") as ws:
        print("Connected. Type messages; /quit exits.")
        async def reader():
            async for raw in ws:
                print("\\n<", json.dumps(json.loads(raw), ensure_ascii=False))
        task = asyncio.create_task(reader())
        try:
            while True:
                line = await asyncio.to_thread(input, "> ")
                if line.strip() == "/quit":
                    break
                if line.strip():
                    await ws.send(json.dumps({"content": line}))
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

if __name__ == "__main__":
    from contextlib import suppress
    asyncio.run(main())
