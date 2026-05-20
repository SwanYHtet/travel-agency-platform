from contextlib import asynccontextmanager

from fastapi import FastAPI

from sqlalchemy import text

from app.core.database import Base, SessionLocal, engine
import app.models
from app.models.booking import User
from app.api.v1.router import api_router


def _seed_db():
    # The original template had no startup hook, so tables were never created.
    # create_all() is idempotent — safe to call on every restart.
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        # Airline_Master and Airport_Master are referenced in booking.py via raw SQL
        # but have no SQLAlchemy models, so create_all() skips them entirely.
        # Without these tables the booking endpoint raises a 500 on every request.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS Airline_Master (
                Airline_Code TEXT PRIMARY KEY,
                Airline_Name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS Airport_Master (
                Airport_Code TEXT PRIMARY KEY,
                Airport_Name TEXT NOT NULL,
                City TEXT,
                Country TEXT
            )
        """))
        conn.commit()

    db = SessionLocal()
    try:
        # Guard prevents duplicate inserts on every restart.
        # Password is hardcoded to CMPE-131@2026 in booking.py (_HARDCODED_PASSWORD).
        if not db.query(User).filter_by(Email="john.doe@example.com").first():
            db.add(User(
                First_Name="John",
                Last_Name="Doe",
                Email="john.doe@example.com",
                Phone_Number="555-123-4567",
            ))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_db()
    yield


app = FastAPI(title="Travel Agency API", lifespan=lifespan)
app.include_router(api_router, prefix="/api/v1")

