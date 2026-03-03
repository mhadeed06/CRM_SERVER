import geoip2.database
from pathlib import Path
DB_PATH = "app/data/GeoLite2-City.mmdb"
reader = geoip2.database.Reader(str(DB_PATH))

def get_region_from_ip(ip: str) -> dict:
    try:
        r = reader.city(ip)
        return {
            "country": r.country.name,
            "country_code": r.country.iso_code,
            "region": r.subdivisions.most_specific.name,
            "city": r.city.name,
        }
    except Exception:
        return {}
