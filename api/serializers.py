from rest_framework import serializers

from .models import APICredential, APIEndpoint, APIResult, ScheduledTask


class APICredentialSerializer(serializers.ModelSerializer):
    """Credential data nested inside APIEndpointSerializer.

    Sensitive fields (token, password, client_secret) are write-only so
    they are never returned in API responses.
    """

    token = serializers.CharField(
        max_length=2000, write_only=True, required=False, allow_blank=True,
        style={'input_type': 'password'},
    )
    password = serializers.CharField(
        max_length=500, write_only=True, required=False, allow_blank=True,
        style={'input_type': 'password'},
    )
    client_secret = serializers.CharField(
        max_length=2000, write_only=True, required=False, allow_blank=True,
        style={'input_type': 'password'},
    )

    class Meta:
        model = APICredential
        fields = [
            'auth_type',
            # Token / API key / custom header
            'token',
            'header_name',
            'query_param_name',
            # Basic / Digest
            'username',
            'password',
            # OAuth 2.0 Client Credentials
            'client_id',
            'client_secret',
            'token_url',
            'oauth2_scope',
            # Always-applied overlays
            'extra_headers',
            'extra_query_params',
        ]


class APIEndpointSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source='owner.username')
    credential = APICredentialSerializer(required=False)

    class Meta:
        model = APIEndpoint
        fields = [
            'id', 'name', 'description', 'url', 'method',
            'headers', 'body', 'is_active', 'owner',
            'credential',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']

    def create(self, validated_data):
        credential_data = validated_data.pop('credential', None)
        endpoint = super().create(validated_data)
        if credential_data is not None:
            APICredential.objects.create(endpoint=endpoint, **credential_data)
        return endpoint

    def update(self, instance, validated_data):
        credential_data = validated_data.pop('credential', None)
        instance = super().update(instance, validated_data)
        if credential_data is not None:
            APICredential.objects.update_or_create(
                endpoint=instance,
                defaults=credential_data,
            )
        return instance


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

