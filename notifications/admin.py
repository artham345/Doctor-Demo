from django.contrib import admin
from .models import EmailNotification

@admin.register(EmailNotification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'subject', 'sent_at', 'attempts', 'next_attempt_at', 'last_error']
    list_filter = ['sent_at']
    exclude = ['text_body', 'html_body', 'recipient']
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
