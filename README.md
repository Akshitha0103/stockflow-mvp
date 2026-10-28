# StockFlow MVP

A lightweight multi-tenant inventory management application built with Flask, SQLite, and Bootstrap.

## Features
- Email/password signup and login with Werkzeug password hashing
- One organization created per signup; one owner account per organization
- Organization-scoped product CRUD and SKU uniqueness
- Dashboard totals, stock valuation, recent products, and low-stock list
- Configurable default low-stock threshold
- Server-side validation and organization-scoped edit/delete queries

## Run locally (Windows PowerShell)
1. Install Python 3.11 or 3.12.
2. Open this folder in VS Code.
3. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
4. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
5. Set a secret key for local development (optional but recommended):
   ```powershell
   $env:SECRET_KEY = "use-a-long-random-secret"
   ```
6. Start the app:
   ```powershell
   python app.py
   ```
7. Open http://127.0.0.1:5000 and create your account.

## Deployment
Push the project to GitHub and create a Python web service on a host that supports Flask and Gunicorn.
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Set environment variable `SECRET_KEY` to a long random secret.
- Set `FLASK_ENV=production` to enable secure session cookies over HTTPS.
- SQLite files on many free hosting tiers are ephemeral. For a demo, data may reset after redeploy/restart. For persistence, attach a persistent disk and set `DATABASE_PATH` to a file path on that disk, or switch to a managed PostgreSQL database.
- Confirm the provider's current free-tier and persistence rules before choosing a host.

## Security notes
- Passwords are stored as password hashes, not plaintext.
- All product read/write queries are filtered by the logged-in organization ID.
- SKU uniqueness is enforced per organization in SQLite.
- Set a unique `SECRET_KEY` in deployment; never use the development fallback in production.
- This is an assessment MVP, not a hardened production SaaS. Add CSRF protection, rate limiting, password reset, backups, and a managed database before production use.

## Demo checklist
1. Sign up with an email and organization name.
2. Add a product with quantity 3 and threshold 5.
3. Verify it appears in the low-stock dashboard.
4. Edit quantity to 20 and verify it leaves the low-stock list.
5. Search by product name and SKU.
6. Change the default threshold in Settings.
7. Create a second account and verify the first account's products are not visible.
