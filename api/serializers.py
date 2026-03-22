from rest_framework import serializers

from .models import APIEndpoint, APIResult, ScheduledTask


class APIEndpointSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = APIEndpoint
        fields = [
            'id', 'name', 'description', 'url', 'method',
            'headers', 'body', 'is_active', 'owner',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']


class ScheduledTaskSerializer(serializers.ModelSerializer):
    endpoint_name = serializers.ReadOnlyField(source='endpoint.name')

    class Meta:
        model = ScheduledTask
        fields = [
            'id', 'endpoint', 'endpoint_name', 'schedule_type',
            'interval_seconds', 'cron_expression', 'is_enabled',
            'send_email', 'email_recipients',
            'last_run', 'next_run',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'endpoint_name', 'last_run', 'next_run', 'created_at', 'updated_at']

    def validate(self, attrs):
        schedule_type = attrs.get('schedule_type', 'interval')
        if schedule_type == 'interval' and not attrs.get('interval_seconds'):
            raise serializers.ValidationError(
                'interval_seconds is required when schedule_type is "interval".'
            )
        if schedule_type == 'cron' and not attrs.get('cron_expression', '').strip():
            raise serializers.ValidationError(
                'cron_expression is required when schedule_type is "cron".'
            )
        return attrs


class APIResultSerializer(serializers.ModelSerializer):
    endpoint_name = serializers.ReadOnlyField(source='endpoint.name')

    class Meta:
        model = APIResult
        fields = [
            'id', 'endpoint', 'endpoint_name', 'scheduled_task',
            'status_code', 'response_body', 'response_headers',
            'execution_time_ms', 'success', 'error_message',
            'created_at',
        ]
        read_only_fields = fields
