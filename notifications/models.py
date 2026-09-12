from django.db import models
from django.utils import timezone

class EmailNotification(models.Model):
    appointment = models.ForeignKey('clinic.Appointment', on_delete=models.CASCADE, null=True, blank=True)
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    text_body = models.TextField()
    html_body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.CharField(max_length=120, blank=True)
    class Meta:
        ordering = ['id']
