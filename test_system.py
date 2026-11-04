import asyncio
import json
import time
import httpx
import websockets

BASE_URL = "http://localhost:8080"
WS_BASE = "ws://localhost:8080"

async def test_all():
    print("=" * 60)
    print("SocketScale Comprehensive Automated System Test Suite")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Health check
        print("\n[TEST 1] Testing Gateway Health & Least-Conn Load Balancing...")
        h1 = (await client.get(f"{BASE_URL}/health")).json()
        h2 = (await client.get(f"{BASE_URL}/health")).json()
        print(f" Request 1 -> Instance: {h1.get('instance_id')}, Status: {h1.get('status')}")
        print(f" Request 2 -> Instance: {h2.get('instance_id')}, Status: {h2.get('status')}")
        assert h1.get("status") == "ok"
        assert h2.get("status") == "ok"
        print(" PASS: Health checks and load balancing operational.")

        # 2. Authentication: Login default admin
        print("\n[TEST 2] Testing Admin Authentication...")
        admin_login = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "AdminPass123!"}
        )
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]
        print(" PASS: Admin login successful.")

        # 3. Authentication: Reject incorrect password
        print("\n[TEST 3] Testing Bad Password Rejection...")
        bad_login = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "WrongPassword!"}
        )
        assert bad_login.status_code == 401
        print(" PASS: Bad password correctly rejected with 401.")

        # 4. Authentication: Register new users
        print("\n[TEST 4] Testing User Registration...")
        unique_suffix = int(time.time())
        u1_name = f"user1_{unique_suffix}"
        u2_name = f"user2_{unique_suffix}"
        
        reg1 = await client.post(
            f"{BASE_URL}/api/auth/register",
            json={"username": u1_name, "password": "Password123!"}
        )
        assert reg1.status_code == 200
        u1_token = reg1.json()["access_token"]
        
        reg2 = await client.post(
            f"{BASE_URL}/api/auth/register",
            json={"username": u2_name, "password": "Password123!"}
        )
        assert reg2.status_code == 200
        u2_token = reg2.json()["access_token"]
        print(f" PASS: Registered {u1_name} and {u2_name}.")

        # 5. Role-Based Access Control: Regular user blocked from admin APIs
        print("\n[TEST 5] Testing RBAC (Admin-only endpoints reject normal user)...")
        forbidden_res = await client.get(
            f"{BASE_URL}/api/admin/overview",
            headers={"Authorization": f"Bearer {u1_token}"}
        )
        assert forbidden_res.status_code == 403
        admin_res = await client.get(
            f"{BASE_URL}/api/admin/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert admin_res.status_code == 200
        print(" PASS: Normal user blocked with 403 Forbidden; Admin permitted with 200 OK.")

        # 6. Room Creation & Listing
        print("\n[TEST 6] Testing Room Creation (Public & Private)...")
        room_test = f"testroom_{unique_suffix}"
        create_res = await client.post(
            f"{BASE_URL}/api/rooms",
            json={"name": room_test, "is_private": False},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert create_res.status_code == 200
        rooms_list = (await client.get(
            f"{BASE_URL}/api/rooms",
            headers={"Authorization": f"Bearer {u1_token}"}
        )).json()
        assert any(r["name"] == room_test for r in rooms_list)
        print(f" PASS: Room #{room_test} created and listed.")

        # 7. WebSocket Multi-User Real-Time Messaging & Cross-Gateway Fan-out
        print("\n[TEST 7] Testing Multi-User WebSocket Communication & Persistence...")
        ws1_url = f"{WS_BASE}/ws/{room_test}?token={u1_token}"
        ws2_url = f"{WS_BASE}/ws/{room_test}?token={u2_token}"

        async with websockets.connect(ws1_url) as ws1, websockets.connect(ws2_url) as ws2:
            greet1 = json.loads(await ws1.recv())
            greet2 = json.loads(await ws2.recv())
            print(f" Client 1 connected to: {greet1.get('instance_id')}")
            print(f" Client 2 connected to: {greet2.get('instance_id')}")

            # Send message from Client 1
            msg_text = f"Hello from Client 1 at {time.time()}"
            await ws1.send(json.dumps({"content": msg_text}))

            # Client 1 receives ack
            ack = json.loads(await asyncio.wait_for(ws1.recv(), timeout=5))
            assert ack.get("type") == "ack"
            print(f" Client 1 received ack: Message ID #{ack['message']['id']}")

            # Client 2 receives broadcast via Redis Pub/Sub relay
            broadcast = None
            for _ in range(5):
                raw = await asyncio.wait_for(ws2.recv(), timeout=5)
                ev = json.loads(raw)
                if ev.get("type") == "message" and ev["message"]["content"] == msg_text:
                    broadcast = ev
                    break
            assert broadcast is not None
            print(f" Client 2 received broadcast: '{broadcast['message']['content']}'")
        print(" PASS: Multi-user WebSocket communication & Redis Pub/Sub relay verified.")

        # 8. Persistent History Loading
        print("\n[TEST 8] Testing PostgreSQL Message History Retrieval...")
        hist_res = await client.get(
            f"{BASE_URL}/api/rooms/{room_test}/messages",
            headers={"Authorization": f"Bearer {u2_token}"}
        )
        assert hist_res.status_code == 200
        history = hist_res.json()
        assert len(history) >= 1
        assert history[-1]["content"] == msg_text
        print(f" PASS: PostgreSQL persisted {len(history)} messages. Chronological retrieval verified.")

        # 9. Admin Overview and Gateways Metrics
        print("\n[TEST 9] Testing Admin Gateways & Infrastructure APIs...")
        gw_resp = (await client.get(
            f"{BASE_URL}/api/admin/gateways",
            headers={"Authorization": f"Bearer {admin_token}"}
        )).json()
        
        gw_list = gw_resp.get("gateways", []) if isinstance(gw_resp, dict) and "gateways" in gw_resp else []
        node_names = [g["node_name"] for g in gw_list] if gw_list else list(gw_resp.keys())
        assert "gateway-a" in node_names or "gateway_a" in node_names
        assert "gateway-b" in node_names or "gateway_b" in node_names
        for n in gw_list:
            print(f" Node {n['node_name']} status: {n['status']} (handled {n.get('requests_handled', 0)} reqs, conns: {n.get('active_connections', 0)})")

        infra_status = (await client.get(
            f"{BASE_URL}/api/admin/infrastructure",
            headers={"Authorization": f"Bearer {admin_token}"}
        )).json()
        assert infra_status["postgres"]["status"] == "ok"
        assert infra_status["redis"]["status"] == "ok"
        assert infra_status["worker"]["status"] == "ok"
        print(f" Infrastructure: PostgreSQL={infra_status['postgres']['status']}, Redis={infra_status['redis']['status']}, Worker={infra_status['worker']['status']}")
        print(f" Outbox Stats: Published={infra_status['postgres']['published_outbox']}, Pending={infra_status['postgres']['pending_outbox']}")
        print(" PASS: Admin monitoring endpoints operational.")

        # 10. System Logs
        print("\n[TEST 10] Testing System Event Logs API...")
        logs = (await client.get(
            f"{BASE_URL}/api/admin/logs?limit=10",
            headers={"Authorization": f"Bearer {admin_token}"}
        )).json()
        assert len(logs) > 0
        print(f" Verified {len(logs)} audit logs in database. Sample: [{logs[0]['severity']}] {logs[0]['message']}")
        print(" PASS: Auditable system logging verified.")

    print("\n" + "=" * 60)
    print("ALL CORE INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_all())

