import argparse, asyncio, json, statistics, time
from datetime import datetime, timezone
import websockets

async def client(i, args, latencies, stats, errors):
    try:
        async with websockets.connect(f"{args.url}?token={args.token}&room={args.room}", open_timeout=10) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), 10))
            stats["connected"] += 1
            stats["instances"].add(hello.get("instance_id", "unknown"))
            for n in range(args.messages):
                content = f"bench-{i}-{n}-{time.perf_counter_ns()}"
                start = time.perf_counter()
                await ws.send(json.dumps({"content": content}))
                deadline = time.perf_counter() + 10
                while time.perf_counter() < deadline:
                    event = json.loads(await asyncio.wait_for(ws.recv(), max(.1, deadline-time.perf_counter())))
                    if event.get("type") == "message" and event.get("content") == content:
                        latencies.append((time.perf_counter()-start)*1000)
                        stats["acked"] += 1
                        break
                else:
                    errors.append(f"client {i}: ack timeout on message {n}")
    except Exception as exc:
        stats["errors"] += 1
        errors.append(f"client {i}: {type(exc).__name__}: {exc}")

async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--token", required=True)
    p.add_argument("--url", default="ws://localhost:8080/ws")
    p.add_argument("--room", default="bench")
    p.add_argument("--clients", type=int, default=10)
    p.add_argument("--messages", type=int, default=20)
    p.add_argument("--output", default="benchmark_results.json")
    a = p.parse_args()
    if not 1 <= a.clients <= 500 or not 1 <= a.messages <= 10000:
        raise SystemExit("clients must be 1..500 and messages 1..10000")
    lat = []
    stats = {"connected": 0, "errors": 0, "acked": 0, "instances": set()}
    errors = []
    start = time.perf_counter()
    await asyncio.gather(*(client(i, a, lat, stats, errors) for i in range(a.clients)))
    elapsed = time.perf_counter() - start
    sorted_lat = sorted(lat)
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "clients": a.clients, "messages_each": a.messages,
        "duration_seconds": round(elapsed, 4),
        "connections_succeeded": stats["connected"], "connection_errors": stats["errors"],
        "messages_expected": a.clients*a.messages, "messages_acknowledged": stats["acked"],
        "throughput_messages_per_second": round(stats["acked"]/elapsed, 2) if elapsed else 0,
        "latency_ms": {
            "mean": round(statistics.mean(lat), 3) if lat else None,
            "median": round(statistics.median(lat), 3) if lat else None,
            "p95": round(sorted_lat[min(len(sorted_lat)-1, int(.95*len(sorted_lat)))], 3) if lat else None,
            "min": round(min(lat), 3) if lat else None, "max": round(max(lat), 3) if lat else None},
        "gateway_instances_seen": sorted(stats["instances"]), "errors_detail": errors[:50],
        "note": "Local send-to-self-ack benchmark. Repeat and record host resources; not a formal capacity guarantee."
    }
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print("Saved:", a.output)

if __name__ == "__main__":
    asyncio.run(main())
