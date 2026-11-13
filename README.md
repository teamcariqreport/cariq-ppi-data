# Car IQ PPI shop data

Builds the US shop database used by the Car IQ PPI Finder WordPress plugin.

Every quarter (or when run by hand under **Actions → Build PPI shop data → Run workflow**) this:

1. Downloads auto repair and inspection shops from the latest [Overture Maps](https://overturemaps.org/) Places release.
2. Cleans them (`scripts/ppi-clean.py`): keeps inspection-capable shop types, removes car washes, towing, events and clubs, fixes states, drops bad locations and duplicates, labels independent / chain / dealership.
3. Publishes one `ppi-shops-XX.csv.gz` file per state plus `manifest.json` as a GitHub release.

The plugin checks the latest release and imports new data automatically.

## Data licence

Data © Overture Maps Foundation contributors, under CDLA-Permissive-2.0, Apache-2.0 and CC0 depending on the source.
The ZIP centroid table in `data/` comes from the `zipcodes` npm package (BSD).
