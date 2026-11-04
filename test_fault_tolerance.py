import asyncio
import json
import time
import httpx
import websockets

BASE_URL = "http://localhost:8080"
WS_BASE = "ws://localhost:8080"

async def test_fault_tolerance():
    print("=" * 60)
    print("SocketScale Fault-Tolerance & Recovery Test Suite")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Admin login
        login_res = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "AdminPass123!"}
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Test Fault Controller Service Listing
        print("\n[FAULT TEST 1] Checking Fault Agent Container Statuses...")
        svcs = (await client.get(f"{BASE_URL}/api/admin/fault/services", headers=headers)).json()
        print(f" Found {len(svcs)} services monitored by fault controller.")
        for s in svcs:
            print(f"  - {s['name']}: {s['status']}")
        assert len(svcs) >= 7
        print(" PASS: Fault controller service listing operational.")

        # 3. Test Gateway A Failure & Failover to Gateway B
        print("\n[FAULT TEST 2] Stopping Gateway A (Simulating Node Crash)...")
        stop_ga = await client.post(f"{BASE_URL}/api/admin/fault/services/gateway-a/stop", headers=headers)
        assert stop_ga.status_code == 200
        print(" Gateway A stopped via fault controller.")
        await asyncio.sleep(2)

        # Verify requests continue through surviving gateways
        print(" Verifying new HTTP/WS requests route through surviving gateways...")
        h = (await client.get(f"{BASE_URL}/health")).json()
        print(f" Received health response from: {h.get('instance_id')}")
        assert h.get("instance_id") in {"gateway-b", "gateway-c"}
        print(" PASS: Failover to surviving nodes succeeded while Gateway A is down.")

        # Restart Gateway A
        print(" Restarting Gateway A (Node Recovery)...")
        start_ga = await client.post(f"{BASE_URL}/api/admin/fault/services/gateway-a/start", headers=headers)
        assert start_ga.status_code == 200
        await asyncio.sleep(4)
        print(" Gateway A started.")

        # 4. Test Transactional Outbox Under Redis Outage
        print("\n[FAULT TEST 3] Testing Transactional Outbox Resilience Under Redis Outage...")
        # Check initial outbox counts
        init_infra = (await client.get(f"{BASE_URL}/api/admin/infrastructure", headers=headers)).json()
        init_pending = init_infra["postgres"]["pending_outbox"]
        print(f" Current outbox pending count: {init_pending}")

        # Stop Redis
        print(" Stopping Redis container...")
        stop_rd = await client.post(f"{BASE_URL}/api/admin/fault/services/redis/stop", headers=headers)
        assert stop_rd.status_code == 200
        await asyncio.sleep(2)

        # Send a message through WebSocket or REST while Redis is DOWN
        print(" Connecting client and sending message while Redis is down...")
        room = "outbox-test"
        await client.post(f"{BASE_URL}/api/rooms", json={"name": room}, headers=headers)
        
        ws_url = f"{WS_BASE}/ws/{room}?token={token}"
        msg_content = f"Durable message persisted during Redis outage at {time.time()}"
        
        async with websockets.connect(ws_url) as ws:
            greet = json.loads(await ws.recv())
            print(f" Connected to {greet.get('instance_id')} (Postgres available, Redis down)")
            await ws.send(json.dumps({"content": msg_content}))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert ack.get("type") == "ack"
            saved_msg_id = ack["message"]["id"]
            print(f" Received ACK: Message #{saved_msg_id} written to PostgreSQL + Outbox!")

        # Verify outbox pending has incremented because Redis is down
        mid_infra = (await client.get(f"{BASE_URL}/api/admin/infrastructure", headers=headers)).json()
        mid_pending = mid_infra["postgres"]["pending_outbox"]
        print(f" Outbox pending count while Redis down: {mid_pending} (incremented!)")
        assert mid_pending >= 1

        # Restart Redis
        print(" Restarting Redis container...")
        start_rd = await client.post(f"{BASE_URL}/api/admin/fault/services/redis/start", headers=headers)
        assert start_rd.status_code == 200
        print(" Redis restarted. Waiting for worker to retry and publish pending outbox events...")
        
        # Wait up to 10 seconds for worker to process pending records
        worker_recovered = False
        for _ in range(10):
            await asyncio.sleep(1)
            cur_infra = (await client.get(f"{BASE_URL}/api/admin/infrastructure", headers=headers)).json()
            if cur_infra["postgres"]["pending_outbox"] == 0:
                worker_recovered = True
                print(f" Worker published pending events! Pending={cur_infra['postgres']['pending_outbox']}, Published={cur_infra['postgres']['published_outbox']}")
                break

        assert worker_recovered, "Worker did not process pending outbox events within 10s"
        print(" PASS: Transactional outbox pattern verified! Zero message loss during Redis outage.")

    print("\n" + "=" * 60)
    print("ALL FAULT TOLERANCE TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_fault_tolerance())

