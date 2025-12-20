# Register your models here.
from django.contrib import admin
from .models import ContactFeedback

@admin.register(ContactFeedback)
class ContactFeedbackAdmin(admin.ModelAdmin):
    list_display = ('email', 'submitted_at')
    list_filter = ('submitted_at',)
    search_fields = ('email', 'feedback')
