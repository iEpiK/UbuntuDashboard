from django.db import models
from django.contrib.auth.models import User


HTTP_METHOD_CHOICES = [
    ('GET', 'GET'),
    ('POST', 'POST'),
    ('PUT', 'PUT'),
    ('PATCH', 'PATCH'),
    ('DELETE', 'DELETE'),
]

SCHEDULE_TYPE_CHOICES = [
    ('interval', 'Interval'),
    ('cron', 'Cron'),
]

AUTH_TYPE_CHOICES = [
    ('none', 'No Authentication'),
    ('bearer', 'Bearer Token'),
    ('api_key_header', 'API Key – Header'),
    ('api_key_query', 'API Key – Query Parameter'),
    ('basic', 'Basic Auth (Username & Password)'),
    ('digest', 'Digest Auth (Username & Password)'),
    ('oauth2_client_credentials', 'OAuth 2.0 – Client Credentials'),
    ('custom_header', 'Custom Header'),
]


class APIEndpoint(models.Model):
    """A third-party API endpoint that the dashboard can call."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=2000)
    method = models.CharField(max_length=10, choices=HTTP_METHOD_CHOICES, default='GET')
    headers = models.JSONField(default=dict, blank=True,
                               help_text='Extra HTTP headers as a JSON object. '
                                         'Authentication headers are managed separately via Credentials.')
    body = models.JSONField(default=dict, blank=True,
                            help_text='Request body as a JSON object (used for POST/PUT/PATCH)')
    is_active = models.BooleanField(default=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_endpoints')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} [{self.method}]'


class APICredential(models.Model):
    """Per-endpoint authentication credentials.

    One-to-one with APIEndpoint so every endpoint has its own isolated
    credential configuration that can be updated independently.

    Primary auth is controlled by ``auth_type``.  In addition,
    ``extra_headers`` and ``extra_query_params`` are always merged into
    every request, regardless of the primary auth type, allowing arbitrary
    multi-header / multi-param configurations.
    """

    endpoint = models.OneToOneField(
        APIEndpoint, on_delete=models.CASCADE, related_name='credential'
    )
    auth_type = models.CharField(
        max_length=30, choices=AUTH_TYPE_CHOICES, default='none',
        help_text='Primary authentication method used when calling this endpoint',
    )

    # ---- Token / API key / custom header value ---------------------------
    token = models.CharField(
        max_length=2000, blank=True,
        help_text='Bearer token, API key value, or custom header value',
    )

    # ---- Basic / Digest auth ---------------------------------------------
    username = models.CharField(max_length=500, blank=True,
                                help_text='Username for Basic or Digest Auth')
    password = models.CharField(max_length=500, blank=True,
                                help_text='Password for Basic or Digest Auth')

    # ---- Header / query-param names --------------------------------------
    header_name = models.CharField(
        max_length=200, blank=True, default='Authorization',
        help_text='Header name for "API Key – Header" or "Custom Header" auth '
                  '(defaults to "Authorization")',
    )
    query_param_name = models.CharField(
        max_length=200, blank=True,
        help_text='Query parameter name for "API Key – Query Parameter" auth',
    )

    # ---- OAuth 2.0 Client Credentials ------------------------------------
    client_id = models.CharField(
        max_length=500, blank=True,
        help_text='OAuth 2.0 client ID',
    )
    client_secret = models.CharField(
        max_length=2000, blank=True,
        help_text='OAuth 2.0 client secret',
    )
    token_url = models.URLField(
        max_length=2000, blank=True,
        help_text='OAuth 2.0 token endpoint URL '
                  '(e.g. https://auth.example.com/oauth/token)',
    )
    oauth2_scope = models.CharField(
        max_length=500, blank=True,
        help_text='Optional space-separated OAuth 2.0 scopes',
    )

    # ---- Always-applied overlays -----------------------------------------
    extra_headers = models.JSONField(
        default=dict, blank=True,
        help_text=(
            'Additional HTTP headers applied on every request, merged after '
            'the primary auth headers.  Use for multi-header API keys, tenant '
            'IDs, versioning headers, etc.  '
            'Example: {"X-Tenant-ID": "acme", "X-API-Version": "2"}'
        ),
    )
    extra_query_params = models.JSONField(
        default=dict, blank=True,
        help_text=(
            'Additional query parameters applied on every request, merged '
            'after any primary auth query params.  '
            'Example: {"version": "2", "format": "json"}'
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'API Credential'

    def __str__(self):
        return f'{self.endpoint.name} – {self.get_auth_type_display()}'

    # ------------------------------------------------------------------
    # Apply credentials to a pending requests.request call
    # ------------------------------------------------------------------

    def _fetch_oauth2_token(self) -> str:
        """Exchange client credentials for an OAuth 2.0 access token."""
        import requests as _req
        payload: dict = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        if self.oauth2_scope:
            payload['scope'] = self.oauth2_scope
        try:
            response = _req.post(self.token_url, data=payload, timeout=30)
            response.raise_for_status()
        except _req.RequestException as exc:
            raise ValueError(
                f'OAuth 2.0 token fetch failed for endpoint "{self.endpoint.name}": {exc}'
            ) from exc
        token = response.json().get('access_token')
        if not token:
            raise ValueError(
                f'OAuth 2.0 token response for endpoint "{self.endpoint.name}" '
                'did not contain an access_token field.'
            )
        return token

    def build_request_kwargs(self, endpoint_headers: dict) -> dict:
        """Return a dict of kwargs to pass to ``requests.request()``.

        Merges *endpoint_headers* (from ``APIEndpoint.headers``) with the
        primary authentication data, then overlays ``extra_headers`` and
        ``extra_query_params`` so that any number of additional credential
        parameters can be added without changing the auth type.
        """
        from requests.auth import HTTPBasicAuth, HTTPDigestAuth

        headers = dict(endpoint_headers)
        params: dict = {}
        auth = None

        # -- primary authentication type ----------------------------------
        if self.auth_type == 'bearer':
            headers['Authorization'] = f'Bearer {self.token}'
        elif self.auth_type == 'api_key_header':
            name = self.header_name or 'Authorization'
            headers[name] = self.token
        elif self.auth_type == 'api_key_query':
            if self.query_param_name:
                params[self.query_param_name] = self.token
        elif self.auth_type == 'basic':
            auth = HTTPBasicAuth(self.username, self.password)
        elif self.auth_type == 'digest':
            auth = HTTPDigestAuth(self.username, self.password)
        elif self.auth_type == 'oauth2_client_credentials':
            access_token = self._fetch_oauth2_token()
            headers['Authorization'] = f'Bearer {access_token}'
        elif self.auth_type == 'custom_header':
            if self.header_name:
                headers[self.header_name] = self.token

        # -- always-applied overlays (merged after primary auth) ----------
        if self.extra_headers:
            headers.update(self.extra_headers)
        if self.extra_query_params:
            params.update(self.extra_query_params)

        kwargs: dict = {'headers': headers}
        if params:
            kwargs['params'] = params
        if auth is not None:
            kwargs['auth'] = auth
        return kwargs


class ScheduledTask(models.Model):
    """A scheduled job that calls an APIEndpoint at a preset interval or cron schedule."""

    endpoint = models.ForeignKey(APIEndpoint, on_delete=models.CASCADE, related_name='scheduled_tasks')
    schedule_type = models.CharField(max_length=10, choices=SCHEDULE_TYPE_CHOICES, default='interval')
    # For interval scheduling
    interval_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Run every N seconds (used when schedule_type is "interval")',
    )
    # For cron scheduling
    cron_expression = models.CharField(
        max_length=100, blank=True,
        help_text='Cron expression (minute hour day month weekday), e.g. "0 9 * * 1-5"',
    )
    is_enabled = models.BooleanField(default=True)
    send_email = models.BooleanField(default=False, help_text='Email the result after each run')
    email_recipients = models.TextField(
        blank=True,
        help_text='Comma-separated list of email addresses to notify',
    )
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Task for {self.endpoint.name} ({self.schedule_type})'

    def get_email_recipient_list(self):
        """Return a list of email addresses from the comma-separated field."""
        return [addr.strip() for addr in self.email_recipients.split(',') if addr.strip()]


class APIResult(models.Model):
    """Stores the response from a single execution of an APIEndpoint."""

    endpoint = models.ForeignKey(APIEndpoint, on_delete=models.CASCADE, related_name='results')
    scheduled_task = models.ForeignKey(
        ScheduledTask, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='results',
    )
    status_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    execution_time_ms = models.FloatField(
        null=True, blank=True,
        help_text='Request round-trip time in milliseconds',
    )
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status = self.status_code or 'ERR'
        return f'{self.endpoint.name} – {status} @ {self.created_at:%Y-%m-%d %H:%M:%S}'

