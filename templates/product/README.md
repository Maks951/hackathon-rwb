# Generated product

This application is independent of the RWB platform. Set a new local password in
`.env`: `PRODUCT_DB_PASSWORD=<your-generated-password>`. Never reuse platform credentials.
Run `docker compose -p rwb-product-demo up --build -d` from this extracted directory.
Admin: http://localhost:4300; PWA: http://localhost:4301. Check requirements-spec.json
and generated-api.json for the actual business operations, then exercise them in the UI.
SQL initialization runs only on an empty volume; preserve product-data.
Validation results are in reports/validation.json. They do not certify semantic business
correctness or database deployment; run the acceptance scenario after deployment.
