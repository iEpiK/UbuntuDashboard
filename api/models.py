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


class APIEndpoint(models.Model):
    """A third-party API endpoint that the dashboard can call."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=2000)
    method = models.CharField(max_length=10, choices=HTTP_METHOD_CHOICES, default='GET')
    headers = models.JSONField(default=dict, blank=True,
                               help_text='HTTP headers as a JSON object, e.g. {"Authorization": "Bearer token"}')
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
