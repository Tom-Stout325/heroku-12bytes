from django.contrib import admin
from .models import PilotProfile, Training


class PilotProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'license_number']


class TrainingAdmin(admin.ModelAdmin):
    list_display = ['pilot', 'title']
    
    
admin.site.register(PilotProfile, PilotProfileAdmin)
admin.site.register(Training, TrainingAdmin)
