# Product database
Independent from the platform PostgreSQL database. Build from this directory after generation.
Generated .sql files are applied by the image entrypoint in filename order on FIRST initialization
of an empty volume only. Preserve volumes. Existing databases need explicit reviewed migrations.
PostGIS is available; generated SQL must enable it only when requirements need geospatial data.
Set POSTGRES_DB, POSTGRES_USER and POSTGRES_PASSWORD at deployment; no credentials are embedded.
