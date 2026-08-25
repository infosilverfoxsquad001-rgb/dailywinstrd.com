# DAILYWINS reorganized Flask project

This version combines the static website and the Flask backend into one application. Flask serves the pages, so navigation uses `url_for()` instead of hard-coded GitHub Pages URLs.

## Structure

```text
dailywins/
├── app.py
├── config.py
├── email_service.py
├── auth_utils.py
├── requirements.txt
├── render.yaml
├── .env.example
├── models/
│   ├── user.py
│   ├── investment.py
│   ├── transaction.py
│   └── admin.py
├── routes/
│   ├── auth.py
│   ├── api.py
│   ├── dashboard.py
│   ├── investments.py
│   ├── transactions.py
│   └── admin.py
├── templates/
├── static/
└── database/
    └── dailywins.db  # created automatically at runtime
```

## What is fixed

- Registration, email verification, login and logout use Flask server-side sessions.
- Passwords are hashed; plaintext passwords are never stored.
- Verification codes expire.
- Password reset uses a time-limited token.
- All frontend navigation is generated with Flask `url_for()`.
- Static images/CSS/JS are served by Flask.
- User dashboard is protected server-side.
- Each logged-in user is loaded from the database rather than from browser localStorage.
- Admin pages have a server-side admin session.
- JSON endpoints are available under `/api/...`.

## Run locally

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

For email verification, copy `.env.example` to `.env` and provide SMTP credentials. If SMTP is not configured, the code is logged by the server. For development only, `ALLOW_DEV_VERIFICATION_CODE=true` can expose the generated code in the registration response/API; keep it false in production.

## Deployment

GitHub Pages cannot execute Flask/Python server code. Push this repository to GitHub, then deploy the Flask application on a Python host such as Render. The included `render.yaml` contains the web-service start command.

For production persistence, use PostgreSQL rather than SQLite on an ephemeral web-service filesystem.

## Important scope

Deposit, withdrawal, payment processing and investment execution are deliberately placeholders. Do not connect real-money flows until the payment, accounting, security and legal/compliance requirements have been properly reviewed.
