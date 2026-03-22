"""
Tests for the api app.

Covers:
- Model creation and str representation
- REST API CRUD for APIEndpoint, ScheduledTask, APIResult
- Endpoint `run` action (mocked HTTP call)
- Serializer validation
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import APIEndpoint, APIResult, ScheduledTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username='testuser', password='testpass123'):
    return User.objects.create_user(username=username, password=password)


def make_endpoint(owner, **kwargs):
    defaults = dict(
        name='Test API',
        url='https://example.com/api',
        method='GET',
        is_active=True,
    )
    defaults.update(kwargs)
    return APIEndpoint.objects.create(owner=owner, **defaults)


def make_task(endpoint, **kwargs):
    defaults = dict(
        schedule_type='interval',
        interval_seconds=3600,
        is_enabled=True,
    )
    defaults.update(kwargs)
    return ScheduledTask.objects.create(endpoint=endpoint, **defaults)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class APIEndpointModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.endpoint = make_endpoint(self.user)

    def test_str(self):
        self.assertIn('Test API', str(self.endpoint))
        self.assertIn('GET', str(self.endpoint))

    def test_defaults(self):
        self.assertTrue(self.endpoint.is_active)
        self.assertEqual(self.endpoint.method, 'GET')
        self.assertEqual(self.endpoint.headers, {})
        self.assertEqual(self.endpoint.body, {})


class ScheduledTaskModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.endpoint = make_endpoint(self.user)
        self.task = make_task(self.endpoint, send_email=True,
                              email_recipients='a@test.com, b@test.com')

    def test_str(self):
        self.assertIn('Test API', str(self.task))

    def test_get_email_recipient_list(self):
        recipients = self.task.get_email_recipient_list()
        self.assertEqual(recipients, ['a@test.com', 'b@test.com'])

    def test_get_email_recipient_list_empty(self):
        self.task.email_recipients = ''
        self.assertEqual(self.task.get_email_recipient_list(), [])


class APIResultModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.endpoint = make_endpoint(self.user)
        self.result = APIResult.objects.create(
            endpoint=self.endpoint,
            status_code=200,
            success=True,
            response_body='{"ok": true}',
        )

    def test_str(self):
        self.assertIn('Test API', str(self.result))
        self.assertIn('200', str(self.result))


# ---------------------------------------------------------------------------
# API endpoint CRUD tests
# ---------------------------------------------------------------------------

class APIEndpointAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        self.other_user = make_user('other', 'otherpass123')
        self.client.force_authenticate(user=self.user)

    def _list_url(self):
        return reverse('apiendpoint-list')

    def _detail_url(self, pk):
        return reverse('apiendpoint-detail', args=[pk])

    def test_create_endpoint(self):
        data = {'name': 'My API', 'url': 'https://api.example.com/', 'method': 'GET'}
        response = self.client.post(self._list_url(), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['owner'], self.user.username)

    def test_list_only_own_endpoints(self):
        make_endpoint(self.user, name='Mine')
        make_endpoint(self.other_user, name='Not Mine')
        response = self.client.get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [e['name'] for e in response.data['results']]
        self.assertIn('Mine', names)
        self.assertNotIn('Not Mine', names)

    def test_update_endpoint(self):
        ep = make_endpoint(self.user)
        response = self.client.patch(
            self._detail_url(ep.pk), {'name': 'Updated'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated')

    def test_delete_endpoint(self):
        ep = make_endpoint(self.user)
        response = self.client.delete(self._detail_url(ep.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_other_user_cannot_update(self):
        ep = make_endpoint(self.user)
        self.client.force_authenticate(user=self.other_user)
        response = self.client.patch(
            self._detail_url(ep.pk), {'name': 'Hacked'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('api.views.requests.request')
    def test_run_action(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"data": 1}'
        mock_resp.headers = {'Content-Type': 'application/json'}
        mock_resp.ok = True
        mock_request.return_value = mock_resp

        ep = make_endpoint(self.user)
        url = reverse('apiendpoint-run', args=[ep.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['status_code'], 200)


# ---------------------------------------------------------------------------
# ScheduledTask API tests
# ---------------------------------------------------------------------------

class ScheduledTaskAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        self.client.force_authenticate(user=self.user)
        self.endpoint = make_endpoint(self.user)

    def _list_url(self):
        return reverse('scheduledtask-list')

    def _detail_url(self, pk):
        return reverse('scheduledtask-detail', args=[pk])

    @patch('api.views.ScheduledTaskViewSet._sync_scheduler')
    def test_create_interval_task(self, mock_sync):
        data = {
            'endpoint': self.endpoint.pk,
            'schedule_type': 'interval',
            'interval_seconds': 300,
        }
        response = self.client.post(self._list_url(), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_sync.assert_called_once()

    @patch('api.views.ScheduledTaskViewSet._sync_scheduler')
    def test_create_cron_task(self, mock_sync):
        data = {
            'endpoint': self.endpoint.pk,
            'schedule_type': 'cron',
            'cron_expression': '0 9 * * 1-5',
        }
        response = self.client.post(self._list_url(), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_interval_task_missing_interval(self):
        data = {
            'endpoint': self.endpoint.pk,
            'schedule_type': 'interval',
        }
        response = self.client.post(self._list_url(), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_cron_task_missing_expression(self):
        data = {
            'endpoint': self.endpoint.pk,
            'schedule_type': 'cron',
        }
        response = self.client.post(self._list_url(), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('api.views.ScheduledTaskViewSet._sync_scheduler')
    def test_delete_task_calls_unregister(self, mock_sync):
        task = make_task(self.endpoint)
        with patch('api.scheduler.unregister_task') as mock_unreg:
            response = self.client.delete(self._detail_url(task.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_unreg.assert_called_once()


# ---------------------------------------------------------------------------
# APIResult API tests
# ---------------------------------------------------------------------------

class APIResultAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        self.client.force_authenticate(user=self.user)
        self.endpoint = make_endpoint(self.user)

    def test_list_results(self):
        APIResult.objects.create(endpoint=self.endpoint, status_code=200, success=True)
        response = self.client.get(reverse('apiresult-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_filter_results_by_endpoint(self):
        other_ep = make_endpoint(self.user, name='Other')
        APIResult.objects.create(endpoint=self.endpoint, status_code=200, success=True)
        APIResult.objects.create(endpoint=other_ep, status_code=404, success=False)
        url = reverse('apiresult-list') + f'?endpoint={self.endpoint.pk}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_results_are_read_only(self):
        result = APIResult.objects.create(endpoint=self.endpoint, status_code=200, success=True)
        url = reverse('apiresult-detail', args=[result.pk])
        response = self.client.put(url, {'status_code': 500}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
