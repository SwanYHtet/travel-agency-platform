import random
import re

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.rapidapi_client import RapidApiError, get_rapidapi_client
from app.services.rapidapi_service import RapidApiService

router = APIRouter(prefix="", tags=["rapidapi"])

def get_rapidapi_service() -> RapidApiService:
    return RapidApiService(get_rapidapi_client())


# ---------------------------------------------------------------------------
# Mock data helpers
#
# The template ships with RAPIDAPI_KEY={YOUR_API_KEY} as a literal placeholder.
# Every real request therefore returns HTTP 401, which the client raises as
# RapidApiError. The helpers below produce deterministic fake results seeded
# by destination + date so the same search always returns the same data.
# The mock shapes exactly match what flightService.js / hotelService.js parse.
# ---------------------------------------------------------------------------

_AIRLINES = [
    ("AA", "American Airlines"),
    ("UA", "United Airlines"),
    ("DL", "Delta Air Lines"),
    ("SW", "Southwest Airlines"),
    ("BA", "British Airways"),
    ("LH", "Lufthansa"),
    ("EK", "Emirates"),
    ("SQ", "Singapore Airlines"),
    ("QF", "Qantas"),
    ("AF", "Air France"),
]

_HOTELS = [
    "Grand Hyatt",
    "Marriott Hotel",
    "Hilton Downtown",
    "Sheraton Resort",
    "Westin Hotel",
    "InterContinental",
    "Radisson Blu",
    "Four Seasons",
    "Ritz-Carlton",
    "Holiday Inn",
]

_ACTIVITIES = [
    ("City Walking Tour", "Tours", 29.99, 4.7, "3 hours"),
    ("Museum of Modern Art", "Culture", 25.00, 4.5, "2 hours"),
    ("Sunset Harbor Cruise", "Water", 59.99, 4.8, "2 hours"),
    ("Food & Wine Tasting", "Food", 75.00, 4.6, "3 hours"),
    ("Bike City Tour", "Sports", 35.00, 4.4, "2.5 hours"),
    ("Historical District Walk", "Tours", 19.99, 4.3, "2 hours"),
    ("Cooking Class", "Food", 89.00, 4.9, "3.5 hours"),
    ("Rooftop Bar Experience", "Nightlife", 45.00, 4.5, "2 hours"),
    ("Day Hiking Trip", "Nature", 55.00, 4.7, "6 hours"),
    ("Kayaking Adventure", "Water", 65.00, 4.6, "3 hours"),
]


def _airport_from_code(code: str) -> str:
    # The frontend sends codes like "SFO.AIRPORT" or "NYC.CITY" — strip the suffix
    # so mock data uses plain 3-letter IATA codes in token/route keys.
    return re.sub(r"\.(AIRPORT|CITY|ALL)$", "", code.upper()).strip()


def _make_flight_offer(index: int, from_code: str, to_code: str, depart_date: str,
                       adults: int, base_seed: int) -> dict:
    rng = random.Random(base_seed + index)
    airline_code, airline_name = _AIRLINES[index % len(_AIRLINES)]
    flight_num = rng.randint(100, 9999)
    dep_hour = rng.randint(6, 20)
    dep_min = rng.choice([0, 15, 30, 45])
    dur_min = rng.randint(90, 720)
    arr_hour = (dep_hour + dur_min // 60) % 24
    arr_min = (dep_min + dur_min % 60) % 60
    price = round(rng.uniform(150, 1800) * adults, 2)
    stops = rng.choice([0, 0, 0, 1, 1, 2])

    depart_dt = f"{depart_date}T{dep_hour:02d}:{dep_min:02d}:00"
    arrive_dt = f"{depart_date}T{arr_hour:02d}:{arr_min:02d}:00"

    return {
        "token": f"FL-{from_code}-{to_code}-{index}",
        "segments": [
            {
                "departureTime": depart_dt,
                "arrivalTime": arrive_dt,
                "totalTime": dur_min * 60,
                "departureAirport": {"code": from_code, "name": f"{from_code} Airport"},
                "arrivalAirport": {"code": to_code, "name": f"{to_code} Airport"},
                "legs": [
                    {
                        "carriersData": [{"name": airline_name, "code": airline_code}],
                        "flightInfo": {
                            "flightNumber": flight_num,
                            "planeType": rng.choice(["Boeing 737", "Airbus A320", "Boeing 777", "Airbus A380"]),
                            "carrierInfo": {"marketingCarrier": airline_code},
                        },
                        "cabinClass": "ECONOMY",
                    }
                ],
            }
        ],
        "priceBreakdown": {
            "total": {"units": price, "currencyCode": "USD"},
        },
        "unifiedPriceBreakdown": {
            "price": {"units": price, "currencyCode": "USD"},
        },
    }


def _make_hotel(index: int, dest_name: str, checkin: str, checkout: str,
                adults: int, base_seed: int) -> dict:
    rng = random.Random(base_seed + index)
    name = f"{dest_name.title()} {_HOTELS[index % len(_HOTELS)]}"
    nightly = round(rng.uniform(80, 500), 2)
    try:
        from datetime import date
        ci = date.fromisoformat(checkin)
        co = date.fromisoformat(checkout)
        nights = max(1, (co - ci).days)
    except Exception:
        nights = 1
    total = round(nightly * nights * adults, 2)

    return {
        "hotel_id": f"HTL-{dest_name[:3].upper()}-{index}",
        "hotel_name": name,
        "class": rng.choice([3, 4, 4, 5]),
        "composite_price_breakdown": {
            "gross_amount": {"value": total, "currency": "USD"},
            "gross_amount_per_night": {"value": nightly, "currency": "USD"},
        },
        "review_score": round(rng.uniform(7.0, 9.9), 1),
        "review_nr": rng.randint(50, 2000),
        "accommodation_type_name": rng.choice(["Hotel", "Resort", "Boutique Hotel"]),
        "is_free_cancellable": rng.choice([True, False]),
        "checkin": {"from": "15:00", "to": "23:00"},
        "checkout": {"from": "07:00", "to": "11:00"},
    }


def _make_activity(index: int, base_seed: int) -> dict:
    rng = random.Random(base_seed + index)
    name, category, price, rating, duration = _ACTIVITIES[index % len(_ACTIVITIES)]
    return {
        "id": f"ACT-{index}",
        "name": name,
        "category": category,
        "price": price,
        "rating": rating,
        "duration": duration,
        "description": f"Enjoy this {category.lower()} experience.",
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/attractions/search")
async def search_attractions(
    start_date: str = Query(..., description="Format: YYYY-MM-DD"),
    end_date: str = Query(..., description="Format: YYYY-MM-DD"),
    dest_name: str = Query(..., description="Example: New York"),
    country_name: str = Query(..., description="Example: United States"),
    locale: str = Query("en-gb"),
    page_number: int = Query(0, ge=0),
    currency: str = Query("AED"),
    order_by: str = Query("attr_book_score"),
    service: RapidApiService = Depends(get_rapidapi_service),
):
    try:
        return service.search_attractions(
            start_date=start_date,
            end_date=end_date,
            dest_name=dest_name,
            country_name=country_name,
            locale=locale,
            page_number=page_number,
            currency=currency,
            order_by=order_by,
        )
    except RapidApiError:
        seed = hash(dest_name + start_date) & 0xFFFFFF
        products = [_make_activity(i, seed) for i in range(10)]
        return {"products": products}


@router.get("/hotels/search")
async def search_hotels(
    page_number: int = Query(0, ge=0),
    dest_type: str = Query("city"),
    dest_name: str = Query(..., description="Example: New York"),
    country_name: str = Query(..., description="Example: United States"),
    units: str = Query("metric"),
    children_number: int = Query(0, ge=0),
    locale: str = Query("en-gb"),
    categories_filter_ids: str | None = Query(None),
    children_ages: str | None = Query(None, description="Comma-separated ages, e.g. 5,0"),
    include_adjacency: bool = Query(True),
    filter_by_currency: str = Query("AED"),
    order_by: str = Query("popularity"),
    checkin_date: str = Query(..., description="Format: YYYY-MM-DD"),
    checkout_date: str = Query(..., description="Format: YYYY-MM-DD"),
    room_number: int = Query(1, ge=1),
    adults_number: int = Query(1, ge=1),
    service: RapidApiService = Depends(get_rapidapi_service),
):
    try:
        return service.search_hotels(
            page_number=page_number,
            dest_type=dest_type,
            dest_name=dest_name,
            country_name=country_name,
            units=units,
            children_number=children_number,
            locale=locale,
            categories_filter_ids=categories_filter_ids,
            children_ages=children_ages,
            include_adjacency=include_adjacency,
            filter_by_currency=filter_by_currency,
            order_by=order_by,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
            room_number=room_number,
            adults_number=adults_number,
        )
    except RapidApiError:
        seed = hash(dest_name + checkin_date) & 0xFFFFFF
        result = [_make_hotel(i, dest_name, checkin_date, checkout_date, adults_number, seed) for i in range(12)]
        return {"result": result}


@router.get("/flights/search")
async def search_flights(
    depart_date: str = Query(..., description="Format: YYYY-MM-DD"),
    from_code: str = Query(..., description="Example: ONT.AIRPORT"),
    to_code: str = Query(..., description="Example: NYC.CITY"),
    adults: int = Query(1, ge=1),
    children: int = Query(0, ge=0),
    children_number: int = Query(0, ge=0),
    locale: str = Query("en-gb"),
    page_number: int = Query(0, ge=0),
    currency: str = Query("AED"),
    order_by: str = Query("BEST"),
    flight_type: str = Query("ONEWAY"),
    cabin_class: str = Query("ECONOMY"),
    children_ages: str | None = Query(None, description="Comma-separated ages, e.g. 5,0"),
    return_date: str | None = Query(None, description="Format: YYYY-MM-DD"),
    service: RapidApiService = Depends(get_rapidapi_service),
):
    try:
        return service.search_flights(
            depart_date=depart_date,
            from_code=from_code,
            to_code=to_code,
            adults=adults,
            locale=locale,
            page_number=page_number,
            currency=currency,
            order_by=order_by,
            flight_type=flight_type,
            cabin_class=cabin_class,
            children_ages=children_ages,
            return_date=return_date,
        )
    except RapidApiError:
        origin = _airport_from_code(from_code)
        dest = _airport_from_code(to_code)
        seed = hash(origin + dest + depart_date) & 0xFFFFFF
        total_pax = max(1, adults + max(children, children_number))
        offers = [_make_flight_offer(i, origin, dest, depart_date, total_pax, seed) for i in range(12)]
        if return_date:
            ret_seed = hash(dest + origin + return_date) & 0xFFFFFF
            ret_offers = [_make_flight_offer(i, dest, origin, return_date, total_pax, ret_seed) for i in range(12)]
            return {"flightOffers": offers, "returnFlightOffers": ret_offers}
        return {"flightOffers": offers}
