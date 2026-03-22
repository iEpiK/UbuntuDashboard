#!/usr/bin/env bash
# =============================================================================
# UbuntuDashboard — installer for Ubuntu 24.04 LTS
#
# Usage (remote one-liner after cloning):
#   git clone https://github.com/iEpiK/UbuntuDashboard.git
#   cd UbuntuDashboard
#   bash install.sh
#
# Or run entirely remotely (the script clones the repo itself):
#   bash <(curl -fsSL https://raw.githubusercontent.com/iEpiK/UbuntuDashboard/main/install.sh)
#
# Options (environment variables):
#   INSTALL_DIR      – Where to install the project (default: /opt/ubuntudashboard)
#   VENV_DIR         – Path for the Python virtual environment (default: $INSTALL_DIR/.venv)
#   REPO_URL         – Git repository URL (default: https://github.com/iEpiK/UbuntuDashboard.git)
#   REPO_BRANCH      – Branch to clone (default: main)
#   SKIP_SUPERUSER   – Set to "true" to skip interactive superuser creation
#   SKIP_SYSTEMD     – Set to "true" to skip systemd service installation
#   SERVICE_USER     – OS user that will own the service (default: ubuntudashboard)
#   BIND_ADDRESS     – Host:port for gunicorn (default: 0.0.0.0:8000)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INSTALL_DIR="${INSTALL_DIR:-/opt/ubuntudashboard}"
VENV_DIR="${VENV_DIR:-${INSTALL_DIR}/.venv}"
REPO_URL="${REPO_URL:-https://github.com/iEpiK/UbuntuDashboard.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
SKIP_SUPERUSER="${SKIP_SUPERUSER:-false}"
SKIP_SYSTEMD="${SKIP_SYSTEMD:-false}"
SERVICE_USER="${SERVICE_USER:-ubuntudashboard}"
BIND_ADDRESS="${BIND_ADDRESS:-0.0.0.0:8000}"
SERVICE_NAME="ubuntudashboard"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)."
    fi
}

# ---------------------------------------------------------------------------
# 1. System requirements check
# ---------------------------------------------------------------------------
info "Checking system requirements…"

if [[ -f /etc/os-release ]]; then
    # shellcheck source=/dev/null
    source /etc/os-release
    if [[ "${ID:-}" != "ubuntu" ]]; then
        warn "This script is optimized for Ubuntu.  Detected: ${PRETTY_NAME:-unknown}."
    fi
else
    warn "Cannot detect OS; /etc/os-release not found."
fi

require_root

# ---------------------------------------------------------------------------
# 2. Install system packages
# ---------------------------------------------------------------------------
info "Updating package lists…"
apt-get update -qq

info "Installing system packages…"
apt-get install -y -qq \
    git \
    python3 \
    python3-venv \
    python3-pip \
    curl

# Verify Python 3.12+
PYTHON_BIN="$(command -v python3)"
PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print("{}.{}".format(*sys.version_info[:2]))')"
info "Python version: ${PYTHON_VERSION}"
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
    success "Python ${PYTHON_VERSION} meets the minimum requirement (3.12)."
else
    error "Python 3.12+ is required. Found ${PYTHON_VERSION}."
fi

# ---------------------------------------------------------------------------
# 3. Clone or update the repository
# ---------------------------------------------------------------------------
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Repository already exists at ${INSTALL_DIR}; pulling latest changes…"
    git -C "${INSTALL_DIR}" fetch --quiet origin "${REPO_BRANCH}"
    git -C "${INSTALL_DIR}" reset --hard "origin/${REPO_BRANCH}" --quiet
    success "Repository updated."
else
    info "Cloning ${REPO_URL} (branch: ${REPO_BRANCH}) into ${INSTALL_DIR}…"
    git clone --quiet --branch "${REPO_BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
    success "Repository cloned."
fi

# ---------------------------------------------------------------------------
# 4. Create a dedicated system user (for systemd service)
# ---------------------------------------------------------------------------
if ! id -u "${SERVICE_USER}" &>/dev/null; then
    info "Creating system user '${SERVICE_USER}'…"
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
    success "User '${SERVICE_USER}' created."
fi
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

# ---------------------------------------------------------------------------
# 5. Create Python virtual environment and install dependencies
# ---------------------------------------------------------------------------
info "Creating Python virtual environment at ${VENV_DIR}…"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
success "Virtual environment created."

info "Installing Python dependencies…"
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"
success "Python dependencies installed."

# ---------------------------------------------------------------------------
# 6. Generate .env file if it does not exist
# ---------------------------------------------------------------------------
ENV_FILE="${INSTALL_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    info "Generating ${ENV_FILE}…"
    SECRET_KEY="$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")"
    cat > "${ENV_FILE}" <<EOF
# UbuntuDashboard environment configuration
# Edit this file to match your environment, then restart the service.

SECRET_KEY=${SECRET_KEY}
DEBUG=false
ALLOWED_HOSTS=localhost,127.0.0.1

# Email settings (uncomment and fill in to enable email notifications)
# EMAIL_HOST=smtp.example.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=true
# EMAIL_HOST_USER=user@example.com
# EMAIL_HOST_PASSWORD=secret
# DEFAULT_FROM_EMAIL=ubuntudashboard@example.com
EOF
    chmod 640 "${ENV_FILE}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${ENV_FILE}"
    success ".env file created."
else
    info ".env file already exists; skipping generation."
fi

# ---------------------------------------------------------------------------
# 7. Export env vars and run Django setup
# ---------------------------------------------------------------------------
info "Running database migrations…"
# Load .env into the current shell so manage.py picks them up
set -o allexport
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +o allexport

sudo -u "${SERVICE_USER}" "${VENV_DIR}/bin/python" "${INSTALL_DIR}/manage.py" migrate --noinput
success "Migrations applied."

info "Collecting static files…"
sudo -u "${SERVICE_USER}" "${VENV_DIR}/bin/python" "${INSTALL_DIR}/manage.py" collectstatic --noinput --clear --quiet
success "Static files collected."

# ---------------------------------------------------------------------------
# 8. Create superuser
# ---------------------------------------------------------------------------
if [[ "${SKIP_SUPERUSER}" != "true" ]]; then
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    info "Create the Django admin superuser account:"
    sudo -u "${SERVICE_USER}" "${VENV_DIR}/bin/python" "${INSTALL_DIR}/manage.py" createsuperuser
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
fi

# ---------------------------------------------------------------------------
# 9. Install systemd service (optional)
# ---------------------------------------------------------------------------
if [[ "${SKIP_SYSTEMD}" != "true" ]]; then
    info "Installing systemd service '${SERVICE_NAME}'…"

    # Install gunicorn into the venv for production use
    "${VENV_DIR}/bin/pip" install --quiet gunicorn

    cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=UbuntuDashboard Django application
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/gunicorn \\
    --bind ${BIND_ADDRESS} \\
    --workers 3 \\
    --timeout 120 \\
    --access-logfile - \\
    --error-logfile - \\
    dashboard.wsgi:application
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"
    success "Systemd service '${SERVICE_NAME}' installed and started."
    info "Check service status with: sudo systemctl status ${SERVICE_NAME}"
fi

# ---------------------------------------------------------------------------
# 10. Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  UbuntuDashboard installation complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Install directory : ${INSTALL_DIR}"
echo -e "  Virtual env       : ${VENV_DIR}"
echo -e "  Config file       : ${ENV_FILE}"
echo ""
if [[ "${SKIP_SYSTEMD}" != "true" ]]; then
    echo -e "  Service           : ${SERVICE_NAME} (systemd)"
    echo -e "  Listening on      : http://${BIND_ADDRESS}"
else
    echo -e "  To start manually:"
    echo -e "    cd ${INSTALL_DIR}"
    echo -e "    source .env  # or export the vars manually"
    echo -e "    ${VENV_DIR}/bin/python manage.py runserver"
fi
echo ""
echo -e "  Admin UI  : http://localhost:8000/admin/"
echo -e "  REST API  : http://localhost:8000/api/"
echo ""
