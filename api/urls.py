from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import APIEndpointViewSet, APIResultViewSet, ScheduledTaskViewSet

router = DefaultRouter()
router.register(r'endpoints', APIEndpointViewSet, basename='apiendpoint')
router.register(r'tasks', ScheduledTaskViewSet, basename='scheduledtask')
router.register(r'results', APIResultViewSet, basename='apiresult')

urlpatterns = [
    path('', include(router.urls)),
]
