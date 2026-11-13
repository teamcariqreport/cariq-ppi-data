#!/usr/bin/env python3
"""
Download US auto repair / inspection shops from Overture Maps Places (free, open data)
into a CSV for the Car IQ PPI Finder.

  python3 overture-repair-shops.py PA      # one state (quick test, a few minutes)
  python3 overture-repair-shops.py         # all of the US (10-30 minutes)

Needs DuckDB:  python3 -m pip install --user duckdb
Data: Overture Maps Foundation (CDLA-Permissive-2.0 / Apache-2.0 / CC0 by source).
"""
import sys
import time
import urllib.request

try:
    import duckdb
except ImportError:
    sys.exit("DuckDB isn't installed. Run:  python3 -m pip install --user duckdb   then try again.")

STATE = sys.argv[1].upper() if len(sys.argv) > 1 else ""
OUT = f"overture-repair-shops-{STATE or 'US'}.csv"

# Categories that point to shops able to do a pre-purchase inspection.
CATEGORY_PATTERN = (
    # New taxonomy: everything under "vehicle_service" (repair, body, tire, inspection...).
    "vehicle_service|"
    # Older releases' category names.
    "automotive_repair|auto_body_shop|car_inspection|emissions_inspection|tire_dealer_and_repair|tire_shop|"
    "truck_repair|brake_service|transmission_repair|engine_repair|auto_electrical_repair|"
    "exhaust_and_muffler_repair|hybrid_car_repair|motorcycle_repair|automotive_services_and_repair"
)

def latest_release() -> str:
    """Newest release folder in Overture's public S3 bucket (no account needed)."""
    import re
    url = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/?list-type=2&prefix=release/&delimiter=/"
    xml = urllib.request.urlopen(url, timeout=30).read().decode()
    releases = sorted(re.findall(r"<Prefix>release/([^/<]+)/</Prefix>", xml))
    if not releases:
        sys.exit("Couldn't read Overture's release list. Send this message to Claude.")
    return releases[-1]


print("Finding the latest Overture release...")
release = sys.argv[2] if len(sys.argv) > 2 else latest_release()
print(f"Release {release}")

con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
src = f"s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"

# Look at this release's columns first: Overture renames fields between releases.
print("Checking this release's columns...")
desc = con.sql(f"DESCRIBE SELECT * FROM read_parquet('{src}', hive_partitioning = 1) LIMIT 0").fetchall()
cols = {r[0]: str(r[1]) for r in desc}
print("Columns:", ", ".join(cols))


def has(col, field=None):
    if col not in cols:
        return False
    return field is None or f"{field} " in cols[col] or f'"{field}"' in cols[col]


def first_of(*options, default="NULL"):
    """First expression whose column (and struct field) exists."""
    for col, field, expr in options:
        if has(col, field):
            return expr
    return default


# Text to match categories against: every category-like column, whatever it's called.
cat_cols = [c for c in ("categories", "basic_category", "taxonomy", "category") if c in cols]
if not cat_cols:
    sys.exit("No category column found in this release. Send the 'Columns:' line above to Claude.")
cat_text = " || ' ' || ".join(f"coalesce(CAST({c} AS VARCHAR), '')" for c in cat_cols)

category = first_of(
    ("basic_category", None, "CAST(basic_category AS VARCHAR)"),
    ("taxonomy", "primary", "CAST(taxonomy.primary AS VARCHAR)"),
    ("categories", "primary", "categories.primary"),
)
name = first_of(("names", "primary", "names.primary"), ("name", None, "name"))
addr = lambda f: first_of(("addresses", None, f"addresses[1].{f}"))
lat = first_of(("bbox", None, "round((bbox.ymin + bbox.ymax) / 2, 6)"))
lng = first_of(("bbox", None, "round((bbox.xmin + bbox.xmax) / 2, 6)"))

state_filter = ""
if STATE:
    state_filter = f"AND replace(CAST({addr('region')} AS VARCHAR), 'US-', '') = '{STATE}'"
status_filter = "AND (operating_status IS NULL OR operating_status = 'open')" if "operating_status" in cols else ""
conf_filter = "AND confidence >= 0.4" if "confidence" in cols else ""

query = f"""
COPY (
  SELECT
    {first_of(("id", None, "id"))}                                   AS overture_id,
    {name}                                                           AS name,
    {category}                                                       AS category,
    left(lower({cat_text}), 300)                                     AS category_detail,
    {first_of(("confidence", None, "round(confidence, 3)"))}         AS confidence,
    {first_of(("websites", None, "websites[1]"))}                    AS website,
    {first_of(("phones", None, "phones[1]"))}                        AS phone,
    {addr('freeform')}                                               AS street,
    {addr('locality')}                                               AS city,
    replace(CAST({addr('region')} AS VARCHAR), 'US-', '')            AS state,
    {addr('postcode')}                                               AS zip,
    {lat}                                                            AS lat,
    {lng}                                                            AS lng,
    {first_of(("brand", "names", "brand.names.primary"))}            AS brand,
    {first_of(("operating_status", None, "operating_status"))}       AS operating_status,
    {first_of(("sources", None, "sources[1].dataset"))}              AS source,
    {first_of(("sources", None, "sources[1].license"))}              AS license
  FROM read_parquet('{src}', hive_partitioning = 1)
  WHERE bbox.xmin BETWEEN -180 AND -65
    AND bbox.ymin BETWEEN 17 AND 72
    AND {addr('country')} = 'US'
    {conf_filter}
    {status_filter}
    {state_filter}
    AND regexp_matches(lower({cat_text}), '{CATEGORY_PATTERN}')
) TO '{OUT}' (HEADER, DELIMITER ',');
"""

start = time.time()
print(f"Downloading {'all US' if not STATE else STATE} repair shops (this streams only what's needed)...")
try:
    con.sql(query)
except Exception as e:
    print("\nThe download query failed. Send everything below to Claude:\n")
    print(e)
    print("\nColumns:", cols)
    sys.exit(1)

rows = con.sql(f"SELECT count(*) FROM read_csv_auto('{OUT}')").fetchall()[0][0]
print(f"\nSaved {rows:,} shops to {OUT} in {time.time() - start:.0f}s\n")
print("Top categories:")
for cat, n in con.sql(f"SELECT category, count(*) n FROM read_csv_auto('{OUT}') GROUP BY 1 ORDER BY 2 DESC LIMIT 15").fetchall():
    print(f"  {n:>7,}  {cat}")
print("\nDone. Send the CSV back to Claude.")
