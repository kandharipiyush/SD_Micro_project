import os
import json
import time
import asyncio
import io
import csv
import statistics
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from jose import jwt, JWTError
from sqlalchemy import select, desc, func
from redis.asyncio import Redis, ConnectionError
import httpx
import websockets

from .db import (
    Session, User, Room, RoomMember, Message, Outbox, BenchmarkRun, SystemLog,
    pwd, init_db, record_log
)

app = FastAPI(
    title="SocketScale API",
    description="Fault-Tolerant Elastic Real-Time Pub/Sub WebSocket Gateway with Persistent Message History",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

SECRET = os.getenv("JWT_SECRET", "local-demo-secret-change-me")
INSTANCE = os.getenv("INSTANCE_ID", "gateway")
FAULT_ADMIN_TOKEN = os.getenv("FAULT_ADMIN_TOKEN", "local-fault-token-change-me")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

redis = Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1.0,
    socket_timeout=1.0,
    retry_on_timeout=False
)
sockets: dict[str, set[WebSocket]] = {}
startup_time = time.time()
request_counter = 0

# Request counting middleware
@app.middleware("http")
async def count_requests(request: Request, call_next):
    global request_counter
    request_counter += 1
    response = await call_next(request)
    return response

# Pydantic Schemas
class Credentials(BaseModel):
    username: str
    password: str

class Registration(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=6, max_length=100)

class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    is_private: bool = False

class BenchmarkTrigger(BaseModel):
    clients: int = Field(default=20, ge=1, le=100)
    messages_per_client: int = Field(default=10, ge=1, le=50)
    room: str = Field(default="benchmark-live")

class BenchmarkReport(BaseModel):
    name: str = Field(default="Benchmark", max_length=100)
    clients: int = Field(ge=1, le=500)
    messages_per_client: int = Field(ge=1, le=1000)
    results: dict

def create_access_token(u: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": u.username, "role": u.role, "iat": now, "exp": now + timedelta(hours=24)},
        SECRET,
        algorithm="HS256"
    )

async def user_auth(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    try:
        claims = jwt.decode(authorization[7:], SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(401, "Invalid token")
    async with Session() as s:
        u = await s.scalar(select(User).where(User.username == claims["sub"]))
        if not u:
            raise HTTPException(401, "Unknown user")
        return u

async def admin_auth(u: User = Depends(user_auth)) -> User:
    if u.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return u

async def admin_claims(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    try:
        claims = jwt.decode(authorization[7:], SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(401, "Invalid token")
    if claims.get("role") != "admin":
        raise HTTPException(403, "Administrator access required")
    return claims

def serialize_message(m: Message) -> dict:
    return {
        "id": m.id,
        "room": m.room,
        "sender": m.sender,
        "content": m.content,
        "created_at": m.created_at.isoformat() + "Z"
    }

# Background Redis relay subscriber
async def redis_relay():
    reconnect_delay = 2.0
    while True:
        ps = None
        try:
            ps = redis.pubsub()
            await ps.psubscribe("room:*")
            reconnect_delay = 2.0  # Reset delay on successful subscription
            async for ev in ps.listen():
                if ev.get("type") != "pmessage":
                    continue
                try:
                    data = json.loads(ev["data"])
                    room_name = data.get("room")
                    if not room_name or room_name not in sockets:
                        continue
                    
                    target_sockets = list(sockets.get(room_name, set()))
                    for ws in target_sockets:
                        try:
                            await ws.send_json({"type": "message", "message": data})
                        except Exception:
                            sockets[room_name].discard(ws)
                except Exception:
                    continue
        except asyncio.CancelledError:
            if ps:
                await ps.close()
            break
        except Exception:
            if ps:
                try:
                    await ps.close()
                except Exception:
                    pass
            # Backoff to avoid blocking threads on DNS lookups during broker outage
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, 10.0)

@app.on_event("startup")
async def on_startup():
    await init_db()
    asyncio.create_task(redis_relay())
    await record_log(
        event_type="SERVICE_LIFECYCLE",
        severity="INFO",
        component=INSTANCE,
        message=f"{INSTANCE.upper()} active in cluster"
    )

# Public Health Check
@app.get("/health")
async def health_check():
    db_status = "ok"
    redis_status = "ok"
    try:
        async with Session() as s:
            await s.execute(select(1))
    except Exception:
        db_status = "unavailable"
    
    try:
        await asyncio.wait_for(redis.ping(), timeout=0.8)
    except Exception:
        redis_status = "unavailable"

    uptime_sec = round(time.time() - startup_time, 1)
    active_conns = sum(len(v) for v in sockets.values())
    overall = "ok" if (db_status == "ok" and redis_status == "ok") else "degraded"

    return {
        "status": overall,
        "instance_id": INSTANCE,
        "uptime_seconds": uptime_sec,
        "requests_handled": request_counter,
        "active_connections": active_conns,
        "postgres": db_status,
        "redis": redis_status
    }

# Authentication APIs
@app.post("/api/auth/register")
async def register(b: Registration):
    async with Session() as s:
        existing = await s.scalar(select(User).where(User.username == b.username))
        if existing:
            raise HTTPException(409, "Username already exists")
        u = User(
            username=b.username,
            password_hash=pwd.hash(b.password),
            role="user"
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        await record_log("AUTH", "INFO", "auth", f"User registered: {b.username}")
        return {
            "access_token": create_access_token(u),
            "username": u.username,
            "role": u.role
        }

@app.post("/api/auth/login")
async def login(b: Credentials):
    async with Session() as s:
        u = await s.scalar(select(User).where(User.username == b.username))
        if not u or not pwd.verify(b.password, u.password_hash):
            raise HTTPException(401, "Incorrect username or password")
        return {
            "access_token": create_access_token(u),
            "username": u.username,
            "role": u.role
        }

@app.get("/api/me")
async def get_me(u: User = Depends(user_auth)):
    return {"username": u.username, "role": u.role}

# Room APIs
@app.get("/api/rooms")
async def list_rooms(u: User = Depends(user_auth)):
    async with Session() as s:
        all_rooms = (await s.scalars(select(Room).order_by(Room.name))).all()
        memberships = set((await s.scalars(
            select(RoomMember.room_name).where(RoomMember.username == u.username)
        )).all())

        visible = []
        for r in all_rooms:
            if not r.is_private or r.created_by == u.username or u.role == "admin" or r.name in memberships:
                visible.append({
                    "name": r.name,
                    "is_private": r.is_private,
                    "created_by": r.created_by,
                    "created_at": r.created_at.isoformat() + "Z"
                })
        return visible

@app.post("/api/rooms")
async def create_room(b: RoomCreate, u: User = Depends(user_auth)):
    name = b.name.strip().lower()
    if not name or len(name) > 40 or not name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "Room name must be 1-40 alphanumeric characters, hyphens or underscores")
    
    async with Session() as s:
        existing = await s.scalar(select(Room).where(Room.name == name))
        if existing:
            raise HTTPException(409, "Room already exists")
        
        new_room = Room(name=name, is_private=b.is_private, created_by=u.username)
        s.add(new_room)
        s.add(RoomMember(room_name=name, username=u.username))
        await s.commit()

        await record_log(
            "ROOM",
            "INFO",
            "chat",
            f"Room '{name}' created by {u.username} (private={b.is_private})"
        )
        return {
            "name": name,
            "is_private": b.is_private,
            "created_by": u.username
        }

@app.post("/api/rooms/{room}/join")
async def join_room(room: str, u: User = Depends(user_auth)):
    room = room.strip().lower()
    async with Session() as s:
        r = await s.scalar(select(Room).where(Room.name == room))
        if not r:
            raise HTTPException(404, "Room not found")
        existing_m = await s.scalar(
            select(RoomMember).where(RoomMember.room_name == room, RoomMember.username == u.username)
        )
        if not existing_m:
            s.add(RoomMember(room_name=room, username=u.username))
            await s.commit()
        return {"status": "joined", "room": room}

@app.get("/api/rooms/{room}/messages")
async def room_history(room: str, limit: int = 50, u: User = Depends(user_auth)):
    room = room.strip().lower()
    async with Session() as s:
        r = await s.scalar(select(Room).where(Room.name == room))
        if not r:
            raise HTTPException(404, "Room not found")
        
        if r.is_private and r.created_by != u.username and u.role != "admin":
            is_member = await s.scalar(
                select(RoomMember).where(RoomMember.room_name == room, RoomMember.username == u.username)
            )
            if not is_member:
                raise HTTPException(403, "Access denied: private room membership required")

        capped_limit = max(1, min(limit, 100))
        rows = (await s.scalars(
            select(Message)
            .where(Message.room == room)
            .order_by(desc(Message.id))
            .limit(capped_limit)
        )).all()

        return [serialize_message(m) for m in reversed(rows)]

# Real-Time WebSocket Endpoint
@app.websocket("/ws/{room}")
async def websocket_endpoint(ws: WebSocket, room: str, token: str):
    room = room.strip().lower()
    try:
        claims = jwt.decode(token, SECRET, algorithms=["HS256"])
        username = claims.get("sub")
        role = claims.get("role", "user")
        if not username:
            await ws.close(code=1008)
            return
    except Exception:
        await ws.close(code=1008)
        return

    async with Session() as s:
        r = await s.scalar(select(Room).where(Room.name == room))
        if not r:
            await ws.close(code=1008)
            return
        if r.is_private and r.created_by != username and role != "admin":
            is_member = await s.scalar(
                select(RoomMember).where(RoomMember.room_name == room, RoomMember.username == username)
            )
            if not is_member:
                await ws.close(code=1008)
                return

    await ws.accept()
    sockets.setdefault(room, set()).add(ws)

    try:
        await ws.send_json({
            "type": "connected",
            "instance_id": INSTANCE,
            "username": username,
            "room": room,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })

        while True:
            data = await ws.receive_json()
            content = str(data.get("content", "")).strip()
            if not content:
                continue
            if len(content) > 2000:
                await ws.send_json({"type": "error", "message": "Message exceeds 2000 characters limit"})
                continue

            try:
                async with Session() as s:
                    m = Message(room=room, sender=username, content=content)
                    s.add(m)
                    await s.flush()
                    
                    payload = serialize_message(m)
                    outbox_entry = Outbox(
                        message_id=m.id,
                        payload=json.dumps(payload),
                        published=False
                    )
                    s.add(outbox_entry)
                    await s.commit()

                await ws.send_json({"type": "ack", "message": payload})
            except Exception as db_err:
                await ws.send_json({
                    "type": "error",
                    "message": "Database write error. Message not saved; please retry.",
                    "detail": str(db_err)[:100]
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        sockets.get(room, set()).discard(ws)

# =========================================================
# DYNAMIC CLUSTER TELEMETRY & DISCOVERY
# =========================================================
cached_known_gateways = [
    {"node_name": "gateway-a", "status": "running"},
    {"node_name": "gateway-b", "status": "running"},
    {"node_name": "gateway-c", "status": "running"}
]

async def fetch_dynamic_gateways():
    """Discover all active gateway nodes from fault-agent and query their health"""
    global cached_known_gateways
    nodes_info = []
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(
                "http://fault-agent:9000/cluster/gateways",
                headers={"X-Admin-Token": FAULT_ADMIN_TOKEN}
            )
            if res.status_code == 200:
                nodes_info = res.json()
                if nodes_info:
                    cached_known_gateways = nodes_info
    except Exception:
        pass

    if not nodes_info:
        nodes_info = cached_known_gateways

    async def probe_node(node):
        name = node["node_name"]

        # If this is the current gateway instance, return local metrics directly without loopback HTTP
        if name == INSTANCE:
            uptime_sec = round(time.time() - startup_time, 1)
            active_conns = sum(len(v) for v in sockets.values())
            return {
                "node_name": name,
                "instance_id": INSTANCE,
                "status": "ok",
                "uptime_seconds": uptime_sec,
                "requests_handled": request_counter,
                "active_connections": active_conns,
                "postgres": "ok",
                "redis": "ok",
                "container_id": node.get("container_id")
            }

        # If Docker controller already reports the node is not running, do NOT make an HTTP request!
        # This prevents Python's thread pool from locking up on DNS lookups to stopped containers.
        if node.get("status") not in {"running", "ok"}:
            return {
                "node_name": name,
                "instance_id": name,
                "status": "stopped",
                "uptime_seconds": 0,
                "requests_handled": 0,
                "active_connections": 0,
                "postgres": "unavailable",
                "redis": "unavailable",
                "container_id": node.get("container_id")
            }

        url = f"http://{name}:8000/health"
        try:
            async with httpx.AsyncClient(timeout=0.4) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    d = r.json()
                    return {
                        "node_name": name,
                        "instance_id": d.get("instance_id", name),
                        "status": "ok",
                        "uptime_seconds": d.get("uptime_seconds", 0),
                        "requests_handled": d.get("requests_handled", 0),
                        "active_connections": d.get("active_connections", 0),
                        "postgres": d.get("postgres", "ok"),
                        "redis": d.get("redis", "ok"),
                        "container_id": node.get("container_id")
                    }
        except Exception:
            pass
        return {
            "node_name": name,
            "instance_id": name,
            "status": "unavailable",
            "uptime_seconds": 0,
            "requests_handled": 0,
            "active_connections": 0,
            "postgres": "unavailable",
            "redis": "unavailable",
            "container_id": node.get("container_id")
        }

    results = await asyncio.gather(*(probe_node(n) for n in nodes_info))
    return results

@app.get("/api/admin/overview")
async def admin_overview(u: User = Depends(admin_auth)):
    async with Session() as s:
        users_count = await s.scalar(select(func.count()).select_from(User))
        messages_count = await s.scalar(select(func.count()).select_from(Message))
        rooms_count = await s.scalar(select(func.count()).select_from(Room))
        pending_outbox = await s.scalar(select(func.count()).select_from(Outbox).where(Outbox.published == False))
        published_outbox = await s.scalar(select(func.count()).select_from(Outbox).where(Outbox.published == True))

    gateways = await fetch_dynamic_gateways()
    total_conns = sum(g["active_connections"] for g in gateways)

    rd_status = "ok"
    try:
        await asyncio.wait_for(redis.ping(), timeout=0.8)
    except Exception:
        rd_status = "unavailable"

    worker_status = "unavailable"
    if rd_status == "ok":
        try:
            hb = await asyncio.wait_for(redis.get("socketscale:worker:heartbeat"), timeout=0.8)
            if hb and (time.time() - float(hb)) < 15:
                worker_status = "ok"
        except Exception:
            pass

    return {
        "users": users_count,
        "rooms": rooms_count,
        "messages": messages_count,
        "outbox_pending": pending_outbox,
        "outbox_published": published_outbox,
        "active_connections": total_conns,
        "gateways": gateways,
        "redis": rd_status,
        "postgres": "ok",
        "worker": worker_status,
        "current_instance": INSTANCE
    }

@app.get("/api/admin/gateways")
async def admin_gateways(u: User = Depends(admin_auth)):
    gateways = await fetch_dynamic_gateways()
    return {"gateways": gateways}

@app.post("/api/admin/gateways/scale")
async def scale_gateway(u: dict = Depends(admin_claims)):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                "http://fault-agent:9000/cluster/gateways/add",
                headers={"X-Admin-Token": FAULT_ADMIN_TOKEN}
            )
            r.raise_for_status()
            res = r.json()
            await record_log(
                "CLUSTER_SCALE",
                "INFO",
                "cluster",
                f"Cluster scaled out: added '{res.get('node_name')}'"
            )
            return res
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text[:200])
    except Exception as exc:
        raise HTTPException(503, f"Fault controller unavailable: {str(exc)[:100]}")

@app.delete("/api/admin/gateways/{name}")
async def decommission_gateway(name: str, u: dict = Depends(admin_claims)):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.delete(
                f"http://fault-agent:9000/cluster/gateways/{name}",
                headers={"X-Admin-Token": FAULT_ADMIN_TOKEN}
            )
            r.raise_for_status()
            res = r.json()
            await record_log(
                "CLUSTER_SCALE",
                "WARNING",
                "cluster",
                f"Cluster scaled in: decommissioned '{name}'"
            )
            return res
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text[:200])
    except Exception as exc:
        raise HTTPException(503, f"Fault controller unavailable: {str(exc)[:100]}")

@app.get("/api/admin/infrastructure")
async def admin_infrastructure(u: User = Depends(admin_auth)):
    db_status = "ok"
    db_messages = 0
    pending_outbox = 0
    published_outbox = 0
    failed_attempts = 0
    try:
        async with Session() as s:
            db_messages = await s.scalar(select(func.count()).select_from(Message))
            pending_outbox = await s.scalar(select(func.count()).select_from(Outbox).where(Outbox.published == False))
            published_outbox = await s.scalar(select(func.count()).select_from(Outbox).where(Outbox.published == True))
            failed_attempts = await s.scalar(select(func.coalesce(func.sum(Outbox.retry_count), 0)).select_from(Outbox))
    except Exception:
        db_status = "unavailable"

    rd_status = "ok"
    redis_info = {}
    try:
        await asyncio.wait_for(redis.ping(), timeout=0.8)
        info = await asyncio.wait_for(redis.info(), timeout=0.8)
        redis_info = {
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "total_commands_processed": info.get("total_commands_processed", 0)
        }
    except Exception:
        rd_status = "unavailable"

    worker_status = "unavailable"
    worker_hb_ago = None
    if rd_status == "ok":
        try:
            hb = await asyncio.wait_for(redis.get("socketscale:worker:heartbeat"), timeout=0.8)
            if hb:
                worker_hb_ago = round(time.time() - float(hb), 1)
                if worker_hb_ago < 15:
                    worker_status = "ok"
        except Exception:
            pass

    return {
        "postgres": {
            "status": db_status,
            "total_messages": db_messages,
            "pending_outbox": pending_outbox,
            "published_outbox": published_outbox,
            "failed_publishing_attempts": failed_attempts
        },
        "redis": {
            "status": rd_status,
            "metrics": redis_info
        },
        "worker": {
            "status": worker_status,
            "last_heartbeat_seconds_ago": worker_hb_ago
        }
    }

@app.get("/api/admin/metrics")
async def admin_metrics(u: User = Depends(admin_auth)):
    async with Session() as s:
        users = await s.scalar(select(func.count()).select_from(User))
        rooms = await s.scalar(select(func.count()).select_from(Room))
        messages = await s.scalar(select(func.count()).select_from(Message))
        pending = await s.scalar(select(func.count()).select_from(Outbox).where(Outbox.published == False))
        published = await s.scalar(select(func.count()).select_from(Outbox).where(Outbox.published == True))
        failed = await s.scalar(select(func.coalesce(func.sum(Outbox.retry_count), 0)).select_from(Outbox))

    return {
        "users": users,
        "rooms": rooms,
        "messages": messages,
        "outbox_pending": pending,
        "outbox_published": published,
        "outbox_failed_attempts": failed,
        "active_connections": sum(len(v) for v in sockets.values()),
        "requests_handled": request_counter,
        "uptime_seconds": round(time.time() - startup_time, 1),
        "instance_id": INSTANCE
    }

# Event Logs
@app.get("/api/admin/logs")
async def get_system_logs(
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = None,
    component: str | None = None,
    u: User = Depends(admin_auth)
):
    async with Session() as s:
        query = select(SystemLog).order_by(desc(SystemLog.id)).limit(limit)
        if event_type:
            query = query.where(SystemLog.event_type == event_type)
        if component:
            query = query.where(SystemLog.component == component)
        
        rows = (await s.scalars(query)).all()
        return [
            {
                "id": log.id,
                "event_type": log.event_type,
                "severity": log.severity,
                "component": log.component,
                "message": log.message,
                "details": log.details,
                "created_at": log.created_at.isoformat() + "Z"
            }
            for log in rows
        ]

# Fault Controller Proxy
@app.get("/api/admin/fault/services")
async def fault_services(u: dict = Depends(admin_claims)):
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get(
                "http://fault-agent:9000/services",
                headers={"X-Admin-Token": FAULT_ADMIN_TOKEN}
            )
            r.raise_for_status()
            return r.json()
    except Exception:
        raise HTTPException(503, "Fault controller agent unavailable")

@app.post("/api/admin/fault/services/{name}/{action}")
async def fault_action(name: str, action: str, u: dict = Depends(admin_claims)):
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(400, "Unsupported service action")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"http://fault-agent:9000/services/{name}/{action}",
                headers={"X-Admin-Token": FAULT_ADMIN_TOKEN}
            )
            r.raise_for_status()
            res = r.json()
            
            await record_log(
                "FAULT_INJECTION",
                "WARNING",
                "fault-agent",
                f"Action '{action}' executed on '{name}'",
                json.dumps(res)
            )
            return res
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text[:300])
    except Exception as exc:
        raise HTTPException(503, f"Fault controller unavailable: {str(exc)[:100]}")

@app.post("/api/admin/fault/stack/{action}")
async def fault_stack(action: str, u: dict = Depends(admin_claims)):
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(400, "Unsupported stack action")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"http://fault-agent:9000/stack/{action}",
                headers={"X-Admin-Token": FAULT_ADMIN_TOKEN}
            )
            r.raise_for_status()
            res = r.json()
            await record_log(
                "FAULT_INJECTION",
                "CRITICAL",
                "fault-agent",
                f"Stack action '{action}' executed",
                json.dumps(res)
            )
            return res
    except Exception:
        raise HTTPException(503, "Fault controller unavailable")

# =========================================================
# DYNAMIC BENCHMARKING ENGINE
# =========================================================
@app.post("/api/admin/benchmarks/run")
async def run_live_benchmark(req: BenchmarkTrigger, u: User = Depends(admin_auth)):
    clients_count = req.clients
    msgs_per_client = req.messages_per_client
    room_name = req.room.strip().lower()

    async with Session() as s:
        existing = await s.scalar(select(Room).where(Room.name == room_name))
        if not existing:
            s.add(Room(name=room_name, is_private=False, created_by=u.username))
            await s.commit()

    bench_token = create_access_token(u)
    ws_target = f"ws://nginx:80/ws/{room_name}?token={bench_token}"

    latencies = []
    errors = []
    acks = [0]
    connected = [0]
    gateway_dist = {}

    async def single_client(cid: int):
        try:
            async with websockets.connect(ws_target, open_timeout=10, close_timeout=5) as ws:
                greet_raw = await asyncio.wait_for(ws.recv(), timeout=8)
                try:
                    greet = json.loads(greet_raw)
                    inst = greet.get("instance_id", "unknown")
                    gateway_dist[inst] = gateway_dist.get(inst, 0) + 1
                except Exception:
                    pass
                connected[0] += 1

                for i in range(msgs_per_client):
                    t0 = time.perf_counter()
                    await ws.send(json.dumps({
                        "content": f"[Live Bench C{cid} M{i+1}] dynamic stress packet"
                    }))

                    while True:
                        resp_raw = await asyncio.wait_for(ws.recv(), timeout=20)
                        ev = json.loads(resp_raw)
                        if ev.get("type") == "ack":
                            lat = (time.perf_counter() - t0) * 1000
                            latencies.append(lat)
                            acks[0] += 1
                            break
                        elif ev.get("type") == "error":
                            errors.append(ev.get("message", "server error"))
                            break
        except Exception as exc:
            errors.append(f"Client {cid}: {str(exc)[:100]}")

    start_all = time.perf_counter()
    tasks = [single_client(i) for i in range(clients_count)]
    await asyncio.gather(*tasks)
    duration = time.perf_counter() - start_all

    latencies.sort()
    def pct(p):
        if not latencies:
            return 0.0
        idx = int(round(p * (len(latencies) - 1)))
        return round(latencies[idx], 2)

    expected = clients_count * msgs_per_client
    acknowledged = acks[0]
    throughput = round(acknowledged / duration, 2) if duration > 0 else 0.0
    mean_lat = round(statistics.mean(latencies), 2) if latencies else 0.0
    median_lat = pct(0.50)
    p95_lat = pct(0.95)
    max_lat = round(max(latencies), 2) if latencies else 0.0

    result = {
        "clients": clients_count,
        "messages_per_client": msgs_per_client,
        "expected_messages": expected,
        "connected_clients": connected[0],
        "failed_connections": clients_count - connected[0],
        "acknowledged": acknowledged,
        "failed_messages": expected - acknowledged,
        "duration_seconds": round(duration, 3),
        "throughput_msg_per_sec": throughput,
        "mean_latency_ms": mean_lat,
        "median_latency_ms": median_lat,
        "p95_latency_ms": p95_lat,
        "max_latency_ms": max_lat,
        "gateway_distribution": gateway_dist,
        "errors_count": len(errors),
        "sample_errors": errors[:5]
    }

    async with Session() as s:
        run_name = f"{clients_count} clients x {msgs_per_client} msgs ({throughput} msg/s)"
        item = BenchmarkRun(
            name=run_name,
            clients=clients_count,
            messages_per_client=msgs_per_client,
            total_messages=expected,
            results=json.dumps(result)
        )
        s.add(item)
        await s.commit()
        await s.refresh(item)

        await record_log(
            "BENCHMARK",
            "INFO",
            "benchmark",
            f"Live Dynamic Benchmark completed: {run_name}"
        )

        return {
            "id": item.id,
            "name": item.name,
            "clients": clients_count,
            "messages_per_client": msgs_per_client,
            "total_messages": expected,
            "results": result,
            "created_at": item.created_at.isoformat() + "Z"
        }

@app.post("/api/admin/benchmarks")
async def save_benchmark(b: BenchmarkReport, u: User = Depends(admin_auth)):
    async with Session() as s:
        item = BenchmarkRun(
            name=b.name,
            clients=b.clients,
            messages_per_client=b.messages_per_client,
            total_messages=b.clients * b.messages_per_client,
            results=json.dumps(b.results)
        )
        s.add(item)
        await s.commit()
        await s.refresh(item)

        await record_log(
            "BENCHMARK",
            "INFO",
            "benchmark",
            f"Benchmark run saved: '{b.name}' ({b.clients} clients, {item.total_messages} msgs)"
        )
        return {
            "id": item.id,
            "name": item.name,
            "created_at": item.created_at.isoformat() + "Z"
        }

@app.get("/api/admin/benchmarks")
async def list_benchmarks(u: User = Depends(admin_auth)):
    async with Session() as s:
        rows = (await s.scalars(select(BenchmarkRun).order_by(desc(BenchmarkRun.id)).limit(50))).all()
        return [
            {
                "id": x.id,
                "name": x.name,
                "clients": x.clients,
                "messages_per_client": x.messages_per_client,
                "total_messages": x.total_messages,
                "results": json.loads(x.results),
                "created_at": x.created_at.isoformat() + "Z"
            }
            for x in rows
        ]

@app.get("/api/admin/benchmarks/{benchmark_id}/export")
async def export_benchmark(
    benchmark_id: int,
    format: str = Query("json", regex="^(json|csv)$"),
    u: User = Depends(admin_auth)
):
    async with Session() as s:
        run = await s.scalar(select(BenchmarkRun).where(BenchmarkRun.id == benchmark_id))
        if not run:
            raise HTTPException(404, "Benchmark not found")

        results = json.loads(run.results)
        if format == "json":
            export_data = {
                "id": run.id,
                "name": run.name,
                "clients": run.clients,
                "messages_per_client": run.messages_per_client,
                "total_messages": run.total_messages,
                "created_at": run.created_at.isoformat() + "Z",
                "results": results
            }
            return Response(
                content=json.dumps(export_data, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=benchmark_{run.id}.json"}
            )
        else:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Metric", "Value"])
            writer.writerow(["Run ID", run.id])
            writer.writerow(["Name", run.name])
            writer.writerow(["Clients", run.clients])
            writer.writerow(["Messages Per Client", run.messages_per_client])
            writer.writerow(["Total Expected", run.total_messages])
            writer.writerow(["Created At", run.created_at.isoformat() + "Z"])
            for k, v in results.items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    writer.writerow([k, v])
            
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=benchmark_{run.id}.csv"}
            )
