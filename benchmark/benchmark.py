import argparse
import asyncio
import json
import time
import statistics
import csv
from pathlib import Path
import httpx
import websockets

async def client_worker(
    client_id: int,
    base_url: str,
    token: str,
    room: str,
    num_messages: int,
    latencies: list,
    errors: list,
    acks: list,
    connected: list,
    gateway_distribution: dict
):
    ws_url = (
        base_url.replace("https://", "wss://").replace("http://", "ws://")
        + f"/ws/{room}?token={token}"
    )
    try:
        async with websockets.connect(ws_url, open_timeout=15, close_timeout=5) as ws:
            # Greet message
            greeting_raw = await asyncio.wait_for(ws.recv(), timeout=10)
            try:
                greeting = json.loads(greeting_raw)
                inst = greeting.get("instance_id", "unknown")
                gateway_distribution[inst] = gateway_distribution.get(inst, 0) + 1
            except Exception:
                pass

            connected[0] += 1

            for i in range(num_messages):
                started = time.perf_counter()
                payload = json.dumps({
                    "content": f"[Client {client_id} msg {i+1}] test message payload"
                })
                await ws.send(payload)

                while True:
                    event_raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    event = json.loads(event_raw)
                    if event.get("type") == "ack":
                        lat = (time.perf_counter() - started) * 1000
                        latencies.append(lat)
                        acks[0] += 1
                        break
                    elif event.get("type") == "error":
                        errors.append(event.get("message", "server error"))
                        break
                    # Skip broadcast relay messages to self/others to find ack
    except Exception as exc:
        errors.append(f"Client {client_id} error: {str(exc)}")

async def run_benchmark(args):
    room_name = args.room.lower().strip()
    print(f"\n=======================================================")
    print(f" SocketScale WebSocket Benchmark")
    print(f" Target: {args.base} | Room: #{room_name}")
    print(f" Concurrent Clients: {args.clients} | Msgs/Client: {args.messages}")
    print(f" Total Expected Messages: {args.clients * args.messages}")
    print(f"=======================================================\n")

    # 1. Authenticate
    async with httpx.AsyncClient(timeout=20) as c:
        try:
            login_res = await c.post(
                f"{args.base}/api/auth/login",
                json={"username": args.username, "password": args.password}
            )
            login_res.raise_for_status()
            token = login_res.json()["access_token"]
        except Exception as e:
            print(f"Authentication failed: {e}")
            return None

        # 2. Ensure room exists
        try:
            await c.post(
                f"{args.base}/api/rooms",
                json={"name": room_name, "is_private": False},
                headers={"Authorization": f"Bearer {token}"}
            )
        except Exception:
            pass

    latencies = []
    errors = []
    acks = [0]
    connected = [0]
    gateway_distribution = {}

    started_all = time.perf_counter()

    tasks = [
        client_worker(
            cid,
            args.base,
            token,
            room_name,
            args.messages,
            latencies,
            errors,
            acks,
            connected,
            gateway_distribution
        )
        for cid in range(args.clients)
    ]

    await asyncio.gather(*tasks)

    duration = time.perf_counter() - started_all
    latencies.sort()

    def percentile(p):
        if not latencies:
            return 0.0
        idx = int(round(p * (len(latencies) - 1)))
        return round(latencies[idx], 2)

    expected = args.clients * args.messages
    acknowledged = acks[0]
    failed = expected - acknowledged
    throughput = round(acknowledged / duration, 2) if duration > 0 else 0.0
    mean_lat = round(statistics.mean(latencies), 2) if latencies else 0.0
    median_lat = percentile(0.50)
    p95_lat = percentile(0.95)
    max_lat = round(max(latencies), 2) if latencies else 0.0

    result = {
        "clients": args.clients,
        "messages_per_client": args.messages,
        "expected_messages": expected,
        "connected_clients": connected[0],
        "failed_connections": args.clients - connected[0],
        "acknowledged": acknowledged,
        "failed_messages": failed,
        "duration_seconds": round(duration, 3),
        "throughput_msg_per_sec": throughput,
        "mean_latency_ms": mean_lat,
        "median_latency_ms": median_lat,
        "p95_latency_ms": p95_lat,
        "max_latency_ms": max_lat,
        "gateway_distribution": gateway_distribution,
        "errors_count": len(errors),
        "sample_errors": errors[:10]
    }

    print(json.dumps(result, indent=2))

    # Save to local file
    output_json = Path(args.output_json) if args.output_json else Path("benchmark_results.json")
    output_json.write_text(json.dumps(result, indent=2))
    print(f"\n[+] Results saved to {output_json.resolve()}")

    if args.output_csv:
        csv_path = Path(args.output_csv)
        with open(csv_path, "w", newline="") as cf:
            writer = csv.writer(cf)
            writer.writerow(["Metric", "Value"])
            for k, v in result.items():
                if isinstance(v, (str, int, float, bool)):
                    writer.writerow([k, v])
                elif isinstance(v, dict):
                    writer.writerow([k, json.dumps(v)])
        print(f"[+] CSV exported to {csv_path.resolve()}")

    # Save to PostgreSQL via API
    if args.save:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                rep = {
                    "name": f"{args.clients} clients x {args.messages} msgs ({throughput} msg/s)",
                    "clients": args.clients,
                    "messages_per_client": args.messages,
                    "results": result
                }
                save_res = await c.post(
                    f"{args.base}/api/admin/benchmarks",
                    json=rep,
                    headers={"Authorization": f"Bearer {token}"}
                )
                save_res.raise_for_status()
                print(f"[+] Successfully saved benchmark run to PostgreSQL: ID={save_res.json().get('id')}")
        except Exception as se:
            print(f"[-] Could not save to database: {se}")

    return result

def main():
    parser = argparse.ArgumentParser(description="SocketScale Concurrent WebSocket Benchmark")
    parser.add_argument("--base", default="http://localhost:8080", help="Nginx or Gateway base URL")
    parser.add_argument("--username", default="admin", help="Username")
    parser.add_argument("--password", default="AdminPass123!", help="Password")
    parser.add_argument("--room", default="benchmark", help="Room name")
    parser.add_argument("--clients", type=int, default=50, help="Number of concurrent clients (1..500)")
    parser.add_argument("--messages", type=int, default=20, help="Messages per client (1..1000)")
    parser.add_argument("--save", action="store_true", help="Save report to PostgreSQL database")
    parser.add_argument("--output-json", default="benchmark_results.json", help="Path to output JSON")
    parser.add_argument("--output-csv", default=None, help="Path to output CSV (optional)")

    args = parser.parse_args()
    asyncio.run(run_benchmark(args))

if __name__ == "__main__":
    main()
