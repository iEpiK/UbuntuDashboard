"""
APScheduler integration.

Each ScheduledTask record gets a corresponding APScheduler job.  The scheduler
is started once when the Django process starts (see apps.py / AppConfig.ready).
"""

import logging
import time

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from django.core.mail import send_mail
from django.utils import timezone
from django_apscheduler.jobstores import DjangoJobStore

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone='UTC')
scheduler.add_jobstore(DjangoJobStore(), 'default')


def _execute_endpoint(endpoint_id: int, task_id: int | None = None) -> None:
    """Fetch the endpoint and persist an APIResult.  Called by the scheduler."""
    from .models import APIEndpoint, APIResult, ScheduledTask  # avoid circular imports

    try:
        endpoint = APIEndpoint.objects.get(pk=endpoint_id)
    except APIEndpoint.DoesNotExist:
        logger.error('APIEndpoint %s not found – job aborted.', endpoint_id)
        return

    task = None
    if task_id:
        try:
            task = ScheduledTask.objects.get(pk=task_id)
        except ScheduledTask.DoesNotExist:
            pass

    start = time.monotonic()
    result = APIResult(endpoint=endpoint, scheduled_task=task)

    # Build request kwargs, applying per-endpoint credentials if configured.
    try:
        cred = endpoint.credential
        req_kwargs = cred.build_request_kwargs(endpoint.headers or {})
    except Exception:  # noqa: BLE001 – RelatedObjectDoesNotExist or similar
        req_kwargs = {'headers': dict(endpoint.headers or {})}

    try:
        response = requests.request(
            method=endpoint.method,
            url=endpoint.url,
            json=endpoint.body if endpoint.body else None,
            timeout=30,
            **req_kwargs,
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        result.status_code = response.status_code
        result.response_body = response.text
        result.response_headers = dict(response.headers)
        result.execution_time_ms = round(elapsed_ms, 2)
        result.success = response.ok
    except requests.RequestException as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        result.execution_time_ms = round(elapsed_ms, 2)
        result.success = False
        result.error_message = str(exc)
        logger.exception('Error calling endpoint %s: %s', endpoint.name, exc)

    result.save()

    # Update task metadata
    if task:
        task.last_run = timezone.now()
        task.save(update_fields=['last_run', 'updated_at'])

        if task.send_email:
            _send_result_email(task, result)


def _send_result_email(task, result) -> None:
    """Send an email notification with the API result."""
    recipients = task.get_email_recipient_list()
    if not recipients:
        return

    subject = (
        f'[UbuntuDashboard] {result.endpoint.name} – '
        f'{"OK" if result.success else "FAILED"} ({result.status_code or "N/A"})'
    )
    body_lines = [
        f'Endpoint : {result.endpoint.name}',
        f'URL      : {result.endpoint.url}',
        f'Method   : {result.endpoint.method}',
        f'Status   : {result.status_code or "N/A"}',
        f'Success  : {result.success}',
        f'Time (ms): {result.execution_time_ms}',
        f'Run at   : {result.created_at}',
        '',
    ]
    if result.error_message:
        body_lines += ['Error:', result.error_message, '']
    body_lines += ['Response body:', result.response_body[:4000]]

    try:
        send_mail(
            subject=subject,
            message='\n'.join(body_lines),
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=recipients,
            fail_silently=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('Failed to send email for task %s: %s', task.pk, exc)


def _job_id(task) -> str:
    return f'scheduled_task_{task.pk}'


def register_task(task) -> None:
    """Add or replace an APScheduler job for *task*."""
    job_id = _job_id(task)
    kwargs = dict(
        func=_execute_endpoint,
        id=job_id,
        replace_existing=True,
        kwargs={'endpoint_id': task.endpoint_id, 'task_id': task.pk},
    )
    if task.schedule_type == 'interval':
        kwargs['trigger'] = IntervalTrigger(seconds=task.interval_seconds)
    else:
        parts = task.cron_expression.strip().split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
        else:
            logger.error('Invalid cron expression for task %s: %r', task.pk, task.cron_expression)
            return
        kwargs['trigger'] = CronTrigger(
            minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
        )
    scheduler.add_job(**kwargs)
    logger.info('Registered job %s for task %s', job_id, task.pk)


def unregister_task(task) -> None:
    """Remove the APScheduler job for *task* if it exists."""
    job_id = _job_id(task)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info('Removed job %s', job_id)


def start() -> None:
    """Start the background scheduler and register all enabled tasks."""
    from .models import ScheduledTask  # avoid circular imports at module level

    if scheduler.running:
        return

    scheduler.start()
    logger.info('APScheduler started.')

    for task in ScheduledTask.objects.filter(is_enabled=True).select_related('endpoint'):
        if task.endpoint.is_active:
            register_task(task)
