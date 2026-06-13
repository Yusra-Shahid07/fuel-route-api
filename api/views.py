import pandas as pd
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from geopy.distance import geodesic
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, 'fuel-prices-for-be-assessment.csv')

df = pd.read_csv(CSV_PATH)
df.columns = df.columns.str.strip()
df['Retail Price'] = pd.to_numeric(df['Retail Price'], errors='coerce')
df = df.dropna(subset=['Retail Price'])
df = df.sort_values('Retail Price').drop_duplicates(subset=['OPIS Truckstop ID'], keep='first')

STATE_COORDS = {
    'AL': (32.8, -86.8), 'AK': (64.2, -153.4), 'AZ': (34.3, -111.1),
    'AR': (34.9, -92.4), 'CA': (36.8, -119.4), 'CO': (39.0, -105.5),
    'CT': (41.6, -72.7), 'DE': (39.0, -75.5), 'FL': (27.8, -81.7),
    'GA': (32.2, -82.9), 'HI': (20.3, -156.4), 'ID': (44.4, -114.5),
    'IL': (40.0, -89.2), 'IN': (39.8, -86.1), 'IA': (42.1, -93.5),
    'KS': (38.5, -98.4), 'KY': (37.7, -84.9), 'LA': (31.2, -91.8),
    'ME': (45.4, -69.0), 'MD': (39.1, -76.8), 'MA': (42.2, -71.5),
    'MI': (44.3, -85.4), 'MN': (46.4, -93.1), 'MS': (32.7, -89.7),
    'MO': (38.5, -92.5), 'MT': (47.0, -110.5), 'NE': (41.5, -99.9),
    'NV': (39.3, -116.6), 'NH': (43.5, -71.6), 'NJ': (40.1, -74.5),
    'NM': (34.8, -106.2), 'NY': (42.2, -74.9), 'NC': (35.6, -79.8),
    'ND': (47.5, -100.5), 'OH': (40.4, -82.8), 'OK': (35.6, -96.9),
    'OR': (44.6, -122.1), 'PA': (40.6, -77.2), 'RI': (41.7, -71.5),
    'SC': (33.9, -80.9), 'SD': (44.4, -100.2), 'TN': (35.9, -86.7),
    'TX': (31.5, -99.3), 'UT': (39.3, -111.1), 'VT': (44.1, -72.7),
    'VA': (37.8, -78.2), 'WA': (47.4, -120.5), 'WV': (38.9, -80.5),
    'WI': (44.3, -89.8), 'WY': (43.0, -107.6), 'DC': (38.9, -77.0),
}

ORS_API_KEY = 'eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjExMDA5YzRlNDk2ZTRkOWZhMzNkZDFlZTU4Yzc5ODljIiwiaCI6Im11cm11cjY0In0='

MPG = 10
REFUEL_AT_MILES = 400


def geocode_ors(place):
    url = "https://api.openrouteservice.org/geocode/search"
    params = {"api_key": ORS_API_KEY, "text": place, "boundary.country": "US", "size": 1}
    r = requests.get(url, params=params)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        return None
    return features[0]["geometry"]["coordinates"]


def get_route(start, end):
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    r = requests.post(url, json={"coordinates": [start, end]}, headers=headers)
    r.raise_for_status()
    return r.json()


@method_decorator(csrf_exempt, name='dispatch')
class RouteView(APIView):
    def post(self, request):
        start_name = request.data.get('start')
        end_name = request.data.get('end')

        if not start_name or not end_name:
            return Response({"error": "start aur end required hain"}, status=status.HTTP_400_BAD_REQUEST)

        start_coords = geocode_ors(start_name)
        end_coords = geocode_ors(end_name)

        if not start_coords or not end_coords:
            return Response({"error": "Location geocode nahi ho saki"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            route_data = get_route(start_coords, end_coords)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        features = route_data['features'][0]
        total_meters = features['properties']['segments'][0]['distance']
        total_miles = total_meters * 0.000621371
        route_coords = features['geometry']['coordinates']

        fuel_stops = self._find_fuel_stops(route_coords)

        total_gallons = total_miles / MPG
        avg_price = (sum(s['price_per_gallon'] for s in fuel_stops) / len(fuel_stops)) if fuel_stops else float(df['Retail Price'].mean())
        total_cost = round(total_gallons * avg_price, 2)

        return Response({
            "start": start_name,
            "end": end_name,
            "total_miles": round(total_miles, 1),
            "total_fuel_cost_usd": total_cost,
            "fuel_stops": fuel_stops,
            "route_coordinates": route_coords,
        })

    def _find_fuel_stops(self, route_coords):
        stops = []
        miles_since_fuel = 0
        cumulative_miles = 0

        for i in range(1, len(route_coords)):
            prev = (route_coords[i-1][1], route_coords[i-1][0])
            curr = (route_coords[i][1], route_coords[i][0])
            segment_miles = geodesic(prev, curr).miles
            cumulative_miles += segment_miles
            miles_since_fuel += segment_miles

            if miles_since_fuel >= REFUEL_AT_MILES:
                lon, lat = route_coords[i]
                station = self._nearest_cheap_station(lat, lon)
                if station is not None:
                    stops.append({
                        "name": station['Truckstop Name'],
                        "city": station['City'].strip(),
                        "state": station['State'],
                        "price_per_gallon": round(float(station['Retail Price']), 3),
                        "at_mile": round(cumulative_miles, 1),
                    })
                miles_since_fuel = 0

        return stops

    def _nearest_cheap_station(self, lat, lon, radius_miles=300):
        best_station = None
        best_score = float('inf')

        for _, row in df.iterrows():
            state = str(row['State']).strip()
            state_coord = STATE_COORDS.get(state)
            if not state_coord:
                continue
            dist = geodesic((lat, lon), state_coord).miles
            if dist <= radius_miles:
                score = row['Retail Price'] + (dist * 0.001)
                if score < best_score:
                    best_score = score
                    best_station = row

        return best_station