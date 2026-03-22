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
    """

    endpoint = models.OneToOneField(
        APIEndpoint, on_delete=models.CASCADE, related_name='credential'
    )
    auth_type = models.CharField(
        max_length=20, choices=AUTH_TYPE_CHOICES, default='none',
        help_text='Authentication method used when calling this endpoint',
    )
    # Token / API key value / custom header value
    token = models.CharField(
        max_length=2000, blank=True,
        help_text='Bearer token, API key value, or custom header value',
    )
    # Basic auth
    username = models.CharField(max_length=500, blank=True,
                                help_text='Username for Basic Auth')
    password = models.CharField(max_length=500, blank=True,
                                help_text='Password for Basic Auth')
    # Header / query-param name used for API key and custom-header auth
    header_name = models.CharField(
        max_length=200, blank=True, default='Authorization',
        help_text='Header name for "API Key – Header" or "Custom Header" auth '
                  '(defaults to "Authorization")',
    )
    query_param_name = models.CharField(
        max_length=200, blank=True,
        help_text='Query parameter name for "API Key – Query Parameter" auth',
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

    def build_request_kwargs(self, extra_headers: dict) -> dict:
        """Return a dict of kwargs to merge into ``requests.request()``.

        Merges *extra_headers* (from ``APIEndpoint.headers``) with any
        authentication headers / params / auth-tuple derived from the
        stored credentials.
        """
        headers = dict(extra_headers)
        params: dict = {}
        auth = None

        if self.auth_type == 'bearer':
            headers['Authorization'] = f'Bearer {self.token}'
        elif self.auth_type == 'api_key_header':
            name = self.header_name or 'Authorization'
            headers[name] = self.token
        elif self.auth_type == 'api_key_query':
            if self.query_param_name:
                params[self.query_param_name] = self.token
        elif self.auth_type == 'basic':
            auth = (self.username, self.password)
        elif self.auth_type == 'custom_header':
            if self.header_name:
                headers[self.header_name] = self.token

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

