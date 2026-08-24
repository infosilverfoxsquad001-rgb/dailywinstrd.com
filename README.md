# DAILYWINS — corrected project

## Structure

- `app.py` — Flask routes, authentication, referral logic, admin controls
- `models.py` — users, transactions, payment settings and audit logs
- `templates/` — public, user and admin pages
- `static/css/style.css` — black/red UI
- `static/images/` — supplied DAILYWINS assets
- `static/uploads/kyc/` — KYC uploads

## Install

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set a strong `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, SMTP settings, and payment addresses.

Run:

```bash
python app.py
```

The default admin is created only when no administrator exists. Change the environment password before production use.

## Important

This package is a website application template. Real deposits, investment returns, payment processing, KYC decisions, and withdrawals should only be represented when backed by the actual regulated/payment infrastructure you intend to use. Do not advertise guaranteed investment returns.


### New homepage/user experience features
- Floating DAILYWINS support chat with polling-based live messaging and an admin reply inbox.
- Floating cryptocurrency market panel powered by public CoinGecko market data.
- Approved-withdrawal activity notifications on the homepage. These notifications use actual approved withdrawals from your database and anonymize the user's name. No fake withdrawal activity is generated.
