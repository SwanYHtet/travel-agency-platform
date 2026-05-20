from datetime import datetime, timedelta
from enum import Enum
from typing import List

#fastAPI core imports
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, engine, Base
from models import Tenant, User, Booking


#we initialize the app
app = FastAPI(title="Travel Booking Backend API")

#create all database tables
Base.metadata.create_all(bind=engine)

#Database Dependency
#this get a database session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#Tenant
def check_tenant(x_tenant_id: str):
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="Missing x-tenant-id header")

#Initialize seed data
def seed_data():
    db = SessionLocal()
    try:
        #create tenants only if none exist
        if db.query(Tenant).count() == 0:
            tenant_1 = Tenant(id=1, name="SkyWay Travel", currency="USD", routing_preference="fastest")
            tenant_2 = Tenant(id=2, name="DreamTrip Agency", currency="USD", routing_preference="cheapest")
            db.add_all([tenant_1, tenant_2])
            db.commit()

        #create users only if none exist
        if db.query(User).count() == 0:
            user_1 = User(id=1, name="Alice", email="alice@example.com", tenant_id=1)
            user_2 = User(id=2, name="Bob", email="bob@example.com", tenant_id=2)
            db.add_all([user_1, user_2])
            db.commit()
    finally:
        db.close()

seed_data()

# Health Check
@app.get("/")
def home():
    return {"message": "Backend is working with persistence and state management"}


# Flight Data Store
# Simulated flight data per route
#42 bidirectional routes cover all pairs of SFO, NRT, ICN, CDG, LHR, JFK, LAX.
#the original Phase 2 had only 4 routes (SFO↔NRT, NRT↔ICN, ICN↔SFO).
# The full set is required so Multi-City Package Builder can route between any two of the 7 supported cities.
FLIGHT_DATA = {
    "SFO-NRT": {
        "itineraryId": 1,
        "totalCost": 850,
        "totalDuration": "11h 20m",
        "legs": [
            {
                "from": "SFO", "to": "NRT",
                "departureTime": "2026-05-10 09:00",
                "arrivalTime": "2026-05-10 17:20",
                "airline": "Japan Airlines",
                "flightNumber": "JL001",
                "layoverMinutes": 0,
                "riskyLayoverWarning": False
            }
        ],
        "backupFlight": {
            "airline": "ANA", "flightNumber": "NH007",
            "departureTime": "2026-05-10 11:30",
            "arrivalTime": "2026-05-10 19:50"
        }
    },
    "NRT-ICN": {
        "itineraryId": 2,
        "totalCost": 320,
        "totalDuration": "2h 30m",
        "legs": [
            {
                "from": "NRT", "to": "ICN",
                "departureTime": "2026-05-14 10:00",
                "arrivalTime": "2026-05-14 12:30",
                "airline": "Korean Air",
                "flightNumber": "KE704",
                "layoverMinutes": 0,
                "riskyLayoverWarning": False
            }
        ],
        "backupFlight": {
            "airline": "Asiana", "flightNumber": "OZ102",
            "departureTime": "2026-05-14 14:00",
            "arrivalTime": "2026-05-14 16:30"
        }
    },
    "ICN-SFO": {
        "itineraryId": 3,
        "totalCost": 780,
        "totalDuration": "10h 50m",
        "legs": [
            {
                "from": "ICN", "to": "SFO",
                "departureTime": "2026-05-18 13:00",
                "arrivalTime": "2026-05-18 08:50",
                "airline": "Korean Air",
                "flightNumber": "KE023",
                "layoverMinutes": 50,
                "riskyLayoverWarning": True
            }
        ],
        "backupFlight": {
            "airline": "United", "flightNumber": "UA893",
            "departureTime": "2026-05-18 16:00",
            "arrivalTime": "2026-05-18 11:50"
        }
    },
    "SFO-ICN": {
        "itineraryId": 4,
        "totalCost": 900,
        "totalDuration": "12h 00m",
        "legs": [{"from": "SFO", "to": "ICN", "departureTime": "2026-05-10 11:00", "arrivalTime": "2026-05-11 15:00", "airline": "Korean Air", "flightNumber": "KE025", "layoverMinutes": 0, "riskyLayoverWarning": False}],
        "backupFlight": {"airline": "Asiana", "flightNumber": "OZ202", "departureTime": "2026-05-10 14:00", "arrivalTime": "2026-05-11 18:00"}
    },
    # ---- FROM SFO ----
    "SFO-CDG": {"itineraryId": 5, "totalCost": 860, "totalDuration": "10h 30m", "legs": [{"from": "SFO", "to": "CDG", "departureTime": "2026-05-10 16:00", "arrivalTime": "2026-05-11 11:30", "airline": "Air France", "flightNumber": "AF083", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "United", "flightNumber": "UA990", "departureTime": "2026-05-10 18:00", "arrivalTime": "2026-05-11 13:30"}},
    "SFO-LHR": {"itineraryId": 6, "totalCost": 820, "totalDuration": "10h 15m", "legs": [{"from": "SFO", "to": "LHR", "departureTime": "2026-05-10 15:00", "arrivalTime": "2026-05-11 09:15", "airline": "British Airways", "flightNumber": "BA286", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Virgin Atlantic", "flightNumber": "VS20", "departureTime": "2026-05-10 17:30", "arrivalTime": "2026-05-11 11:45"}},
    "SFO-JFK": {"itineraryId": 7, "totalCost": 340, "totalDuration": "5h 30m", "legs": [{"from": "SFO", "to": "JFK", "departureTime": "2026-05-10 07:00", "arrivalTime": "2026-05-10 15:30", "airline": "United", "flightNumber": "UA201", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Delta", "flightNumber": "DL401", "departureTime": "2026-05-10 09:00", "arrivalTime": "2026-05-10 17:30"}},
    "SFO-LAX": {"itineraryId": 8, "totalCost": 120, "totalDuration": "1h 20m", "legs": [{"from": "SFO", "to": "LAX", "departureTime": "2026-05-10 08:00", "arrivalTime": "2026-05-10 09:20", "airline": "Southwest", "flightNumber": "WN100", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "United", "flightNumber": "UA511", "departureTime": "2026-05-10 10:00", "arrivalTime": "2026-05-10 11:20"}},
    # ---- TO SFO ----
    "NRT-SFO": {"itineraryId": 9, "totalCost": 850, "totalDuration": "9h 30m", "legs": [{"from": "NRT", "to": "SFO", "departureTime": "2026-05-18 17:00", "arrivalTime": "2026-05-18 10:30", "airline": "ANA", "flightNumber": "NH008", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Japan Airlines", "flightNumber": "JL002", "departureTime": "2026-05-18 19:00", "arrivalTime": "2026-05-18 12:30"}},
    "CDG-SFO": {"itineraryId": 10, "totalCost": 860, "totalDuration": "11h 00m", "legs": [{"from": "CDG", "to": "SFO", "departureTime": "2026-05-18 11:00", "arrivalTime": "2026-05-18 13:00", "airline": "Air France", "flightNumber": "AF084", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "United", "flightNumber": "UA991", "departureTime": "2026-05-18 13:00", "arrivalTime": "2026-05-18 15:00"}},
    "LHR-SFO": {"itineraryId": 11, "totalCost": 820, "totalDuration": "10h 45m", "legs": [{"from": "LHR", "to": "SFO", "departureTime": "2026-05-18 12:00", "arrivalTime": "2026-05-18 14:45", "airline": "British Airways", "flightNumber": "BA287", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Virgin Atlantic", "flightNumber": "VS21", "departureTime": "2026-05-18 14:00", "arrivalTime": "2026-05-18 16:45"}},
    "JFK-SFO": {"itineraryId": 12, "totalCost": 340, "totalDuration": "6h 00m", "legs": [{"from": "JFK", "to": "SFO", "departureTime": "2026-05-18 07:00", "arrivalTime": "2026-05-18 10:00", "airline": "Delta", "flightNumber": "DL402", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "United", "flightNumber": "UA202", "departureTime": "2026-05-18 09:00", "arrivalTime": "2026-05-18 12:00"}},
    "LAX-SFO": {"itineraryId": 13, "totalCost": 120, "totalDuration": "1h 20m", "legs": [{"from": "LAX", "to": "SFO", "departureTime": "2026-05-18 08:00", "arrivalTime": "2026-05-18 09:20", "airline": "Southwest", "flightNumber": "WN101", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "United", "flightNumber": "UA512", "departureTime": "2026-05-18 10:00", "arrivalTime": "2026-05-18 11:20"}},
    # ---- FROM/TO LAX ----
    "LAX-NRT": {"itineraryId": 14, "totalCost": 780, "totalDuration": "11h 00m", "legs": [{"from": "LAX", "to": "NRT", "departureTime": "2026-05-10 13:00", "arrivalTime": "2026-05-11 17:00", "airline": "Japan Airlines", "flightNumber": "JL061", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "ANA", "flightNumber": "NH005", "departureTime": "2026-05-10 15:00", "arrivalTime": "2026-05-11 19:00"}},
    "NRT-LAX": {"itineraryId": 15, "totalCost": 780, "totalDuration": "9h 30m", "legs": [{"from": "NRT", "to": "LAX", "departureTime": "2026-05-18 17:30", "arrivalTime": "2026-05-18 11:00", "airline": "ANA", "flightNumber": "NH006", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Japan Airlines", "flightNumber": "JL062", "departureTime": "2026-05-18 19:30", "arrivalTime": "2026-05-18 13:00"}},
    "LAX-ICN": {"itineraryId": 16, "totalCost": 830, "totalDuration": "12h 30m", "legs": [{"from": "LAX", "to": "ICN", "departureTime": "2026-05-10 14:00", "arrivalTime": "2026-05-11 18:30", "airline": "Korean Air", "flightNumber": "KE017", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Asiana", "flightNumber": "OZ201", "departureTime": "2026-05-10 16:00", "arrivalTime": "2026-05-11 20:30"}},
    "ICN-LAX": {"itineraryId": 17, "totalCost": 830, "totalDuration": "11h 00m", "legs": [{"from": "ICN", "to": "LAX", "departureTime": "2026-05-18 10:00", "arrivalTime": "2026-05-18 07:00", "airline": "Korean Air", "flightNumber": "KE018", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Asiana", "flightNumber": "OZ202", "departureTime": "2026-05-18 12:00", "arrivalTime": "2026-05-18 09:00"}},
    "LAX-CDG": {"itineraryId": 18, "totalCost": 790, "totalDuration": "11h 00m", "legs": [{"from": "LAX", "to": "CDG", "departureTime": "2026-05-10 16:30", "arrivalTime": "2026-05-11 12:30", "airline": "Air France", "flightNumber": "AF065", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Delta", "flightNumber": "DL8702", "departureTime": "2026-05-10 18:30", "arrivalTime": "2026-05-11 14:30"}},
    "CDG-LAX": {"itineraryId": 19, "totalCost": 790, "totalDuration": "11h 30m", "legs": [{"from": "CDG", "to": "LAX", "departureTime": "2026-05-18 10:00", "arrivalTime": "2026-05-18 12:30", "airline": "Air France", "flightNumber": "AF066", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Delta", "flightNumber": "DL8703", "departureTime": "2026-05-18 12:00", "arrivalTime": "2026-05-18 14:30"}},
    "LAX-LHR": {"itineraryId": 20, "totalCost": 750, "totalDuration": "10h 30m", "legs": [{"from": "LAX", "to": "LHR", "departureTime": "2026-05-10 17:00", "arrivalTime": "2026-05-11 11:30", "airline": "British Airways", "flightNumber": "BA269", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Virgin Atlantic", "flightNumber": "VS41", "departureTime": "2026-05-10 19:00", "arrivalTime": "2026-05-11 13:30"}},
    "LHR-LAX": {"itineraryId": 21, "totalCost": 750, "totalDuration": "11h 00m", "legs": [{"from": "LHR", "to": "LAX", "departureTime": "2026-05-18 11:00", "arrivalTime": "2026-05-18 14:00", "airline": "British Airways", "flightNumber": "BA270", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Virgin Atlantic", "flightNumber": "VS42", "departureTime": "2026-05-18 13:00", "arrivalTime": "2026-05-18 16:00"}},
    "LAX-JFK": {"itineraryId": 22, "totalCost": 310, "totalDuration": "5h 20m", "legs": [{"from": "LAX", "to": "JFK", "departureTime": "2026-05-10 08:00", "arrivalTime": "2026-05-10 16:20", "airline": "Delta", "flightNumber": "DL403", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "American", "flightNumber": "AA100", "departureTime": "2026-05-10 10:00", "arrivalTime": "2026-05-10 18:20"}},
    "JFK-LAX": {"itineraryId": 23, "totalCost": 310, "totalDuration": "5h 50m", "legs": [{"from": "JFK", "to": "LAX", "departureTime": "2026-05-18 08:00", "arrivalTime": "2026-05-18 11:50", "airline": "Delta", "flightNumber": "DL404", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "American", "flightNumber": "AA101", "departureTime": "2026-05-18 10:00", "arrivalTime": "2026-05-18 13:50"}},
    # ---- FROM/TO JFK ----
    "JFK-NRT": {"itineraryId": 24, "totalCost": 980, "totalDuration": "14h 00m", "legs": [{"from": "JFK", "to": "NRT", "departureTime": "2026-05-10 13:00", "arrivalTime": "2026-05-11 16:00", "airline": "Japan Airlines", "flightNumber": "JL005", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "ANA", "flightNumber": "NH009", "departureTime": "2026-05-10 15:00", "arrivalTime": "2026-05-11 18:00"}},
    "NRT-JFK": {"itineraryId": 25, "totalCost": 980, "totalDuration": "13h 00m", "legs": [{"from": "NRT", "to": "JFK", "departureTime": "2026-05-18 16:00", "arrivalTime": "2026-05-18 15:00", "airline": "Japan Airlines", "flightNumber": "JL006", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "ANA", "flightNumber": "NH010", "departureTime": "2026-05-18 18:00", "arrivalTime": "2026-05-18 17:00"}},
    "JFK-ICN": {"itineraryId": 26, "totalCost": 1020, "totalDuration": "14h 30m", "legs": [{"from": "JFK", "to": "ICN", "departureTime": "2026-05-10 12:00", "arrivalTime": "2026-05-11 15:30", "airline": "Korean Air", "flightNumber": "KE082", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Asiana", "flightNumber": "OZ221", "departureTime": "2026-05-10 14:00", "arrivalTime": "2026-05-11 17:30"}},
    "ICN-JFK": {"itineraryId": 27, "totalCost": 1020, "totalDuration": "14h 00m", "legs": [{"from": "ICN", "to": "JFK", "departureTime": "2026-05-18 10:30", "arrivalTime": "2026-05-18 10:30", "airline": "Korean Air", "flightNumber": "KE081", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Asiana", "flightNumber": "OZ222", "departureTime": "2026-05-18 12:30", "arrivalTime": "2026-05-18 12:30"}},
    "JFK-CDG": {"itineraryId": 28, "totalCost": 630, "totalDuration": "7h 30m", "legs": [{"from": "JFK", "to": "CDG", "departureTime": "2026-05-10 22:00", "arrivalTime": "2026-05-11 11:30", "airline": "Air France", "flightNumber": "AF011", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Delta", "flightNumber": "DL8701", "departureTime": "2026-05-10 23:00", "arrivalTime": "2026-05-11 12:30"}},
    "CDG-JFK": {"itineraryId": 29, "totalCost": 630, "totalDuration": "8h 30m", "legs": [{"from": "CDG", "to": "JFK", "departureTime": "2026-05-18 10:00", "arrivalTime": "2026-05-18 12:30", "airline": "Air France", "flightNumber": "AF012", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Delta", "flightNumber": "DL8702", "departureTime": "2026-05-18 12:00", "arrivalTime": "2026-05-18 14:30"}},
    "JFK-LHR": {"itineraryId": 30, "totalCost": 580, "totalDuration": "7h 00m", "legs": [{"from": "JFK", "to": "LHR", "departureTime": "2026-05-10 21:00", "arrivalTime": "2026-05-11 09:00", "airline": "British Airways", "flightNumber": "BA112", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "American", "flightNumber": "AA100", "departureTime": "2026-05-10 22:00", "arrivalTime": "2026-05-11 10:00"}},
    "LHR-JFK": {"itineraryId": 31, "totalCost": 580, "totalDuration": "8h 00m", "legs": [{"from": "LHR", "to": "JFK", "departureTime": "2026-05-18 11:00", "arrivalTime": "2026-05-18 14:00", "airline": "British Airways", "flightNumber": "BA113", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "American", "flightNumber": "AA101", "departureTime": "2026-05-18 13:00", "arrivalTime": "2026-05-18 16:00"}},
    # ---- FROM/TO LHR ----
    "LHR-NRT": {"itineraryId": 32, "totalCost": 880, "totalDuration": "12h 00m", "legs": [{"from": "LHR", "to": "NRT", "departureTime": "2026-05-10 10:00", "arrivalTime": "2026-05-11 07:00", "airline": "British Airways", "flightNumber": "BA008", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Japan Airlines", "flightNumber": "JL043", "departureTime": "2026-05-10 12:00", "arrivalTime": "2026-05-11 09:00"}},
    "NRT-LHR": {"itineraryId": 33, "totalCost": 880, "totalDuration": "12h 30m", "legs": [{"from": "NRT", "to": "LHR", "departureTime": "2026-05-18 11:00", "arrivalTime": "2026-05-18 15:30", "airline": "Japan Airlines", "flightNumber": "JL044", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "British Airways", "flightNumber": "BA009", "departureTime": "2026-05-18 13:00", "arrivalTime": "2026-05-18 17:30"}},
    "LHR-ICN": {"itineraryId": 34, "totalCost": 920, "totalDuration": "11h 30m", "legs": [{"from": "LHR", "to": "ICN", "departureTime": "2026-05-10 13:00", "arrivalTime": "2026-05-11 08:30", "airline": "Korean Air", "flightNumber": "KE908", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "British Airways", "flightNumber": "BA018", "departureTime": "2026-05-10 15:00", "arrivalTime": "2026-05-11 10:30"}},
    "ICN-LHR": {"itineraryId": 35, "totalCost": 920, "totalDuration": "11h 30m", "legs": [{"from": "ICN", "to": "LHR", "departureTime": "2026-05-18 13:30", "arrivalTime": "2026-05-18 18:00", "airline": "Korean Air", "flightNumber": "KE907", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "British Airways", "flightNumber": "BA019", "departureTime": "2026-05-18 15:30", "arrivalTime": "2026-05-18 20:00"}},
    "LHR-CDG": {"itineraryId": 36, "totalCost": 140, "totalDuration": "1h 15m", "legs": [{"from": "LHR", "to": "CDG", "departureTime": "2026-05-10 09:00", "arrivalTime": "2026-05-10 11:15", "airline": "Air France", "flightNumber": "AF1281", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "British Airways", "flightNumber": "BA304", "departureTime": "2026-05-10 11:00", "arrivalTime": "2026-05-10 13:15"}},
    "CDG-LHR": {"itineraryId": 37, "totalCost": 140, "totalDuration": "1h 15m", "legs": [{"from": "CDG", "to": "LHR", "departureTime": "2026-05-14 08:00", "arrivalTime": "2026-05-14 08:15", "airline": "Air France", "flightNumber": "AF1282", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "British Airways", "flightNumber": "BA305", "departureTime": "2026-05-14 10:00", "arrivalTime": "2026-05-14 10:15"}},
    # ---- FROM/TO CDG ----
    "CDG-NRT": {"itineraryId": 38, "totalCost": 930, "totalDuration": "12h 00m", "legs": [{"from": "CDG", "to": "NRT", "departureTime": "2026-05-10 10:30", "arrivalTime": "2026-05-11 06:30", "airline": "Air France", "flightNumber": "AF275", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Japan Airlines", "flightNumber": "JL047", "departureTime": "2026-05-10 12:30", "arrivalTime": "2026-05-11 08:30"}},
    "NRT-CDG": {"itineraryId": 39, "totalCost": 930, "totalDuration": "13h 00m", "legs": [{"from": "NRT", "to": "CDG", "departureTime": "2026-05-18 10:00", "arrivalTime": "2026-05-18 15:00", "airline": "Air France", "flightNumber": "AF276", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Japan Airlines", "flightNumber": "JL048", "departureTime": "2026-05-18 12:00", "arrivalTime": "2026-05-18 17:00"}},
    "CDG-ICN": {"itineraryId": 40, "totalCost": 880, "totalDuration": "11h 30m", "legs": [{"from": "CDG", "to": "ICN", "departureTime": "2026-05-10 13:00", "arrivalTime": "2026-05-11 07:30", "airline": "Air France", "flightNumber": "AF267", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Korean Air", "flightNumber": "KE902", "departureTime": "2026-05-10 15:00", "arrivalTime": "2026-05-11 09:30"}},
    "ICN-CDG": {"itineraryId": 41, "totalCost": 880, "totalDuration": "11h 30m", "legs": [{"from": "ICN", "to": "CDG", "departureTime": "2026-05-18 09:00", "arrivalTime": "2026-05-18 15:30", "airline": "Korean Air", "flightNumber": "KE901", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Air France", "flightNumber": "AF268", "departureTime": "2026-05-18 11:00", "arrivalTime": "2026-05-18 17:30"}},
    # ---- ICN ↔ NRT (reverse) ----
    "ICN-NRT": {"itineraryId": 42, "totalCost": 320, "totalDuration": "2h 30m", "legs": [{"from": "ICN", "to": "NRT", "departureTime": "2026-05-14 14:00", "arrivalTime": "2026-05-14 16:30", "airline": "Korean Air", "flightNumber": "KE705", "layoverMinutes": 0, "riskyLayoverWarning": False}], "backupFlight": {"airline": "Asiana", "flightNumber": "OZ103", "departureTime": "2026-05-14 16:00", "arrivalTime": "2026-05-14 18:30"}},
}

# Single-Leg Flight Search
@app.get("/api/flights/search")
def search_flights(
    origin: str,
    destination: str,
    departureDate: str,
    x_tenant_id: str = Header(None)
):
    """Search for a single flight leg between two cities."""
    check_tenant(x_tenant_id)

    route_key = f"{origin.upper()}-{destination.upper()}"
    flight = FLIGHT_DATA.get(route_key)

    preferred_airline = "Japan Airlines" if x_tenant_id == "1" else "Korean Air"

    if not flight:
        return {
            "tenant": x_tenant_id,
            "origin": origin,
            "destination": destination,
            "departureDate": departureDate,
            "preferredAirline": preferred_airline,
            "message": f"No flights found for route {origin.upper()} → {destination.upper()}.",
            "results": []
        }

    # apply tenant preferred airline prioritization (AC 3.10)
    results = [flight]
    results.sort(
        key=lambda f: any(
            leg["airline"] == preferred_airline for leg in f["legs"]
        ),
        reverse=True
    )

    return {
        "tenant": x_tenant_id,
        "origin": origin,
        "destination": destination,
        "departureDate": departureDate,
        "preferredAirline": preferred_airline,
        "results": results
    }


#this for Multi-City Flight Search

class FlightLeg(BaseModel):
    """Represents one leg of a multi-city trip."""
    origin: str
    destination: str
    departureDate: str

class MultiCityFlightRequest(BaseModel):
    """Request body for a multi-city flight search."""
    legs: List[FlightLeg]

@app.post("/api/flights/multi-city")
def search_multi_city_flights(
    request: MultiCityFlightRequest,
    x_tenant_id: str = Header(None)
):
    """
    Search flights for a multi-city trip in a single request.
    Accepts a list of legs (origin, destination, departureDate).
    Example: SFO→NRT, NRT→ICN, ICN→SFO
    Returns each leg's flight options, total trip cost, and risky layover warnings.
    """
    check_tenant(x_tenant_id)

    if len(request.legs) < 2:
        raise HTTPException(
            status_code=400,
            detail="Multi-city search requires at least 2 legs."
        )

    preferred_airline = "Japan Airlines" if x_tenant_id == "1" else "Korean Air"

    trip_legs = []
    total_trip_cost = 0
    has_risky_layover = False
    failed_segments = []

    for leg in request.legs:
        route_key = f"{leg.origin.upper()}-{leg.destination.upper()}"
        flight = FLIGHT_DATA.get(route_key)

        if not flight:
            # AC 3.9: if one leg fails, show error for that segment but continue
            failed_segments.append({
                "origin": leg.origin.upper(),
                "destination": leg.destination.upper(),
                "departureDate": leg.departureDate,
                "error": f"No flight data found for {leg.origin.upper()} → {leg.destination.upper()}"
            })
            continue

        # check for risky layovers (AC 3.4: layover under 60 minutes)
        for flight_leg in flight["legs"]:
            if flight_leg.get("layoverMinutes", 0) > 0 and flight_leg["layoverMinutes"] < 60:
                has_risky_layover = True

        total_trip_cost += flight["totalCost"]

        trip_legs.append({
            "origin": leg.origin.upper(),
            "destination": leg.destination.upper(),
            "departureDate": leg.departureDate,
            "flight": flight
        })

    if not trip_legs:
        return {
            "tenant": x_tenant_id,
            "preferredAirline": preferred_airline,
            "message": "No valid flight legs found for this multi-city trip.",
            "totalTripCost": 0,
            "riskyLayoverDetected": False,
            "legs": [],
            "failedSegments": failed_segments
        }

    return {
        "tenant": x_tenant_id,
        "preferredAirline": preferred_airline,
        "totalTripCost": total_trip_cost,
        "totalLegs": len(trip_legs),
        "riskyLayoverDetected": has_risky_layover,  # AC 3.4
        "legs": trip_legs,
        "failedSegments": failed_segments  # AC 3.9
    }


#Hotel Search
@app.get("/api/hotels/search")
def search_hotels(
    city: str,
    maxPrice: float = None,
    minRating: float = None,
    tag: str = None,
    x_tenant_id: str = Header(None)
):
    """Search hotels by city with optional filters: maxPrice, minRating, tag."""
    check_tenant(x_tenant_id)

    hotels = [
        {
            "name": "Tokyo Modern Hotel",
            "city": "Tokyo",
            "pricePerNight": 150,
            "nights": 3,
            "totalStayCost": 450,
            "distanceFromReferenceKm": 1.2,
            "rating": 4.5,
            "tags": ["modern", "scenic"],
            "featuredForTenant": x_tenant_id == "1"
        },
        {
            "name": "Tokyo Budget Inn",
            "city": "Tokyo",
            "pricePerNight": 80,
            "nights": 3,
            "totalStayCost": 240,
            "distanceFromReferenceKm": 3.5,
            "rating": 3.8,
            "tags": ["budget", "simple"],
            "featuredForTenant": False
        },
        {
            "name": "Tokyo Scenic Suites",
            "city": "Tokyo",
            "pricePerNight": 200,
            "nights": 3,
            "totalStayCost": 600,
            "distanceFromReferenceKm": 0.8,
            "rating": 4.7,
            "tags": ["luxury", "scenic", "modern"],
            "featuredForTenant": False
        },
        {
            "name": "Seoul Luxury View Hotel",
            "city": "Seoul",
            "pricePerNight": 220,
            "nights": 3,
            "totalStayCost": 660,
            "distanceFromReferenceKm": 1.0,
            "rating": 4.8,
            "tags": ["luxury", "featured"],
            "featuredForTenant": x_tenant_id == "2"
        },
        {
            "name": "Seoul Budget Stay",
            "city": "Seoul",
            "pricePerNight": 70,
            "nights": 3,
            "totalStayCost": 210,
            "distanceFromReferenceKm": 4.0,
            "rating": 3.6,
            "tags": ["budget", "simple"],
            "featuredForTenant": False
        },
        {
            "name": "Seoul Central Inn",
            "city": "Seoul",
            "pricePerNight": 130,
            "nights": 3,
            "totalStayCost": 390,
            "distanceFromReferenceKm": 1.5,
            "rating": 4.3,
            "tags": ["modern", "scenic"],
            "featuredForTenant": False
        },
        {"name": "Hôtel Plaza Athénée", "city": "Paris", "pricePerNight": 820, "nights": 3, "totalStayCost": 2460, "distanceFromReferenceKm": 0.5, "rating": 4.9, "tags": ["luxury", "scenic"], "featuredForTenant": x_tenant_id == "1"},
        {"name": "Le Marais Boutique Hotel", "city": "Paris", "pricePerNight": 340, "nights": 3, "totalStayCost": 1020, "distanceFromReferenceKm": 1.2, "rating": 4.6, "tags": ["modern", "scenic"], "featuredForTenant": False},
        {"name": "Novotel Paris Centre", "city": "Paris", "pricePerNight": 210, "nights": 3, "totalStayCost": 630, "distanceFromReferenceKm": 2.1, "rating": 4.3, "tags": ["modern"], "featuredForTenant": False},
        {"name": "The Savoy", "city": "London", "pricePerNight": 900, "nights": 3, "totalStayCost": 2700, "distanceFromReferenceKm": 0.8, "rating": 4.9, "tags": ["luxury", "scenic"], "featuredForTenant": x_tenant_id == "1"},
        {"name": "Marriott London Grosvenor Square", "city": "London", "pricePerNight": 480, "nights": 3, "totalStayCost": 1440, "distanceFromReferenceKm": 1.5, "rating": 4.7, "tags": ["modern", "luxury"], "featuredForTenant": False},
        {"name": "Premier Inn London City", "city": "London", "pricePerNight": 160, "nights": 3, "totalStayCost": 480, "distanceFromReferenceKm": 3.0, "rating": 4.2, "tags": ["budget"], "featuredForTenant": False},
        {"name": "The Plaza Hotel", "city": "New York", "pricePerNight": 850, "nights": 3, "totalStayCost": 2550, "distanceFromReferenceKm": 0.3, "rating": 4.8, "tags": ["luxury", "scenic"], "featuredForTenant": x_tenant_id == "2"},
        {"name": "Marriott Marquis Times Square", "city": "New York", "pricePerNight": 520, "nights": 3, "totalStayCost": 1560, "distanceFromReferenceKm": 0.5, "rating": 4.6, "tags": ["modern", "luxury"], "featuredForTenant": False},
        {"name": "Pod 51 Hotel", "city": "New York", "pricePerNight": 190, "nights": 3, "totalStayCost": 570, "distanceFromReferenceKm": 2.0, "rating": 4.2, "tags": ["budget", "modern"], "featuredForTenant": False},
        {"name": "Shutters on the Beach", "city": "Los Angeles", "pricePerNight": 780, "nights": 3, "totalStayCost": 2340, "distanceFromReferenceKm": 0.1, "rating": 4.8, "tags": ["luxury", "scenic"], "featuredForTenant": x_tenant_id == "2"},
        {"name": "The LINE LA", "city": "Los Angeles", "pricePerNight": 310, "nights": 3, "totalStayCost": 930, "distanceFromReferenceKm": 1.8, "rating": 4.5, "tags": ["modern", "scenic"], "featuredForTenant": False},
        {"name": "Freehand Los Angeles", "city": "Los Angeles", "pricePerNight": 200, "nights": 3, "totalStayCost": 600, "distanceFromReferenceKm": 2.5, "rating": 4.3, "tags": ["budget", "modern"], "featuredForTenant": False},
        {"name": "Four Seasons San Francisco", "city": "San Francisco", "pricePerNight": 750, "nights": 3, "totalStayCost": 2250, "distanceFromReferenceKm": 0.4, "rating": 4.8, "tags": ["luxury", "scenic"], "featuredForTenant": x_tenant_id == "1"},
        {"name": "Hotel Zephyr Fisherman's Wharf", "city": "San Francisco", "pricePerNight": 280, "nights": 3, "totalStayCost": 840, "distanceFromReferenceKm": 1.5, "rating": 4.4, "tags": ["modern", "scenic"], "featuredForTenant": False},
        {"name": "The Mosser Hotel", "city": "San Francisco", "pricePerNight": 150, "nights": 3, "totalStayCost": 450, "distanceFromReferenceKm": 2.0, "rating": 4.1, "tags": ["budget"], "featuredForTenant": False},
    ]

    # filter by city
    results = [h for h in hotels if h["city"].lower() == city.lower()]
    # filter by max price per night
    if maxPrice is not None:
        results = [h for h in results if h["pricePerNight"] <= maxPrice]
    # filter by min rating
    if minRating is not None:
        results = [h for h in results if h["rating"] >= minRating]
    # filter by tag
    if tag:
        results = [h for h in results if tag.lower() in [t.lower() for t in h["tags"]]]
    # featured hotels appear first (AC 4.5)
    results.sort(key=lambda h: h["featuredForTenant"], reverse=True)

    return {
        "tenant": x_tenant_id,
        "city": city,
        "results": results
    }


# Attraction Search
@app.get("/api/attractions/search")
def search_attractions(
    city: str,
    category: str = None,
    maxPrice: float = None,
    x_tenant_id: str = Header(None)
):
    """Search attractions by city with optional filters: category, maxPrice."""
    check_tenant(x_tenant_id)

    attractions = [
        {"name": "Shibuya Crossing", "city": "Tokyo", "category": "landmark", "price": 0, "rating": 4.7},
        {"name": "Tokyo Tower", "city": "Tokyo", "category": "landmark", "price": 20, "rating": 4.6},
        {"name": "Senso-ji Temple", "city": "Tokyo", "category": "history", "price": 0, "rating": 4.8},
        {"name": "Tsukiji Fish Market", "city": "Tokyo", "category": "food", "price": 0, "rating": 4.5},
        {"name": "Gyeongbokgung Palace", "city": "Seoul", "category": "history", "price": 5, "rating": 4.8},
        {"name": "Bukchon Hanok Village", "city": "Seoul", "category": "landmark", "price": 0, "rating": 4.6},
        {"name": "Myeongdong Street Food", "city": "Seoul", "category": "food", "price": 10, "rating": 4.5},
        {"name": "Eiffel Tower", "city": "Paris", "category": "landmark", "price": 28, "rating": 4.7},
        {"name": "Louvre Museum", "city": "Paris", "category": "history", "price": 17, "rating": 4.8},
        {"name": "Seine River Cruise", "city": "Paris", "category": "scenic", "price": 15, "rating": 4.6},
        {"name": "Montmartre Walk", "city": "Paris", "category": "landmark", "price": 0, "rating": 4.5},
        {"name": "Tower of London", "city": "London", "category": "history", "price": 30, "rating": 4.7},
        {"name": "British Museum", "city": "London", "category": "history", "price": 0, "rating": 4.8},
        {"name": "Thames River Cruise", "city": "London", "category": "scenic", "price": 20, "rating": 4.5},
        {"name": "Buckingham Palace", "city": "London", "category": "landmark", "price": 0, "rating": 4.6},
        {"name": "Statue of Liberty", "city": "New York", "category": "landmark", "price": 24, "rating": 4.7},
        {"name": "Metropolitan Museum of Art", "city": "New York", "category": "history", "price": 30, "rating": 4.8},
        {"name": "Central Park", "city": "New York", "category": "landmark", "price": 0, "rating": 4.9},
        {"name": "Broadway Show", "city": "New York", "category": "food", "price": 120, "rating": 4.8},
        {"name": "Venice Beach", "city": "Los Angeles", "category": "landmark", "price": 0, "rating": 4.5},
        {"name": "Getty Museum", "city": "Los Angeles", "category": "history", "price": 0, "rating": 4.7},
        {"name": "Hollywood Walk of Fame", "city": "Los Angeles", "category": "landmark", "price": 0, "rating": 4.4},
        {"name": "Universal Studios", "city": "Los Angeles", "category": "food", "price": 109, "rating": 4.6},
        {"name": "Golden Gate Bridge", "city": "San Francisco", "category": "landmark", "price": 0, "rating": 4.9},
        {"name": "Alcatraz Island", "city": "San Francisco", "category": "history", "price": 43, "rating": 4.7},
        {"name": "Fisherman's Wharf", "city": "San Francisco", "category": "food", "price": 0, "rating": 4.5},
        {"name": "Cable Car Ride", "city": "San Francisco", "category": "scenic", "price": 8, "rating": 4.6},
    ]

    results = [a for a in attractions if a["city"].lower() == city.lower()]

    if category:
        results = [a for a in results if a["category"].lower() == category.lower()]

    if maxPrice is not None:
        results = [a for a in results if a["price"] <= maxPrice]

    return {
        "tenant": x_tenant_id,
        "city": city,
        "results": results
    }


#Booking Models
class BookingStatus(str, Enum):
    # three lifecycle states of a booking
    pending = "Pending"
    confirmed = "Confirmed"
    cancelled = "Cancelled"

class BookingCreate(BaseModel):
    """Schema for creating a new booking."""
    user_id: int
    booking_type: str
    name: str
    city: str
    total_cost: float

class BookingStatusUpdate(BaseModel):
    """Schema for updating booking status."""
    status: BookingStatus


# Booking Endpoints
@app.post("/api/bookings")
def create_booking(
    booking: BookingCreate,
    x_tenant_id: str = Header(None),
    db: Session = Depends(get_db)
):
    """Create and persist a new booking in the database."""
    check_tenant(x_tenant_id)

    # verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == int(x_tenant_id)).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # verify user belongs to this tenant
    user = db.query(User).filter(
        User.id == booking.user_id,
        User.tenant_id == int(x_tenant_id)
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found for this tenant")

    new_booking = Booking(
        tenant_id=int(x_tenant_id),
        user_id=booking.user_id,
        booking_type=booking.booking_type,
        name=booking.name,
        city=booking.city,
        total_cost=booking.total_cost,
        status=BookingStatus.pending.value
    )

    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    return {
        "message": "Booking saved successfully",
        "booking": {
            "id": new_booking.id,
            "tenant_id": new_booking.tenant_id,
            "user_id": new_booking.user_id,
            "booking_type": new_booking.booking_type,
            "name": new_booking.name,
            "city": new_booking.city,
            "total_cost": new_booking.total_cost,
            "status": new_booking.status,
            "created_at": new_booking.created_at
        }
    }


@app.get("/api/bookings")
def list_bookings(
    user_id: int = None,
    x_tenant_id: str = Header(None),
    db: Session = Depends(get_db)
):
    """List all bookings for a tenant, optionally filtered by user_id."""
    check_tenant(x_tenant_id)

    query = db.query(Booking).filter(Booking.tenant_id == int(x_tenant_id))

    if user_id is not None:
        query = query.filter(Booking.user_id == user_id)

    bookings = query.order_by(Booking.id.desc()).all()

    return {
        "tenant": x_tenant_id,
        "count": len(bookings),
        "results": [
            {
                "id": b.id,
                "tenant_id": b.tenant_id,
                "user_id": b.user_id,
                "booking_type": b.booking_type,
                "name": b.name,
                "city": b.city,
                "total_cost": b.total_cost,
                "status": b.status,
                "created_at": b.created_at
            }
            for b in bookings
        ]
    }


@app.get("/api/bookings/{booking_id}")
def get_booking(
    booking_id: int,
    x_tenant_id: str = Header(None),
    db: Session = Depends(get_db)
):
    """Retrieve a single booking by ID, scoped to the tenant."""
    check_tenant(x_tenant_id)

    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.tenant_id == int(x_tenant_id)
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    return {
        "id": booking.id,
        "tenant_id": booking.tenant_id,
        "user_id": booking.user_id,
        "booking_type": booking.booking_type,
        "name": booking.name,
        "city": booking.city,
        "total_cost": booking.total_cost,
        "status": booking.status,
        "created_at": booking.created_at
    }


@app.patch("/api/bookings/{booking_id}/status")
def update_booking_status(
    booking_id: int,
    payload: BookingStatusUpdate,
    x_tenant_id: str = Header(None),
    db: Session = Depends(get_db)
):
    """Update the status of a booking (Pending → Confirmed or Cancelled)."""
    check_tenant(x_tenant_id)

    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.tenant_id == int(x_tenant_id)
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # cancelled bookings cannot be modified
    if booking.status == BookingStatus.cancelled.value:
        raise HTTPException(status_code=400, detail="Cancelled booking cannot be changed")

    booking.status = payload.status.value
    db.commit()
    db.refresh(booking)

    return {
        "message": "Booking status updated successfully",
        "booking": {
            "id": booking.id,
            "status": booking.status
        }
    }


@app.post("/api/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: int,
    x_tenant_id: str = Header(None),
    db: Session = Depends(get_db)
):
    """Cancel a booking by setting its status to Cancelled."""
    check_tenant(x_tenant_id)

    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.tenant_id == int(x_tenant_id)
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.status = BookingStatus.cancelled.value
    db.commit()
    db.refresh(booking)

    return {
        "message": "Booking cancelled successfully",
        "booking": {
            "id": booking.id,
            "status": booking.status
        }
    }


# Single-City Recommendation
@app.get("/api/recommendations")
def get_recommendations(
    city: str,
    budget: float,
    origin: str = "SFO",
    departureDate: str = "2026-05-10",
    minRating: float = 0,
    maxHotelPrice: float = None,
    tag: str = None,
    x_tenant_id: str = Header(None)
):
    """
    Build and rank the top 3 travel packages (flight + hotel) within the user's budget.
    The user provides a city, budget, and optional filters.
    The system finds all valid flight+hotel combinations that fit the budget,
    scores them by value, rating, and distance, and returns the top 3 ranked packages.
    """
    check_tenant(x_tenant_id)

    if budget <= 0:
        return {
            "tenant": x_tenant_id,
            "city": city,
            "budget": budget,
            "message": "Budget must be greater than 0.",
            "results": []
        }

    try:
        flight_response = search_flights(
            origin=origin,
            destination=city,
            departureDate=departureDate,
            x_tenant_id=x_tenant_id
        )
        hotel_response = search_hotels(
            city=city,
            maxPrice=maxHotelPrice,
            minRating=minRating,
            tag=tag,
            x_tenant_id=x_tenant_id
        )
        attraction_response = search_attractions(
            city=city,
            x_tenant_id=x_tenant_id
        )

        flights = flight_response.get("results", [])
        hotels = hotel_response.get("results", [])
        # always include top 3 attractions (project spec requirement)
        top_attractions = attraction_response.get("results", [])[:3]

        recommended_packages = []

        # build all flight + hotel combinations within budget
        for flight in flights:
            for hotel in hotels:
                total_cost = flight["totalCost"] + hotel["totalStayCost"]

                if total_cost <= budget:
                    # scoring: reward budget savings, high rating, proximity, featured status
                    score = 0
                    score += (budget - total_cost) * 0.5         # budget efficiency
                    score += hotel["rating"] * 100               # hotel quality
                    score += max(0, 50 - hotel["distanceFromReferenceKm"] * 10)  # proximity
                    if hotel["featuredForTenant"]:
                        score += 75                              # tenant featured boost (AC 4.5)

                    recommended_packages.append({
                        "flight": flight,
                        "hotel": hotel,
                        "suggestedAttractions": top_attractions,
                        "totalPackageCost": round(total_cost, 2),
                        "remainingBudget": round(budget - total_cost, 2),
                        "recommendationScore": round(score, 2)
                    })

        # rank by score descending
        recommended_packages.sort(
            key=lambda p: p["recommendationScore"],
            reverse=True
        )

        # return top 3 packages
        top_packages = recommended_packages[:3]

        if not top_packages:
            return {
                "tenant": x_tenant_id,
                "city": city,
                "budget": budget,
                "message": "No matching travel packages found within your budget.",
                "results": []
            }

        return {
            "tenant": x_tenant_id,
            "city": city,
            "budget": budget,
            "totalPackagesFound": len(recommended_packages),
            "bestRecommendation": top_packages[0],
            "top3Packages": top_packages
        }

    except Exception:
        raise HTTPException(status_code=500, detail="Recommendation service failed.")


def _adjust_flight_dates(flight: dict, base_date_str: str) -> dict:
    """Return a deep copy of a FLIGHT_DATA entry with dates replaced by base_date_str.
    Preserves the same-day vs next-day arrival offset from the original data."""
    import copy
    flight = copy.deepcopy(flight)
    base = datetime.strptime(base_date_str, "%Y-%m-%d").date()
    for leg in flight.get("legs", []):
        try:
            orig_dep = datetime.strptime(leg["departureTime"], "%Y-%m-%d %H:%M")
            orig_arr = datetime.strptime(leg["arrivalTime"], "%Y-%m-%d %H:%M")
            day_diff = (orig_arr.date() - orig_dep.date()).days
            leg["departureTime"] = f"{base} {orig_dep.strftime('%H:%M')}"
            leg["arrivalTime"] = f"{base + timedelta(days=day_diff)} {orig_arr.strftime('%H:%M')}"
        except (ValueError, KeyError):
            pass
    if "backupFlight" in flight:
        bf = flight["backupFlight"]
        try:
            orig_dep = datetime.strptime(bf["departureTime"], "%Y-%m-%d %H:%M")
            bf["departureTime"] = f"{base} {orig_dep.strftime('%H:%M')}"
        except (ValueError, KeyError):
            pass
    return flight


#Multi-City Budget Package Builder
class MultiCityPackageRequest(BaseModel):
    """
    Request body for building a full multi-city travel package within a budget.
    The user provides a list of cities to visit, the budget, and optional hotel filters.
    The system constructs a complete package: all flights + one hotel per city.
    """
    cities: List[str]      # ordered list of destination cities e.g. ["Tokyo", "Seoul"]
    origin_iata: str   # starting airport IATA code e.g. "SFO"
    return_iata: str        # return airport IATA code e.g. "SFO"
    departure_date: str   # first departure date e.g. "2026-05-10"
    budget: float    # total budget in USD
    nights_per_city: int = 3     # how many nights to stay per city
    adults: int = 1          # number of travellers (used to multiply attraction costs)
    minRating: float = 0   # minimum hotel rating filter
    maxHotelPricePerNight: float = None   # max hotel price per night filter

@app.post("/api/packages/multi-city")
def build_multi_city_package(
    request: MultiCityPackageRequest,
    x_tenant_id: str = Header(None)
):
    """
    Build a complete multi-city travel package within the user's budget.

    Given a list of cities, an origin, a return airport, and a total budget,
    this endpoint:
      1. Constructs all flight legs (origin → city1 → city2 → ... → return)
      2. Finds hotels in each destination city
      3. Builds every combination of flights + hotels across all cities
      4. Filters combinations that fit within the total budget
      5. Returns the top 3 ranked packages sorted by recommendation score

    Example: origin=SFO, cities=[Tokyo, Seoul], return=SFO
    Legs generated: SFO→NRT, NRT→ICN, ICN→SFO
    """
    check_tenant(x_tenant_id)

    if request.budget <= 0:
        raise HTTPException(status_code=400, detail="Budget must be greater than 0.")
    if len(request.cities) < 1:
        raise HTTPException(status_code=400, detail="At least one destination city is required.")

    # Maps city names  to airport codes used in FLIGHT_DATA keys
    #Any city not in this map causes an immediate 400 response
    CITY_TO_IATA = {
        "tokyo": "NRT",
        "seoul": "ICN",
        "paris": "CDG",
        "london": "LHR",
        "new york": "JFK",
        "los angeles": "LAX",
        "san francisco": "SFO"
    }

    preferred_airline = "Japan Airlines" if x_tenant_id == "1" else "Korean Air"

    # Step 1: Build the ordered list of IATA codes for the trip
    iata_stops = [request.origin_iata.upper()]
    city_iata_map = {}  # city name → IATA for later hotel matching

    for city in request.cities:
        iata = CITY_TO_IATA.get(city.lower())
        if not iata:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown city '{city}'. Supported cities: {list(CITY_TO_IATA.keys())}"
            )
        iata_stops.append(iata)
        city_iata_map[city.lower()] = iata

    iata_stops.append(request.return_iata.upper())

    #Step 2: Fetch all flight legs with dynamic dates
    flight_legs = []
    failed_legs = []
    base_flight_cost = 0
    trip_start = datetime.strptime(request.departure_date, "%Y-%m-%d")
    # Each city visit is nights_per_city days; the final (return) leg departs after all cities.
    num_cities = len(request.cities)
    return_date = (trip_start + timedelta(days=num_cities * request.nights_per_city)).strftime("%Y-%m-%d")

    for i in range(len(iata_stops) - 1):
        origin = iata_stops[i]
        destination = iata_stops[i + 1]
        route_key = f"{origin}-{destination}"
        flight = FLIGHT_DATA.get(route_key)

        # Leg i departs after i city stays; the last leg (return) departs after all cities.
        leg_day_offset = i * request.nights_per_city
        leg_date = (trip_start + timedelta(days=leg_day_offset)).strftime("%Y-%m-%d")

        if not flight:
            failed_legs.append({
                "origin": origin,
                "destination": destination,
                "error": f"No flight data for {origin} → {destination}"
            })
        else:
            base_flight_cost += flight["totalCost"]
            flight_legs.append({
                "origin": origin,
                "destination": destination,
                "departureDate": leg_date,
                "flight": _adjust_flight_dates(flight, leg_date),
            })

    if not flight_legs:
        return {
            "tenant": x_tenant_id,
            "budget": request.budget,
            "message": "No valid flight legs found for this multi-city route.",
            "failedLegs": failed_legs,
            "top3Packages": []
        }

    #Step 3: Fetch hotels for each destination city
    city_hotels = {}
    for city in request.cities:
        hotel_response = search_hotels(
            city=city,
            maxPrice=request.maxHotelPricePerNight,
            minRating=request.minRating,
            x_tenant_id=x_tenant_id
        )
        hotels = hotel_response.get("results", [])

        # adjust hotel cost to match nights_per_city
        for h in hotels:
            h["nights"] = request.nights_per_city
            h["totalStayCost"] = round(h["pricePerNight"] * request.nights_per_city, 2)

        city_hotels[city.lower()] = hotels

    # ---- Step 4: Get top 3 attractions per city and their total cost ----
    city_attractions = {}
    city_attraction_costs = {}
    for city in request.cities:
        attraction_response = search_attractions(city=city, x_tenant_id=x_tenant_id)
        top3 = attraction_response.get("results", [])[:3]
        city_attractions[city.lower()] = top3
        city_attraction_costs[city.lower()] = round(
            sum(a.get("price", 0) for a in top3) * request.adults, 2
        )

    # Step 5: Build all hotel combinations across cities 
    # Use recursive combination builder
    def build_hotel_combinations(cities, city_hotels):
        """Generate all combinations of one hotel per city."""
        if not cities:
            return [[]]
        city = cities[0]
        rest = cities[1:]
        hotels = city_hotels.get(city.lower(), [])
        if not hotels:
            return [[{"city": city, "hotel": None}] + combo for combo in build_hotel_combinations(rest, city_hotels)]
        combinations = []
        for hotel in hotels:
            for combo in build_hotel_combinations(rest, city_hotels):
                combinations.append([{"city": city, "hotel": hotel}] + combo)
        return combinations

    hotel_combinations = build_hotel_combinations(request.cities, city_hotels)

    # Step 6: Score and filter packages within budget 
    packages = []

    for hotel_combo in hotel_combinations:
        # total hotel cost across all cities
        hotel_total = sum(
            entry["hotel"]["totalStayCost"]
            for entry in hotel_combo
            if entry["hotel"] is not None
        )
        attraction_total = sum(
            city_attraction_costs.get(entry["city"].lower(), 0)
            for entry in hotel_combo
        )
        total_package_cost = base_flight_cost + hotel_total + attraction_total

        if total_package_cost > request.budget:
            continue  # skip packages over budget

        # scoring
        score = 0
        score += (request.budget - total_package_cost) * 0.5  # budget efficiency

        for entry in hotel_combo:
            if entry["hotel"]:
                score += entry["hotel"]["rating"] * 100
                score += max(0, 50 - entry["hotel"]["distanceFromReferenceKm"] * 10)
                if entry["hotel"]["featuredForTenant"]:
                    score += 75

        # attach attractions per city with their cost
        city_breakdown = []
        for entry in hotel_combo:
            city_name = entry["city"]
            city_breakdown.append({
                "city": city_name,
                "hotel": entry["hotel"],
                "suggestedAttractions": city_attractions.get(city_name.lower(), []),
                "attractionCost": city_attraction_costs.get(city_name.lower(), 0),
            })

        packages.append({
            "flightLegs": flight_legs,
            "departureDate": request.departure_date,
            "returnDate": return_date,
            "totalFlightCost": round(base_flight_cost, 2),
            "cityBreakdown": city_breakdown,
            "totalHotelCost": round(hotel_total, 2),
            "totalAttractionCost": round(attraction_total, 2),
            "totalPackageCost": round(total_package_cost, 2),
            "remainingBudget": round(request.budget - total_package_cost, 2),
            "recommendationScore": round(score, 2),
            "riskyLayoverDetected": any(
                leg["flight"]["legs"][0].get("riskyLayoverWarning", False)
                for leg in flight_legs
            ),
            "failedFlightLegs": failed_legs
        })

    #we rank by score
    packages.sort(key=lambda p: p["recommendationScore"], reverse=True)
    top_packages = packages[:3]

    if not top_packages:
        return {
            "tenant": x_tenant_id,
            "cities": request.cities,
            "budget": request.budget,
            "totalFlightCost": round(base_flight_cost, 2),
            "message": "No complete travel packages found within your budget. Try increasing your budget or adjusting hotel filters.",
            "failedFlightLegs": failed_legs,
            "top3Packages": []
        }

    return {
        "tenant": x_tenant_id,
        "preferredAirline": preferred_airline,
        "cities": request.cities,
        "budget": request.budget,
        "totalPackagesEvaluated": len(packages),
        "bestPackage": top_packages[0],
        "top3Packages": top_packages,
        "failedFlightLegs": failed_legs
    }