"""
Geocode BERDO building addresses to lat/long and cache them.

Uses the US Census Geocoder batch endpoint (free, keyless). Writes
fixtures/geocoded.json mapping building_id -> [lng, lat] (or null if the
address could not be matched). Re-running is incremental: already-cached ids
are skipped, so you can resume after rate limits.

Run:  PYTHONPATH=. python3 scripts/geocode_buildings.py
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
from pathlib import Path

import httpx2 as httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from server.data import load_buildings  # noqa: E402

CACHE_PATH = Path(__file__).parent.parent / "fixtures" / "geocoded.json"
CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_SIZE = 1000  # Census batch limit is 10k; keep smaller for reliability


def _clean_street(address: str) -> str:
    """Pull a street address out of a messy BERDO address string."""
    a = address.strip()
    # drop a trailing ", Boston, MA 02xxx" if present; we pass zip separately
    a = re.sub(r",?\s*boston,?\s*ma\s*\d{5}.*$", "", a, flags=re.I)
    a = re.sub(r",?\s*ma\s*\d{5}.*$", "", a, flags=re.I)
    # collapse a leading duplicate house number range like "420 414 POND ST" -> "420 POND ST"
    a = re.sub(r"^(\d+)\s+\d+\s+", r"\1 ", a)
    # drop stray " R " range markers
    a = re.sub(r"\s+R\s+", " ", a)
    return a.strip().strip(",")


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {"source": "US Census Geocoder (geocoding.geo.census.gov), one-way address->point. Keyless.",
            "lng_lat_by_building_id": {}}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def main() -> int:
    cache = _load_cache()
    coords = cache["lng_lat_by_building_id"]
    buildings = load_buildings()
    todo = [b for b in buildings if b.building_id not in coords]
    print(f"{len(coords)} cached; {len(todo)} to geocode")

    for start in range(0, len(todo), BATCH_SIZE):
        chunk = todo[start:start + BATCH_SIZE]
        # Census batch CSV: unique id, street, city, state, zip
        buf = io.StringIO()
        w = csv.writer(buf)
        for b in chunk:
            w.writerow([b.building_id, _clean_street(b.address), "Boston", "MA", b.zip or ""])
        files = {"addressFile": ("addresses.csv", buf.getvalue(), "text/csv")}
        data = {"benchmark": "Public_AR_Current"}

        try:
            r = httpx.post(CENSUS_BATCH_URL, data=data, files=files, timeout=180)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"batch {start}-{start+len(chunk)} failed: {e}; saving progress")
            _save_cache(cache)
            time.sleep(5)
            continue

        # Response is CSV: id, input, match, matchtype, matched_addr, lon,lat, ...
        reader = csv.reader(io.StringIO(r.text))
        matched = 0
        returned_ids = set()
        for row in reader:
            if len(row) < 3:
                continue
            bid = row[0]
            returned_ids.add(bid)
            is_match = row[2] == "Match"
            if is_match and len(row) >= 6 and row[5]:
                try:
                    lon, lat = row[5].split(",")
                    coords[bid] = [round(float(lon), 6), round(float(lat), 6)]
                    matched += 1
                    continue
                except (ValueError, IndexError):
                    pass
            coords[bid] = None  # no match — recorded so we don't retry forever
        # Record any chunk ids the response omitted entirely as null, so the
        # batch is never retried forever.
        for b in chunk:
            coords.setdefault(b.building_id, None)

        _save_cache(cache)
        got = sum(1 for v in coords.values() if v)
        print(f"batch done: +{matched} matched this batch; {got}/{len(coords)} total have coords")
        time.sleep(1)

    got = sum(1 for v in coords.values() if v)
    print(f"\nDONE: {got}/{len(coords)} buildings geocoded ({got/len(coords)*100:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
