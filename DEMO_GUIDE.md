# SocketScale — Faculty Demonstration Guide & Walkthrough

This guide provides the exact demonstration sequence to showcase **SocketScale** to college faculty and project evaluators. It covers horizontal load balancing, dynamic elastic node scaling ($N$ gateways), real-time cross-gateway synchronization, transactional outbox durability, fault injection, and dynamic performance benchmarking.

---

## Pre-Demo Checklist

1. Make sure Docker Desktop is running on Windows.
2. In PowerShell, navigate to `SocketScale` directory:
   ```powershell
   cd "c:\Users\Lenovo\Downloads\SocketScale_Project_Completed (1)\SocketScale"
   ```
3. Start the application:
   ```powershell
   docker compose up -d
   ```
4. Verify all 9 core services are active:
   ```powershell
   docker compose ps
   ```
5. Open two separate browser windows (or one standard and one incognito window):
   - **Window 1 (Admin)**: `http://localhost:8080`
   - **Window 2 (User)**: `http://localhost:8080`
   - **API Docs (Swagger UI)**: `http://localhost:8080/docs`

---

## Demonstration Sequence (Step-by-Step)

### Step 1: User Authentication & Role-Based Access Control (RBAC)
1. In **Window 1**, log in with the administrator account:
   - **Username**: `admin`
   - **Password**: `AdminPass123!`
   - *Observation*: Notice the Admin UI opens with full access to **Admin Overview**, **Elastic Gateways**, **Infrastructure**, **Fault Tolerance Lab**, **Benchmarks & Analytics**, and **System Logs**.
2. In **Window 2**, switch to the **Create Account** tab and register a new user:
   - **Username**: `student1`
   - **Password**: `StudentPass123!`
   - *Observation*: `student1` is immediately logged in with the `user` role. Notice regular users only see the **Live Chat** interface. Administrative tabs are protected by JWT claims and role verification.

---

### Step 2: Real-Time Multi-User Chat & Redis Fan-Out
1. In **Window 1 (admin)**, click **User Chat** in the sidebar. Select the `#general` room.
   - Notice the connection badge in the top right shows: `WS: connected via gateway-a` (or `b` / `c`).
2. In **Window 2 (student1)**, open `#general`.
   - Notice its connection badge connects to another gateway node (Nginx distributes incoming WebSocket connections using `least_conn`).
3. Type a message in Window 1 and send it:
   - *"Hello from Gateway node A!"*
4. *Observation*: The message appears **instantly** in Window 2!
   - **Faculty Explanation**: *"Even though the two users are connected through separate gateway containers, the message was written to PostgreSQL, dispatched to Redis Pub/Sub, and fanned out in sub-millisecond real time to the second gateway."*

---

### Step 3: Dynamic Elastic Scaling — Adding & Deleting Gateway Nodes ($N$ Nodes)
This demonstrates high-availability dynamic clustering:

1. In **Window 1**, navigate to **Gateway Nodes**.
   - Show the current list of active gateways: `gateway-a`, `gateway-b`, `gateway-c`.
2. Click the blue **"+ Scale Out (Add Gateway Node)"** button.
   - *Observation*: A new container `gateway-d` is spawned dynamically by the Docker controller.
   - The controller automatically writes the new upstream into Nginx's configuration (`upstreams.conf`) and issues a zero-downtime hot reload: `nginx -s reload`.
3. In PowerShell, show that traffic immediately balances across all 4 nodes:
   ```powershell
   python -c "import httpx; [print(httpx.get('http://localhost:8080/health').json()['instance_id']) for _ in range(8)]"
   ```
   *Output*: You will see requests distributed across `gateway-a`, `gateway-b`, `gateway-c`, and `gateway-d`!
4. Show that any node can be decommissioned:
   - In the **Gateway Nodes** table, click the red **Delete Node** button next to `gateway-d`.
   - *Observation*: The container is cleanly stopped, removed, Nginx upstreams are updated, and traffic safely scales in back to 3 nodes without dropping connections.

---

### Step 4: Fault Tolerance Lab — Simulating Gateway Crash & Failover
1. In **Window 1**, navigate to **Fault Tolerance Lab**.
2. Locate **Gateway A** and click the red **STOP** button.
   - Confirm the action in the prompt.
   - The status updates to **stopped / down** in real time.
3. In **Window 2 (student1)**, send a message or refresh:
   - Notice that Nginx immediately routes the traffic to **Gateway B** or **Gateway C** with sub-2s failover!
   - Active users can reconnect immediately and all previous message history is intact from PostgreSQL.
4. Return to **Fault Tolerance Lab** and click **START** on **Gateway A**:
   - The node starts up, becomes healthy, and Nginx automatically re-includes it in the active upstream pool.

---

### Step 5: Transactional Outbox Under Redis Outage (Zero Data Loss)
This is the core academic system-design demonstration proving data consistency.

1. In **Window 1**, navigate to **Infrastructure**.
   - Note the **Pending Outbox Queue** is currently `0`.
2. Navigate to **Fault Tolerance Lab**. Click **STOP** next to **Redis Pub/Sub**.
3. In **Window 2 (Chat)**, send a message:
   - *"Critical message sent while Redis is offline!"*
4. Notice:
   - The user receives an instant **ACK** with a persistent message ID!
5. In **Window 1**, refresh the **Infrastructure** page:
   - Show that **Pending Outbox Queue** has incremented to `1`!
   - **Faculty Explanation**: *"Because we use the Transactional Outbox pattern, the message is durably written to PostgreSQL in an atomic database transaction. Redis being down does not lose the message!"*
6. In **Fault Tolerance Lab**, click **START** next to **Redis Pub/Sub**.
7. Wait 2 seconds and check **Infrastructure**:
   - The **Pending Outbox Queue** drops back to `0`, and the **Published Outbox Events** increments!
   - The background worker autonomously caught up and published the message to Redis with zero data loss!

---

### Step 6: Interactive Dynamic Benchmarking & Analytics
1. In **Window 1**, navigate to **Benchmarks & Analytics**.
2. Under **Run Live Benchmark**:
   - Enter **Concurrent Clients**: `20` (or any custom number up to 100).
   - Enter **Messages / Client**: `10` (or any custom number up to 50).
   - Target Room: `benchmark-live`.
3. Click **"Run Benchmark Now"**:
   - Watch the live execution in the cluster.
   - In under 2 seconds, the scorecard updates with:
     - **Throughput**: ~130–180 msg/sec
     - **P95 Latency**: ~10–25 ms
     - **Duration**: ~0.8–1.5 seconds
     - **Gateway Distribution**: Exact message counts distributed across Gateway A, B, and C.
4. Show the 6 visual interactive charts (Recharts):
   1. *Message Throughput Comparison (msgs/sec)*
   2. *Average Latency Comparison (ms)*
   3. *P95 Tail Latency Comparison (ms)*
   4. *Successful vs Failed Messages*
   5. *Concurrent Clients vs Throughput Curve*
   6. *Concurrent Clients vs Latency Curve*
5. Click the **Export CSV** and **Export JSON** buttons in the header to demonstrate real-time metric export.
6. *(Optional CLI run)* In PowerShell, run the CLI benchmark tool:
   ```powershell
   python benchmark/benchmark.py --clients 15 --messages 10 --save
   ```
   Refresh the web page to show the CLI run immediately appended to the PostgreSQL history!

---

### Step 7: System Operational Event Logs
1. In **Window 1**, navigate to **System Logs**.
2. Show the auditable log table recording:
   - Service lifecycle events (`SERVICE_LIFECYCLE`)
   - Cluster scaling actions (`CLUSTER_SCALE`)
   - Fault injection actions (`FAULT_INJECTION`)
   - Outbox worker retry and recovery events (`OUTBOX_WORKER`)
   - Benchmark completions (`BENCHMARK`)
3. Filter by **Component** or **Event Type** to show real database query filtering.

---

### Step 8: Clean Stack Shutdown
Show the faculty how easy it is to manage via PowerShell:
```powershell
# Stop all services cleanly
docker compose down
```

---

## Key Viva & Academic Questions to Answer

**Q1: How does Nginx balance WebSocket connections?**
- Nginx uses the `least_conn` directive, which assigns incoming WebSocket handshakes to the gateway node with the fewest active connections. It also has `proxy_next_upstream` configured with a 2-second timeout so that if any node fails, incoming connections fail over to healthy nodes without user-visible errors.

**Q2: What is the dual-write problem and how does the Transactional Outbox solve it?**
- In traditional setups, an application writes to a database and then attempts to publish to a message broker (Redis/Kafka). If the network drops or Redis crashes between the two calls, the message is saved in PostgreSQL but never broadcast to other users (inconsistency). With the Transactional Outbox pattern, the message and the outbox event are saved in the **same atomic database transaction**. A dedicated background worker polls unpublished outbox records and retries them until Redis acknowledges receipt.

**Q3: How is dynamic horizontal scaling achieved without restarting Nginx?**
- When a new gateway is added via the dashboard or API, the Docker SDK controller provisions the container on `socketscale_default`, adds the container's hostname to `/app/nginx/upstreams.conf`, and executes `nginx -s reload` inside the Nginx container. Nginx spawns new worker processes with the updated upstream pool while allowing existing workers to drain active connections, achieving zero downtime.
