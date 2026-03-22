from django.contrib import admin

from .models import APICredential, APIEndpoint, APIResult, ScheduledTask


class APICredentialInline(admin.StackedInline):
    model = APICredential
    extra = 0
    min_num = 0
    max_num = 1
    can_delete = True
    verbose_name = 'Credentials'
    verbose_name_plural = 'Credentials'
    fieldsets = [
        (None, {'fields': ['auth_type']}),
        ('Bearer / API Key / Custom Header', {
            'fields': ['token', 'header_name', 'query_param_name'],
            'classes': ['collapse'],
        }),
        ('Basic Auth', {
            'fields': ['username', 'password'],
            'classes': ['collapse'],
        }),
    ]


@admin.register(APIEndpoint)
class APIEndpointAdmin(admin.ModelAdmin):
    list_display = ['name', 'method', 'url', 'auth_type_display', 'is_active', 'owner', 'created_at']
    list_filter = ['method', 'is_active', 'owner']
    search_fields = ['name', 'url', 'description']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [APICredentialInline]
    fieldsets = [
        (None, {'fields': ['name', 'description', 'is_active', 'owner']}),
        ('Request', {'fields': ['url', 'method', 'headers', 'body']}),
        ('Timestamps', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    @admin.display(description='Auth Type')
    def auth_type_display(self, obj):
        try:
            return obj.credential.get_auth_type_display()
        except APICredential.DoesNotExist:
            return '—'


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    list_display = [
        'endpoint', 'schedule_type', 'interval_seconds', 'cron_expression',
        'is_enabled', 'send_email', 'last_run', 'next_run',
    ]
    list_filter = ['schedule_type', 'is_enabled', 'send_email']
    search_fields = ['endpoint__name']
    readonly_fields = ['last_run', 'next_run', 'created_at', 'updated_at']
    fieldsets = [
        (None, {'fields': ['endpoint', 'is_enabled']}),
        ('Schedule', {'fields': ['schedule_type', 'interval_seconds', 'cron_expression']}),
        ('Notifications', {'fields': ['send_email', 'email_recipients']}),
        ('Runtime info', {'fields': ['last_run', 'next_run'], 'classes': ['collapse']}),
        ('Timestamps', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from . import scheduler as sched
        if obj.is_enabled and obj.endpoint.is_active:
            sched.register_task(obj)
        else:
            sched.unregister_task(obj)

    def delete_model(self, request, obj):
        from . import scheduler as sched
        sched.unregister_task(obj)
        super().delete_model(request, obj)


@admin.register(APIResult)
class APIResultAdmin(admin.ModelAdmin):
    list_display = [
        'endpoint', 'status_code', 'success', 'execution_time_ms', 'created_at',
    ]
    list_filter = ['success', 'endpoint']
    search_fields = ['endpoint__name', 'response_body', 'error_message']
    readonly_fields = [
        'endpoint', 'scheduled_task', 'status_code', 'response_body',
        'response_headers', 'execution_time_ms', 'success', 'error_message', 'created_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
