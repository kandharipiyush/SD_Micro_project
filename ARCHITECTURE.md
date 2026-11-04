# SocketScale — Distributed Architecture & System Design

This document details the architectural design, component responsibilities, message workflows, and fault recovery mechanisms of **SocketScale**.

---

## 1. High-Level Architecture Topology

```
                  [ Web Browsers / Benchmark Clients ]
                                    │
                                    ▼
                ┌───────────────────────────────────────┐
                │        Nginx 1.27 Ingress Router      │
                │  (Port 8080 | least_conn | Failover)  │
                └───────────────────┬───────────────────┘
                                    │
            ┌───────────────────────┴───────────────────────┐
            ▼                                               ▼
┌───────────────────────┐                       ┌───────────────────────┐
│   FastAPI Gateway A   │                       │   FastAPI Gateway B   │
│ (Instance: gateway-a) │                       │ (Instance: gateway-b) │
└───────────┬───────────┘                       └───────────┬───────────┘
            │                                               │
            │           ┌───────────────────────┐           │
            ├───────────►   PostgreSQL 16 DB    ◄───────────┤
            │           │  (Users/Messages/     │           │
            │           │   Outbox/Benchmarks)  │           │
            │           └───────────▲───────────┘           │
            │                       │ (Polls unpublished)   │
            │           ┌───────────┴───────────┐           │
            │           │ Outbox Worker Process │           │
            │           └───────────┬───────────┘           │
            │                       │ (Publishes event)     │
            │           ┌───────────▼───────────┐           │
            └───────────►   Redis 7 Pub/Sub     ◄───────────┘
              (Subscribes to room:* channels)
```

---

## 2. Component Responsibilities

### 2.1. Nginx Reverse Proxy & Load Balancer (`socketscale-nginx`)
- **Port Ingress**: Exposes single external port `8080`.
- **Load Balancing**: Distributes incoming HTTP and WebSocket connections using `least_conn` algorithm.
- **Failover Engine**: Configured with `proxy_next_upstream error timeout invalid_header http_502 http_503 http_504` and `proxy_connect_timeout 2s`. When one gateway crashes, connections and HTTP calls are transparently directed to the healthy peer within seconds.
- **Path Routing**:
  - `/` → Serves React static build via frontend web server.
  - `/api/` → Proxied to gateway nodes.
  - `/ws/` → Upgraded to WebSocket and proxied to gateway nodes.
  - `/docs` & `/openapi.json` → Proxied to FastAPI gateway Swagger UI.
  - `/api/recovery/` → Routed directly to the local Fault Agent for stack restoration.

### 2.2. Dual Gateway Instances (`socketscale-gateway-a`, `socketscale-gateway-b`)
- Independent stateless FastAPI servers running on port 8000.
- Handle JWT authentication and role validation.
- Accept real-time WebSocket client connections.
- Save inbound chat messages and outbox entries within an **atomic database transaction**.
- Acknowledge message receipt immediately to the sender (`type: "ack"`).
- Maintain an active Redis Pub/Sub subscription to `room:*` and broadcast incoming events to local room sockets.

### 2.3. PostgreSQL Relational Persistence (`socketscale-postgres`)
- Persistent relational database storage mounted to a named Docker volume (`pgdata`).
- Tables:
  - `users`: Registered accounts, roles (`admin`/`user`), and Argon2 password hashes.
  - `rooms`: Public and private chat rooms with creator references.
  - `room_members`: Access control list for private room membership.
  - `messages`: Chronologically ordered persistent chat history.
  - `message_outbox`: Transactional outbox records with publish status, timestamps, retry counter, and error logs.
  - `benchmark_runs`: Saved high-concurrency load-testing reports.
  - `system_logs`: Audit trail for service state changes, fault actions, and worker events.

### 2.4. Autonomous Outbox Worker (`socketscale-worker`)
- Independent Python daemon running in its own container.
- Constantly queries PostgreSQL for unpublished outbox entries:
  ```sql
  SELECT * FROM message_outbox WHERE published = FALSE ORDER BY id LIMIT 100;
  ```
- Publishes each record's payload to the corresponding Redis channel (`room:<name>`).
- Upon successful publish:
  - Updates `published = TRUE` and records `published_at` timestamp.
  - Increments successful publish counter in Redis.
- If Redis is unavailable:
  - Increments `retry_count` and records error details in `last_error`.
  - Backs off and resumes immediately once Redis reconnects.
- Emits periodic heartbeat into Redis (`socketscale:worker:heartbeat`) for health telemetry.

### 2.5. Redis Pub/Sub Broker (`socketscale-redis`)
- Ephemeral in-memory messaging broker.
- Powers the real-time cross-gateway fan-out fabric.
- Guarantees sub-millisecond dispatch of chat messages between Gateway A and Gateway B.

### 2.6. Local Fault Agent (`socketscale-fault-agent`)
- Isolated controller connected to the local Docker socket.
- Exposes administrative endpoints to stop, start, and restart specific application containers.
- Enforces container name allowlists preventing arbitrary command execution.
- Employs asynchronous container termination to allow invoking gateways to cleanly return HTTP acknowledgments before shutting down.

---

## 3. End-to-End Data & Event Flows

### 3.1. Message Ingestion & Transactional Outbox Flow
```
User Client (Gateway A)
         │  1. Sends WebSocket message: {"content": "Hello!"}
         ▼
FastAPI Gateway A
         │  2. Begins DB Transaction
         ├────────────────────────────────────────┐
         ▼                                        ▼
INSERT INTO messages (...)             INSERT INTO message_outbox (...)
         │                                        │
         └───────────────────┬────────────────────┘
                             │  3. COMMIT Transaction
                             ▼
                    PostgreSQL Storage (Durable)
                             │
                             ▼  4. Sends instant ACK to User: {"type": "ack", "id": 42}
```

### 3.2. Background Outbox Dispatch & Cross-Gateway Relay
```
Outbox Worker
     │  1. SELECT * FROM message_outbox WHERE published = FALSE
     ▼
PostgreSQL
     │  2. Returns pending record #42
     ▼
Outbox Worker
     │  3. redis.publish("room:general", payload)
     ▼
Redis Pub/Sub
     │
     ├────────────────────────────────────┐
     ▼                                    ▼
FastAPI Gateway A                   FastAPI Gateway B
  (Listening on room:general)         (Listening on room:general)
     │                                    │
     ▼                                    ▼
Local Clients on Gateway A          Local Clients on Gateway B
{"type": "message", "id": 42}       {"type": "message", "id": 42}
```

---

## 4. Failure Recovery & Resilience Guarantees

| Failure Scenario | Immediate System Impact | Recovery Mechanism | Data Loss? |
|---|---|---|---|
| **Gateway A Crashes** | Active WebSockets on A disconnect. | Nginx automatically diverts all new connections and HTTP traffic to Gateway B within 2 seconds. Reconnecting clients fetch full room history from PostgreSQL. | **Zero message loss** |
| **Redis Outage** | Instant real-time fan-out across nodes pauses. | Gateways continue accepting and writing messages to PostgreSQL and Outbox. Senders receive ACKs. When Redis recovers, the Outbox Worker automatically flushes queued events to Redis. | **Zero message loss** |
| **Worker Crashes** | Outbox messages queue up in PostgreSQL. | Restarting the worker causes it to pick up where it left off, reading all unpublished records ordered by ID and flushing them to Redis. | **Zero message loss** |
| **PostgreSQL Outage** | New message persistence temporarily fails; health reports `degraded`. | Gateways return error responses informing clients to retry. Existing connections stay alive. System resumes full persistence once PostgreSQL restarts. | **Existing data preserved in Docker volume** |

