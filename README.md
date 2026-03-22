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
| **Per-endpoint credentials** | 8 auth types per endpoint: Bearer, API Key (header/query), Basic, Digest, OAuth 2.0 Client Credentials, Custom Header; plus arbitrary extra headers/params overlays |
| **Scheduled execution** | Run endpoints automatically on an *interval* (every N seconds) or a *cron* schedule |
| **Email notifications** | Optionally email the response to one or more addresses after each run |
| **On-demand run** | Trigger any endpoint immediately via `POST /api/endpoints/{id}/run/` |
| **Result history** | Browse paginated response history; filter by endpoint |
| **Django Admin** | Full CRUD management through the built-in admin interface |
| **REST API** | DRF-powered API with session + basic authentication |

---

## Requirements

| Requirement | Version |
|-------------|---------|
| **OS** | Ubuntu 24.04 LTS (or any system with Python 3.12+) |
| **Python** | 3.12+ |
| **Django** | 4.2+ |

---

## Installation on Ubuntu 24.04 LTS

### Option A — Automated one-command install (recommended)

```bash
# Clone and run the installer as root (or with sudo)
git clone https://github.com/iEpiK/UbuntuDashboard.git
cd UbuntuDashboard
sudo bash install.sh
```

The installer will:
1. Install system packages (`python3`, `python3-venv`, `git`, `curl`)
2. Create a dedicated system user (`ubuntudashboard`)
3. Set up a Python virtual environment and install all dependencies
4. Generate a random `SECRET_KEY` and create a `.env` config file at `/opt/ubuntudashboard/.env`
5. Apply database migrations and collect static files
6. Prompt you to create an admin superuser
7. Install and start a **systemd service** (using gunicorn) — the dashboard starts automatically on boot

After install the dashboard is available at **http://\<your-server\>:8000/**

**Customise the install location:**
```bash
sudo INSTALL_DIR=/srv/dashboard BIND_ADDRESS=0.0.0.0:9000 bash install.sh
```

**Skip systemd / superuser creation (e.g. in CI):**
```bash
sudo SKIP_SYSTEMD=true SKIP_SUPERUSER=true bash install.sh
```

**Remote one-liner** (script clones the repo itself):
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/iEpiK/UbuntuDashboard/main/install.sh)
```

---

### Option B — Manual Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/iEpiK/UbuntuDashboard.git
cd UbuntuDashboard

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (edit .env as needed)
cp .env.example .env   # or create .env manually

# 5. Apply migrations
python manage.py migrate

# 6. Create a superuser for the admin dashboard
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
```

Open <http://127.0.0.1:8000/admin/> to manage endpoints and tasks through the
Django Admin.  The REST API is available at <http://127.0.0.1:8000/api/>.

---

## Configuration

All settings can be overridden via environment variables (or a `.env` file
that is loaded by `install.sh`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(insecure dev key)* | Django secret key — **must be set in production** |
| `DEBUG` | `true` | Set to `false` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed host names |
| `EMAIL_HOST` | `localhost` | SMTP server hostname |
| `EMAIL_PORT` | `25` | SMTP server port |
| `EMAIL_USE_TLS` | `false` | Enable STARTTLS |
| `EMAIL_HOST_USER` | *(empty)* | SMTP login username |
| `EMAIL_HOST_PASSWORD` | *(empty)* | SMTP login password |
| `DEFAULT_FROM_EMAIL` | `ubuntudashboard@localhost` | From address for outgoing email |

Example `.env` file:
```dotenv
SECRET_KEY=your-very-long-random-secret
DEBUG=false
ALLOWED_HOSTS=dashboard.example.com,www.dashboard.example.com
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=user@example.com
EMAIL_HOST_PASSWORD=secret
DEFAULT_FROM_EMAIL=ubuntudashboard@example.com
```

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

**Create endpoint with OAuth 2.0 + extra headers:**
```json
{
  "name": "Acme Data API",
  "url": "https://api.acme.com/data",
  "method": "GET",
  "credential": {
    "auth_type": "oauth2_client_credentials",
    "client_id": "my-client",
    "client_secret": "my-secret",
    "token_url": "https://auth.acme.com/token",
    "oauth2_scope": "read",
    "extra_headers": {"X-Tenant-ID": "acme", "X-Version": "2"},
    "extra_query_params": {"format": "json"}
  }
}
```

### Supported Authentication Types

| Type | `auth_type` value |
|------|--------------------|
| No Authentication | `none` |
| Bearer Token | `bearer` |
| API Key – Header | `api_key_header` |
| API Key – Query Param | `api_key_query` |
| Basic Auth | `basic` |
| Digest Auth | `digest` |
| OAuth 2.0 Client Credentials | `oauth2_client_credentials` |
| Custom Header | `custom_header` |

Any auth type can be combined with `extra_headers` and `extra_query_params`
for multi-header / multi-param setups.

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

## Running Tests

```bash
python manage.py test api
```

