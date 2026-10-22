import asyncio
import json
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

import jwt
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel, StringConstraints
from pwdlib import PasswordHash
from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

INSTANCE_ID = os.getenv("INSTANCE_ID", "gateway-" + uuid4().hex[:6])
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://socketscale:local-demo-password@localhost:5432/socketscale")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "replace-this-local-demo-secret")
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)
passwords = PasswordHash.recommended()
redis_client = None
listener_task = None

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room: Mapped[str] = mapped_column(String(80), index=True)
    username: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Credentials(BaseModel):
    username: Annotated[str, StringConstraints(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")]
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]

def make_token(username):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": username, "iat": now, "exp": now + timedelta(hours=12)}, JWT_SECRET, algorithm="HS256")

def decode_token(token):
    try:
        name = jwt.decode(token, JWT_SECRET, algorithms=["HS256"]).get("sub")
        if not isinstance(name, str) or not name:
            raise ValueError()
        return name
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Invalid or expired token")

class Manager:
    def __init__(self):
        self.sockets = defaultdict(set)
        self.opened = 0
        self.closed = 0
        self.published = 0
        self.started = time.time()
    async def connect(self, room, ws):
        await ws.accept()
        self.sockets[room].add(ws)
        self.opened += 1
    def disconnect(self, room, ws):
        self.sockets[room].discard(ws)
        if not self.sockets[room]:
            self.sockets.pop(room, None)
        self.closed += 1
    async def broadcast(self, room, event):
        dead = []
        for ws in list(self.sockets.get(room, set())):
            try:
                await ws.send_text(json.dumps(event, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(room, ws)

manager = Manager()

async def listen_redis():
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("socketscale:room:*")
    try:
        async for item in pubsub.listen():
            if item.get("type") != "pmessage":
                continue
            try:
                event = json.loads(item["data"])
                if event.get("origin") != INSTANCE_ID:
                    await manager.broadcast(event["room"], event)
            except (ValueError, KeyError, TypeError):
                pass
    finally:
        await pubsub.aclose()

@asynccontextmanager
async def lifespan(app):
    global redis_client, listener_task
    for attempt in range(30):
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            await redis_client.ping()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except Exception:
            if redis_client:
                with suppress(Exception):
                    await redis_client.aclose()
            redis_client = None
            if attempt == 29:
                raise
            await asyncio.sleep(2)
    listener_task = asyncio.create_task(listen_redis())
    try:
        yield
    finally:
        listener_task.cancel()
        with suppress(asyncio.CancelledError):
            await listener_task
        if redis_client:
            await redis_client.aclose()
        await engine.dispose()

app = FastAPI(title="SocketScale Gateway API", version="1.0.0", lifespan=lifespan)

@app.get("/")
async def root():
    return {"name": "SocketScale", "instance_id": INSTANCE_ID, "docs": "/docs"}

@app.get("/health")
async def health():
    db_ok = cache_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        db_ok = True
    except Exception:
        pass
    try:
        if redis_client:
            await redis_client.ping()
            cache_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok and cache_ok else "degraded", "instance_id": INSTANCE_ID,
            "postgres": "ok" if db_ok else "unavailable", "redis": "ok" if cache_ok else "unavailable",
            "uptime_seconds": round(time.time() - manager.started, 2)}

@app.post("/api/auth/register", status_code=201)
async def register(body: Credentials):
    username = body.username.lower()
    async with Session() as session:
        if await session.scalar(select(User).where(User.username == username)):
            raise HTTPException(409, "Username already exists")
        session.add(User(username=username, password_hash=passwords.hash(body.password)))
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise HTTPException(409, "Username already exists")
    return {"access_token": make_token(username), "token_type": "bearer", "username": username}

@app.post("/api/auth/login")
async def login(body: Credentials):
    username = body.username.lower()
    async with Session() as session:
        user = await session.scalar(select(User).where(User.username == username))
    if not user or not passwords.verify(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": make_token(username), "token_type": "bearer", "username": username}

async def current_user(token: str = Query(...)):
    return decode_token(token)

@app.get("/api/whoami")
async def whoami(username: str = Depends(current_user)):
    return {"username": username, "instance_id": INSTANCE_ID}

@app.get("/api/rooms/{room}/messages")
async def history(room: str, username: str = Depends(current_user), limit: int = 50):
    if not 1 <= limit <= 100:
        raise HTTPException(400, "limit must be between 1 and 100")
    async with Session() as session:
        rows = (await session.scalars(select(Message).where(Message.room == room).order_by(Message.id.desc()).limit(limit))).all()
    return {"room": room, "messages": [{"id": m.id, "username": m.username, "content": m.content, "created_at": m.created_at.isoformat()} for m in reversed(rows)]}

@app.get("/api/metrics")
async def metrics():
    return {"instance_id": INSTANCE_ID, "uptime_seconds": round(time.time() - manager.started, 2),
            "active_connections": sum(len(v) for v in manager.sockets.values()),
            "rooms": {k: len(v) for k, v in manager.sockets.items()},
            "events": {"connections_opened": manager.opened, "connections_closed": manager.closed, "messages_published": manager.published}}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str, room: str = "general"):
    try:
        username = decode_token(token)
    except HTTPException:
        await ws.close(code=4401, reason="Invalid token")
        return
    if not room or len(room) > 80:
        await ws.close(code=4400, reason="Invalid room")
        return
    await manager.connect(room, ws)
    await ws.send_text(json.dumps({"type": "connected", "instance_id": INSTANCE_ID, "room": room, "username": username}))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                obj = json.loads(raw)
                message = obj.get("content")
                if not isinstance(message, str) or not message.strip() or len(message) > 2000:
                    raise ValueError()
            except (ValueError, AttributeError):
                await ws.send_text(json.dumps({"type": "error", "detail": "Send JSON with non-empty content up to 2000 characters"}))
                continue
            async with Session() as session:
                row = Message(room=room, username=username, content=message.strip())
                session.add(row)
                await session.commit()
                await session.refresh(row)
                event = {"type": "message", "id": row.id, "room": room, "username": username,
                         "content": message.strip(), "created_at": row.created_at.isoformat(), "origin": INSTANCE_ID}
            try:
                await redis_client.publish(f"socketscale:room:{room}", json.dumps(event))
            except Exception:
                await ws.send_text(json.dumps({"type": "error", "detail": "Redis publish failed"}))
                continue
            manager.published += 1
            await manager.broadcast(room, event)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(room, ws)
