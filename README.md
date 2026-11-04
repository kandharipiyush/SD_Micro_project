# SocketScale — Fault-Tolerant Real-Time Pub/Sub WebSocket Gateway with Persistent Message History

**SocketScale** is a horizontally scalable, fault-tolerant, distributed messaging platform demonstrating modern system design principles. It features a 3-node load-balanced FastAPI WebSocket gateway cluster (`Gateway A`, `Gateway B`, `Gateway C`) behind Nginx, Redis Pub/Sub for inter-gateway real-time synchronization, PostgreSQL persistent storage using the Transactional Outbox pattern, an autonomous background delivery worker, a Docker-isolated Fault Tolerance Lab, and an interactive dynamic benchmarking engine.

---

## 1. Key Features

- **Modern SaaS Web Dashboard**: Clean React + Vite interface with real-time user chat, admin overview, 3-gateway telemetry, infrastructure telemetry, interactive fault injection, and dynamic benchmark analytics.
- **3-Node Load-Balanced Gateway Cluster**: Independent FastAPI instances (`Gateway A`, `Gateway B`, and `Gateway C`) managed via Nginx with `least_conn` load balancing and sub-second automatic failover.
- **Cross-Gateway Real-Time Fan-Out**: Real-time Redis Pub/Sub channels synchronize messages across separate gateway instances, ensuring clients connected to different gateways can seamlessly exchange messages.
- **Transactional Outbox Persistence**: Messages are saved in PostgreSQL alongside an outbox event in the same atomic database transaction. An autonomous worker polls and publishes to Redis with retry capabilities, eliminating message loss during broker outages.
- **Interactive Dynamic Benchmarking**: In addition to the CLI, an interactive benchmark runner is integrated directly into the web UI. Users can dynamically input any number of concurrent clients and messages/requests per client, launch the test across the cluster, and watch the system measure throughput, percentiles (Mean, Median, P95, Max), and gateway distributions in real time.
- **Fault Tolerance Lab**: Controlled Docker service manipulation (Stop/Start/Restart for Gateway A, Gateway B, Gateway C, All Gateways, Redis, PostgreSQL, Worker, Nginx, Frontend, and entire stack recovery) with safety confirmation modals.

---

## 2. Quick Start (Windows PowerShell)

```powershell
# 1. Open Windows PowerShell in the SocketScale directory
cd "c:\Users\Lenovo\Downloads\SocketScale_Project_Completed (1)\SocketScale"

# 2. Initialize environment configuration
Copy-Item .env.example .env

# 3. Build and launch all 9 services in background
docker compose up --build -d

# 4. Verify all container services are healthy and running
docker compose ps
```

### Access URLs
- **Web Application**: [http://localhost:8080](http://localhost:8080)
- **Interactive OpenAPI Documentation (Swagger)**: [http://localhost:8080/docs](http://localhost:8080/docs)
- **Cluster Gateway Health Probe**: [http://localhost:8080/health](http://localhost:8080/health)

### Default Demonstration Accounts
| Role | Username | Password | Purpose |
|---|---|---|---|
| **Administrator** | `admin` | `AdminPass123!` | Full access to Admin Overview, Gateway Metrics, Fault Lab, Benchmarks & Logs |
| **User 1** | `piyush` | `UserPass123!` | Live chat client 1 |
| **User 2** | `mahek` | `UserPass123!` | Live chat client 2 |
