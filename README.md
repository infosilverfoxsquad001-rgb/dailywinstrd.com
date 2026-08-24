# DAILYWINS — exact original design integration

This package uses the supplied HTML files as the visual source of truth. Existing markup/classes/layouts are retained; changes are limited to Flask/Jinja wiring and requested features.

## Run
1. Create a virtual environment.
2. Install `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set secrets (use a real environment loader in production).
4. Run `python app.py`.

The default development database is SQLite. Use a production database such as PostgreSQL for deployment.

## Templates
The supplied filenames are retained, including `dashboard(1).html`, `admin-dashboard.html`, `admin-users.html`, `admin-login.html`, and `user-details(1).html`.

## Currency
User balances, deposits, withdrawals, referral bonuses and homepage withdrawal notifications are USD.

## Important
Password reset URLs are logged server-side as a development fallback; configure a real email provider before production. Crypto prices on the homepage use a browser-side public market endpoint and display USD.
