from django.urls import path
from django.conf import settings
from django.conf.urls.static import static



from .views import *

from .forms import *


# Incident report wizard steps
wizard_forms = [
    ("event", EventDetailsForm),
    ("general", GeneralInfoForm),
    ("equipment", EquipmentDetailsForm),
    ("environment", EnvironmentalConditionsForm),
    ("witness", WitnessForm),
    ("action", ActionTakenForm),
    ("followup", FollowUpForm),
]


urlpatterns = [

    path('docs', documents, name='documents'),
    path('drone-portal/', drone_portal, name='drone_portal'),
    
    # Incident Reporting
    path('incident-reporting', incident_reporting_system, name='incident_reporting_system'),
    path('incidents/', incident_report_list, name='incident_report_list'),
    path('incidents/<int:pk>/', incident_report_detail, name='incident_detail'),
    path('report/new/', IncidentReportWizard.as_view(wizard_forms), name='submit_incident_report'),
    path('report/success/', incident_report_success, name='incident_report_success'),
    path('report/pdf/<int:pk>/', incident_report_pdf, name='incident_report_pdf'),

    # SOPs and General Documents
    path('sops/', sop_list, name='sop_list'),
    path('sops/upload/', sop_upload, name='sop_upload'),
    path("sops/delete/<int:pk>/", delete_sop, name="delete_sop"),
    path('documents/', general_document_list, name='general_document_list'),
    path('documents/upload/', upload_general_document, name='upload_general_document'),
    path('documents/delete/<int:pk>/', delete_document, name='delete_document'),


    # Equipment
    path('equipment/', equipment_list, name='equipment_list'),
    path('equipment/create/', equipment_create, name='equipment_create'),
    path('equipment/pdf/', equipment_pdf, name='equipment_pdf'),
    path('equipment/<uuid:pk>/edit/', equipment_edit, name='equipment_edit'),
    path('equipment/<uuid:pk>/delete/', equipment_delete, name='equipment_delete'),
    path('equipment/<uuid:pk>/pdf/', equipment_pdf_single, name='equipment_pdf_single'),
    path('equipment/export/csv/', export_equipment_csv, name='export_equipment_csv'),


    # Flight Logs
    path('flightlogs/', flightlog_list, name='flightlog_list'),
    path('flight-upload/', upload_flightlog_csv, name='flightlog_upload'),
    path('flightlogs/<int:pk>/', flightlog_detail, name='flightlog_detail'),
    path('flightlogs/<int:pk>/edit/', flightlog_edit, name='flightlog_edit'),
    path('flightlogs/<int:pk>/delete/', flightlog_delete, name='flightlog_delete'),
    path('flightlogs/<int:pk>/pdf/', flightlog_pdf, name='flightlog_pdf'),
    path('flightlogs/export/csv/', export_flightlogs_csv, name='export_flightlogs_csv'),
    
    
    # flight maps
    path('map/', flight_map_view, name='flight_map'),
    path("map/embed/", flight_map_embed, name="flight_map_embed")


]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
