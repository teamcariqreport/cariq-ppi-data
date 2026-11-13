"""Clean Overture repair-shop CSV into per-state import files for the PPI Finder."""
import csv, gzip, math, os, re, sys, collections

csv.field_size_limit(10**7)
SRC, ZIPS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)

# Shop types that can do (or are relevant to) a pre-purchase inspection, and a rank weight:
# lower = listed earlier at equal distance.
KEEP = {
    'car_inspection': 0.7, 'automotive_repair': 1.0, 'automotive_service': 1.1, 'engine_repair_service': 1.0,
    'transmission_repair': 1.2, 'brake_service_and_repair': 1.3, 'auto_electrical_repair': 1.3,
    'exhaust_and_muffler_repair': 1.4, 'hybrid_car_repair': 1.0, 'automotive_consultant': 1.0,
    'auto_restoration_service': 1.2, 'truck_repair': 1.2, 'recreation_vehicle_repair': 1.2,
    'motorcycle_repair': 1.3, 'emissions_inspection': 1.5, 'tire_dealer_and_repair': 1.5,
    'auto_body_shop': 1.6, 'tire_shop': 1.6, 'motorsport_vehicle_repair': 1.2,
}
LABEL = {
    'car_inspection': 'Vehicle inspection', 'automotive_repair': 'Auto repair', 'automotive_service': 'Auto service',
    'engine_repair_service': 'Engine repair', 'transmission_repair': 'Transmission repair',
    'brake_service_and_repair': 'Brake repair', 'auto_electrical_repair': 'Auto electrical repair',
    'exhaust_and_muffler_repair': 'Exhaust and muffler', 'hybrid_car_repair': 'Hybrid and EV repair',
    'automotive_consultant': 'Car buying consultant', 'auto_restoration_service': 'Restoration and classics',
    'truck_repair': 'Truck repair', 'recreation_vehicle_repair': 'RV repair', 'motorcycle_repair': 'Motorcycle repair',
    'emissions_inspection': 'Emissions and state inspection', 'tire_dealer_and_repair': 'Tire and auto service',
    'auto_body_shop': 'Auto body', 'tire_shop': 'Tire and auto service', 'motorsport_vehicle_repair': 'Performance and race repair',
}
CHAINS = ('firestone', 'pep boys', 'midas', 'meineke', 'jiffy lube', 'valvoline', 'monro', 'goodyear', 'ntb',
          'mavis', 'tires plus', 'big o tires', 'christian brothers', 'les schwab', 'discount tire', 'aamco',
          'precision tune', 'grease monkey', 'take 5', 'tire kingdom', 'car-x', 'brakes plus', 'walmart',
          'costco', 'sears auto', 'tuffy', 'caliber', 'gerber collision', 'maaco', 'cottman', 'lee myles',
          'express oil', 'kwik kar', 'tire discounters', 'belle tire', 'napa autocare', 'service king',
          'crash champions', 'safelite', 'sun devil', 'conrad', 'just tires', 'american tire', 'quick lane')
MAKES = re.compile(r"\b(chevrolet|chevy|ford|toyota|honda|nissan|hyundai|kia|subaru|mazda|volkswagen|vw|bmw|mercedes(-benz)?|audi|lexus|acura|infiniti|cadillac|buick|gmc|chrysler|dodge|jeep|lincoln|volvo|porsche|mitsubishi|genesis|jaguar|land rover|mini|alfa romeo|fiat|tesla|rivian)\b", re.I)
INDIE = re.compile(r"\b(repair|garage|specialists?|clinic|tech|doctor|independent|imports?|euro|performance|parts|salvage|body|collision|tire|used|transmission|muffler|brake|diesel)\b", re.I)
DEALER_WORD = re.compile(r"\b(dealership|auto ?mall|motor ?cars?|auto group)\b", re.I)
STATES = {'alabama':'AL','alaska':'AK','arizona':'AZ','arkansas':'AR','california':'CA','colorado':'CO','connecticut':'CT',
 'delaware':'DE','district of columbia':'DC','florida':'FL','georgia':'GA','hawaii':'HI','idaho':'ID','illinois':'IL',
 'indiana':'IN','iowa':'IA','kansas':'KS','kentucky':'KY','louisiana':'LA','maine':'ME','maryland':'MD',
 'massachusetts':'MA','michigan':'MI','minnesota':'MN','mississippi':'MS','missouri':'MO','montana':'MT',
 'nebraska':'NE','nevada':'NV','new hampshire':'NH','new jersey':'NJ','new mexico':'NM','new york':'NY',
 'north carolina':'NC','north dakota':'ND','ohio':'OH','oklahoma':'OK','oregon':'OR','pennsylvania':'PA',
 'rhode island':'RI','south carolina':'SC','south dakota':'SD','tennessee':'TN','texas':'TX','utah':'UT',
 'vermont':'VT','virginia':'VA','washington':'WA','west virginia':'WV','wisconsin':'WI','wyoming':'WY'}
CODES = set(STATES.values())

ADDRESS_NAME = re.compile(r"^(\d+\s+)?[\w .'-]*\b(hwy|highway|st|street|rd|road|ave|avenue|blvd|pike|route|rte|dr|drive|ln|lane|way|pkwy)\.?( [nsew]\.?)?$", re.I)
JUNK_SITE = re.compile(r"(poi\.place|business\.site|yelp\.|yellowpages\.|mapquest\.|manta\.com|bizapedia|chamberofcommerce\.com|cylex|hotfrog|superpages)", re.I)
NONSHOP = re.compile(r"\b(nationals|car club|owners'? club|club of|association|assoc|society|events?|auction|museum|festival|cruise night|swap ?meet|car show|salvage|junk ?yard|community college|foundation|league)\b", re.I)
zips = {}
for line in open(ZIPS):
    p = line.strip().split(',')
    if len(p) == 5:
        zips[p[0]] = (float(p[1]), float(p[2]), p[4])


def miles(a, b, c, d):
    x, y = math.radians(c - a), math.radians(d - b)
    h = math.sin(x / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(y / 2) ** 2
    return 2 * 3958.8 * math.asin(min(1, math.sqrt(h)))


def digits(p):
    d = re.sub(r'\D', '', p or '')
    return d[1:] if len(d) == 11 and d[0] == '1' else d


def fmt_phone(d):
    return f'({d[:3]}) {d[3:6]}-{d[6:]}' if len(d) == 10 else ''


stats = collections.Counter()
best = {}  # dedupe key -> row
for r in csv.DictReader(open(SRC, newline='')):
    stats['in'] += 1
    m = re.search(r"'primary': ([a-z_]+)", r['category_detail'])
    sub = m.group(1) if m else r['category']
    if sub not in KEEP:
        stats['drop_type'] += 1
        continue
    st = (r['state'] or '').strip()
    st = STATES.get(st.lower(), st.upper())
    z5 = (r['zip'] or '')[:5]
    lat, lng = float(r['lat']), float(r['lng'])
    if z5 in zips:
        zl = zips[z5]
        if miles(lat, lng, zl[0], zl[1]) > 25:
            stats['drop_location'] += 1
            continue
        if st not in CODES:
            st = zl[2]
    if st not in CODES:
        stats['drop_state'] += 1
        continue
    name = re.sub(r'\s+', ' ', (r['name'] or '').replace('​', '')).strip()
    if not name:
        stats['drop_noname'] += 1
        continue
    if ADDRESS_NAME.match(name) or len(name) < 3 or NONSHOP.search(name):
        stats['drop_badname'] += 1
        continue
    ph = digits(r['phone'])
    site = (r['website'] or '').strip()
    if JUNK_SITE.search(site):
        site = ''
    if not ph and not site:
        stats['drop_nocontact'] += 1
        continue
    low = name.lower()
    brand = (r['brand'] or '').strip()
    if DEALER_WORD.search(name) or (MAKES.search(name) and not INDIE.search(name)):
        kind = 'dealership'
    elif brand or any(re.search(r'\b' + re.escape(c) + r'\b', low) for c in CHAINS):
        kind = 'chain'
    else:
        kind = 'independent'
    row = {
        'ext_id': r['overture_id'], 'name': name, 'category': sub, 'label': LABEL[sub], 'rank': KEEP[sub],
        'phone': fmt_phone(ph), 'website': site,
        'street': (r['street'] or '').replace('​', '').strip(), 'city': (r['city'] or '').strip(),
        'state': st, 'zip': z5, 'lat': round(lat, 6), 'lng': round(lng, 6), 'brand': brand, 'kind': kind,
        'source': r['source'], 'license': r['license'], 'confidence': r['confidence'] or '0',
    }
    norm = re.sub(r'[^a-z0-9]', '', low)[:24]
    cell = (round(lat, 2), round(lng, 2))
    keys = [('n', norm, cell)] + ([('p', ph, cell)] if len(ph) == 10 else [])
    score = float(row['confidence']) + (0.2 if row['website'] else 0) + (0.2 if row['phone'] else 0) + (0.1 if row['street'] else 0)
    row['_score'] = score
    dup = next((best[k] for k in keys if k in best), None)
    if dup is not None:
        stats['dupes'] += 1
        if score <= dup['_score']:
            # Fill gaps on the kept record from the duplicate.
            for f in ('phone', 'website', 'street'):
                if not dup[f] and row[f]:
                    dup[f] = row[f]
            continue
        for f in ('phone', 'website', 'street'):
            if not row[f] and dup[f]:
                row[f] = dup[f]
        dup['_dead'] = True
    for k in keys:
        best[k] = row

seen, by_state = set(), collections.defaultdict(list)
for row in best.values():
    if row.get('_dead') or id(row) in seen:
        continue
    seen.add(id(row))
    by_state[row['state']].append(row)

FIELDS = ['ext_id', 'name', 'category', 'label', 'rank', 'phone', 'website', 'street', 'city', 'state', 'zip',
          'lat', 'lng', 'brand', 'kind', 'source', 'license', 'confidence']
total = 0
for st, rows in sorted(by_state.items()):
    rows.sort(key=lambda x: (x['zip'], x['name']))
    with gzip.open(os.path.join(OUT, f'ppi-shops-{st}.csv.gz'), 'wt', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    total += len(rows)
stats['out'] = total
print(dict(stats))
print('states', len(by_state))
print(collections.Counter({s: len(r) for s, r in by_state.items()}).most_common(6))
print(collections.Counter(r['kind'] for rs in by_state.values() for r in rs))
