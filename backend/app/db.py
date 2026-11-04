import os
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean, Integer, ForeignKey, select, desc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from passlib.context import CryptContext

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://socketscale:socketscale@postgres:5432/socketscale"
)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=20, max_overflow=10)
Session = async_sessionmaker(engine, expire_on_commit=False)
pwd = CryptContext(schemes=["argon2"], deprecated="auto")

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class RoomMember(Base):
    __tablename__ = "room_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_name: Mapped[str] = mapped_column(String(100), index=True)
    username: Mapped[str] = mapped_column(String(80), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    room: Mapped[str] = mapped_column(String(100), index=True)
    sender: Mapped[str] = mapped_column(String(80), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class Outbox(Base):
    __tablename__ = "message_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    payload: Mapped[str] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="Benchmark")
    clients: Mapped[int] = mapped_column(Integer)
    messages_per_client: Mapped[int] = mapped_column(Integer)
    total_messages: Mapped[int] = mapped_column(Integer)
    results: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class SystemLog(Base):
    __tablename__ = "system_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="INFO", index=True)
    component: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(String(255))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

async def record_log(event_type: str, severity: str, component: str, message: str, details: str | None = None):
    try:
        async with Session() as s:
            s.add(SystemLog(
                event_type=event_type,
                severity=severity,
                component=component,
                message=message,
                details=details
            ))
            await s.commit()
    except Exception:
        # Fallback if DB is unavailable during failure simulation
        pass

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with Session() as s:
        # Seed default users if not present
        default_users = [
            ("admin", "admin", "AdminPass123!"),
            ("piyush", "user", "UserPass123!"),
            ("mahek", "user", "UserPass123!"),
            ("faculty", "user", "FacultyPass123!")
        ]
        for name, role, pw in default_users:
            existing = await s.scalar(select(User).where(User.username == name))
            if not existing:
                s.add(User(username=name, role=role, password_hash=pwd.hash(pw)))
        
        # Seed default general public room
        general_room = await s.scalar(select(Room).where(Room.name == "general"))
        if not general_room:
            s.add(Room(name="general", is_private=False, created_by="system"))
            
        dev_room = await s.scalar(select(Room).where(Room.name == "announcements"))
        if not dev_room:
            s.add(Room(name="announcements", is_private=False, created_by="admin"))
            
        await s.commit()

        # Record system initialization log
        await record_log(
            event_type="SERVICE_LIFECYCLE",
            severity="INFO",
            component="database",
            message="PostgreSQL database initialized and seed records verified"
        )
