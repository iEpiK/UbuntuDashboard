# UbuntuDashboard

A Django-based admin dashboard that lets you configure custom third-party API
endpoints, schedule them to run automatically, and optionally receive results by
email.  A master REST API exposes every configured endpoint, its schedule, and
all collected results.

---

## Features

| Feature | Description |
|---------|-------------|
| **Custom API endpoints** | Register any HTTP endpoint (GET/POST/PUT/PATCH/DELETE) with custom headers and body |
| **Scheduled execution** | Run endpoints automatically on an *interval* (every N seconds) or a *cron* schedule |
| **Email notifications** | Optionally email the response to one or more addresses after each run |
| **On-demand run** | Trigger any endpoint immediately via `POST /api/endpoints/{id}/run/` |
| **Result history** | Browse paginated response history; filter by endpoint |
| **Django Admin** | Full CRUD management through the built-in admin interface |
| **REST API** | DRF-powered API with session + basic authentication |

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/iEpiK/UbuntuDashboard.git
cd UbuntuDashboard

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply migrations
python manage.py migrate

# 5. Create a superuser for the admin dashboard
python manage.py createsuperuser

# 6. Start the development server
python manage.py runserver
```

Open <http://127.0.0.1:8000/admin/> to manage endpoints and tasks through the
Django Admin.  The REST API is available at <http://127.0.0.1:8000/api/>.

---

## REST API Reference

All endpoints require authentication.  Use session login at
`/api-auth/login/` or supply HTTP Basic credentials.

### API Endpoints (`/api/endpoints/`)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/endpoints/` | List your endpoints |
| POST | `/api/endpoints/` | Create a new endpoint |
| GET | `/api/endpoints/{id}/` | Retrieve an endpoint |
| PUT/PATCH | `/api/endpoints/{id}/` | Update an endpoint |
| DELETE | `/api/endpoints/{id}/` | Delete an endpoint |
| POST | `/api/endpoints/{id}/run/` | Run the endpoint immediately |

**Create endpoint payload example:**
```json
{
  "name": "Weather API",
  "url": "https://api.open-meteo.com/v1/forecast?latitude=52&longitude=13&current_weather=true",
  "method": "GET",
  "headers": {},
  "body": {},
  "description": "Berlin current weather"
}
```

### Scheduled Tasks (`/api/tasks/`)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/tasks/` | List tasks |
| POST | `/api/tasks/` | Create a task |
| GET/PUT/PATCH | `/api/tasks/{id}/` | Retrieve / update a task |
| DELETE | `/api/tasks/{id}/` | Delete and unschedule a task |

**Interval task payload:**
```json
{
  "endpoint": 1,
  "schedule_type": "interval",
  "interval_seconds": 3600,
  "send_email": true,
  "email_recipients": "you@example.com"
}
```

**Cron task payload:**
```json
{
  "endpoint": 1,
  "schedule_type": "cron",
  "cron_expression": "0 9 * * 1-5",
  "send_email": false
}
```

### Results (`/api/results/`)

Read-only.  Filter by endpoint with `?endpoint={id}`.

---

## Email Configuration

Edit `dashboard/settings.py` (or set environment variables) to point at your
SMTP server:

```python
EMAIL_HOST = 'smtp.example.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'user@example.com'
EMAIL_HOST_PASSWORD = 'secret'
DEFAULT_FROM_EMAIL = 'ubuntudashboard@example.com'
```

---

## Running Tests

```bash
python manage.py test api
```
