# DAILY WINS Flask Backend — Starter

This package is a **demo/starter authentication API** intended to connect a static frontend to a Flask backend.

## Included

- Flask application
- SQLite database via SQLAlchemy
- User registration
- Password hashing
- Email verification token flow
- Login
- Basic user lookup
- Health endpoint
- Gunicorn configuration through `requirements.txt`
- Environment variable template

## Important

This starter intentionally does **not** implement real-money deposits, withdrawals, crypto transfers, payment collection, OTP-for-payment, or investment-return logic.

For a legitimate production service, use a properly reviewed payment provider, secure authentication/session handling, HTTPS, rate limiting, audit logging, and applicable financial/legal compliance.

## Local setup

### Windows

```bash
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

### macOS/Linux

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

The API will run on:

`http://127.0.0.1:5000`

## Main endpoints

- `GET /`
- `GET /api/health`
- `POST /api/auth/register`
- `GET /api/auth/verify-email?token=...`
- `POST /api/auth/login`
- `GET /api/users/<id>`

## Registration example

```json
{
  "full_name": "Example User",
  "email": "user@example.com",
  "password": "StrongPassword123!"
}
```

The registration response contains a demo verification URL. In production, send the token through a properly configured transactional email provider rather than returning it from the API.

## Render

Create a Render Web Service and use:

Build command:
`pip install -r requirements.txt`

Start command:
`gunicorn app:app`

Set `SECRET_KEY` as a secure environment variable. For production persistence, configure a PostgreSQL database and set `DATABASE_URL`.
