# SocketScale — Backend-Only Mini Project

Focused on the stated requirements: **full code implementation, fault-injection tests, and benchmarks**. No frontend is included.

## Components
- FastAPI REST API and WebSocket endpoint
- JWT authentication and Argon2 password hashing
- PostgreSQL persistence for users/messages
- Redis Pub/Sub for cross-instance message relay
- Two gateway replicas
- Nginx `least_conn` load balancing
- Interactive WebSocket client, benchmark script, fault-injection PowerShell script

## Start (Docker Desktop required)
From the extracted project directory:
```powershell
docker compose up --build -d
docker compose ps
```
Base URL: `http://localhost:8080`
Health: `http://localhost:8080/health`
Metrics: `http://localhost:8080/api/metrics`
Swagger: `http://localhost:8080/docs`

## Register/login
```powershell
$body = @{username="demo_user"; password="DemoPass123!"} | ConvertTo-Json
$auth = Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/auth/register -ContentType "application/json" -Body $body
$token = $auth.access_token
```
If the account exists, use `/api/auth/login` instead. Use a unique username for registration.
History:
```powershell
Invoke-RestMethod -Uri "http://localhost:8080/api/rooms/general/messages?token=$token"
```
Gateway identification:
```powershell
Invoke-RestMethod -Uri "http://localhost:8080/api/whoami?token=$token"
```

## Test real-time messaging
Install Python 3.11+:
```powershell
python -m pip install -r tools/requirements.txt
```
Run clients in two terminals using different user tokens:
```powershell
python tools/ws_client.py --token YOUR_JWT_TOKEN --room general
```
Type messages. The connection greeting displays the gateway instance ID. Verify two clients are connected to different instances before claiming cross-gateway Pub/Sub.

## Benchmark
```powershell
python tools/benchmark.py --token YOUR_JWT_TOKEN --room bench --clients 10 --messages 20
```
Creates `benchmark_results.json` with connection success, acknowledgements, throughput, mean/median/P95 latency, gateway IDs, and errors. Repeat with different client counts and record real results; do not invent performance figures.

## Fault injection
```powershell
.\tests\fault_injection.ps1
```
This temporarily stops and restarts gateway-a and Redis. Record HTTP status/body, whether new connections work, existing WebSocket behavior, logs, and recovery time. A command completing is not proof of a passed test.
```powershell
docker compose logs --tail 80 gateway-a gateway-b nginx redis
```

## Endpoints
- `POST /api/auth/register` — `{ "username": "...", "password": "..." }`
- `POST /api/auth/login`
- `GET /api/whoami?token=JWT`
- `GET /api/rooms/{room}/messages?token=JWT&limit=50`
- `GET /api/metrics`
- `GET /health`
- `WS /ws?token=JWT&room=general`, send `{"content":"Hello"}`

## Limitations
Educational local prototype. No TLS/WSS, rate limiting, production secrets management, or durable event queue. WebSocket JWT is passed in the query string for demo simplicity and may be logged. Redis Pub/Sub is not durable. Metrics are per replica, not aggregated. Benchmark is local send-to-self-ack timing, not a formal capacity guarantee.
