# Fuel Route API

A Django REST API that finds the cheapest fuel stops along any US route.

## What it does
- Takes a start and end location within the USA
- Returns the optimal route with cheapest fuel stops every 400 miles
- Calculates total fuel cost based on 10 MPG
- Uses real fuel price data from CSV

## Tech Stack
- Django 6.0.6
- Django REST Framework
- OpenRouteService API (routing + geocoding)
- Pandas (CSV processing)
- Geopy (distance calculations)

## API Usage

**Endpoint:** `POST /api/route/`

**Request:**
```json
{
    "start": "New York, NY",
    "end": "Los Angeles, CA"
}
```

**Response:**
```json
{
    "start": "New York, NY",
    "end": "Los Angeles, CA",
    "total_miles": 2797.3,
    "total_fuel_cost_usd": 958.6,
    "fuel_stops": [...],
    "route_coordinates": [...]
}
```

## Setup
1. Clone the repo
2. Create virtual environment: `python -m venv venv`
3. Activate: `venv\Scripts\activate`
4. Install dependencies: `pip install django djangorestframework pandas geopy requests`
5. Run: `python manage.py runserver`
