import logging
import geoip2.database

logger = logging.getLogger("uvicorn")

DB_PATH = "app/data/GeoLite2-City.mmdb"

try:
    reader = geoip2.database.Reader(str(DB_PATH))
except Exception:
    logger.warning("GeoIP database not found at %s — IP lookups will return empty", DB_PATH)
    reader = None


def get_region_from_ip(ip: str) -> dict:
    if reader is None:
        return {}
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
