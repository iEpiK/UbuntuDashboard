import logging

import requests
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import APIEndpoint, APIResult, ScheduledTask
from .serializers import APIEndpointSerializer, APIResultSerializer, ScheduledTaskSerializer

logger = logging.getLogger(__name__)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Allow the owner of an APIEndpoint to edit it; others can only read."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        endpoint = obj if isinstance(obj, APIEndpoint) else obj.endpoint
        return endpoint.owner == request.user


class APIEndpointViewSet(viewsets.ModelViewSet):
    """
    CRUD for user-defined API endpoints.

    Extra action:
      POST /api/endpoints/{id}/run/  — trigger a one-off call immediately
    """

    serializer_class = APIEndpointSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        return APIEndpoint.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['post'], url_path='run')
    def run(self, request, pk=None):
        """Immediately execute the endpoint and return the result."""
        endpoint = self.get_object()
        result = _call_endpoint(endpoint)
        serializer = APIResultSerializer(result)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ScheduledTaskViewSet(viewsets.ModelViewSet):
    """
    CRUD for scheduled tasks that automatically call an APIEndpoint.

    Creating or updating a task registers / updates the APScheduler job.
    Deleting a task removes the job.
    """

    serializer_class = ScheduledTaskSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        return ScheduledTask.objects.filter(endpoint__owner=self.request.user)

    def perform_create(self, serializer):
        task = serializer.save()
        self._sync_scheduler(task)

    def perform_update(self, serializer):
        task = serializer.save()
        self._sync_scheduler(task)

    def perform_destroy(self, instance):
        from . import scheduler as sched
        sched.unregister_task(instance)
        instance.delete()

    @staticmethod
    def _sync_scheduler(task):
        from . import scheduler as sched
        if task.is_enabled and task.endpoint.is_active:
            sched.register_task(task)
        else:
            sched.unregister_task(task)


class APIResultViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to API call results."""

    serializer_class = APIResultSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = APIResult.objects.filter(endpoint__owner=self.request.user)
        endpoint_id = self.request.query_params.get('endpoint')
        if endpoint_id:
            qs = qs.filter(endpoint_id=endpoint_id)
        return qs


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _call_endpoint(endpoint: APIEndpoint, task: ScheduledTask | None = None) -> APIResult:
    """Synchronously call *endpoint* and persist an :class:`APIResult`."""
    import time

    start = time.monotonic()
    result = APIResult(endpoint=endpoint, scheduled_task=task)

    try:
        response = requests.request(
            method=endpoint.method,
            url=endpoint.url,
            headers=endpoint.headers or {},
            json=endpoint.body if endpoint.body else None,
            timeout=30,
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
    return result
