# Quick API tests

## Health

```bash
curl http://127.0.0.1:5000/api/health
```

## Register

```bash
curl -X POST http://127.0.0.1:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test User","email":"test@example.com","password":"StrongPassword123!"}'
```

Copy the returned `verification_url` and open it in a browser.

## Login

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"StrongPassword123!"}'
```
