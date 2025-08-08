from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from formtools.wizard.views import SessionWizardView
from django.template.loader import render_to_string
from django.template.loader import get_template
# from django.templatetags.static import static
from django.conf.urls.static import static
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils.timezone import now
from django.http import HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from datetime import timedelta
from weasyprint import HTML 
import os
import csv
import uuid
import tempfile
import re
from .forms import *
from .models import *
from datetime import timedelta
from django.db.models import Count

from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
import traceback
import sys

@login_required
def drone_portal(request):
    total_flights = FlightLog.objects.count()
    active_drones = FlightLog.objects.all()
    total_flight_time = timedelta()
    total_photos = 0
    total_videos = 0

    all_logs = FlightLog.objects.all()
    for log in all_logs:
        if log.air_time:
            total_flight_time += log.air_time
        if log.photos:
            total_photos += log.photos
        if log.videos:
            total_videos += log.videos

    active_drones = (
        FlightLog.objects.exclude(drone_serial='')
        .values_list('drone_serial', flat=True)
        .distinct()
        .count()
    )

    context = {
        'active_drones': active_drones,
        'total_flights': total_flights,
        'total_flight_time': total_flight_time,
        'total_photos': total_photos,
        'total_videos': total_videos,
        'current_page': 'home',
        'highest_altitude_flight': FlightLog.objects.order_by('-max_altitude_ft').first(),
        'fastest_speed_flight': FlightLog.objects.order_by('-max_speed_mph').first(),
        'longest_flight': FlightLog.objects.order_by('-max_distance_ft').first(),
        }


    return render(request, 'flightplan/drone_portal.html', context)




#=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->  D O C U M E N T S   V I E W S


@login_required
def documents(request):
    context = {'current_page': 'document'}  
    return render(request, 'flightplan/drone_portal.html', context)


@login_required
def incident_reporting_system(request):
    query = request.GET.get('q', '').strip()
    reports = DroneIncidentReport.objects.all().order_by('-report_date')
    if query:
        reports = reports.filter(
            Q(reported_by__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query)
        )
    context = {
        'incident_reports': reports,
        'search_query': query,
        'current_page': 'incidents' 
        
    }
    return render(request, 'flightplan/incident_reporting_system.html', context)


@login_required
def incident_report_pdf(request, pk):
    report = get_object_or_404(DroneIncidentReport, pk=pk)
    logo_path = request.build_absolute_uri(static("images/logo2.png"))
    context = {
        'report': report,
        'logo_path': logo_path,
        'now': timezone.now(),
        'current_page': 'incidents' 
        
    }
    html_string = render_to_string('flightplan/incident_report_pdf.html', context, request=request)
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    pdf_content = html.write_pdf()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="incident_report_{pk}.pdf"'
    response.write(pdf_content)
    return response

FORMS = [
    ("general", GeneralInfoForm),
    ("event", EventDetailsForm),
    ("equipment", EquipmentDetailsForm),
    ("environment", EnvironmentalConditionsForm),
    ("witness", WitnessForm),
    ("action", ActionTakenForm),
    ("followup", FollowUpForm),
]

TEMPLATES = {
    "general": "flightplan/wizard_form.html",
    "event": "flightplan/wizard_form.html",
    "equipment": "flightplan/wizard_form.html",
    "environment": "flightplan/wizard_form.html",
    "witness": "flightplan/wizard_form.html",
    "action": "flightplan/wizard_form.html",
    "followup": "flightplan/wizard_form.html",
}

class IncidentReportWizard(SessionWizardView, LoginRequiredMixin):
    template_name = 'flightplan/incident_report_form.html'

    def get(self, request, *args, **kwargs):
        self.storage.reset()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        current_step = self.steps.step1 + 1
        total_steps = self.steps.count
        progress_percent = int((current_step / total_steps) * 100)
        context.update({
            'current_step': current_step,
            'total_steps': total_steps,
            'progress_percent': progress_percent,
            'current_page': 'incidents' 
            
        })
        return context

    def done(self, form_list, **kwargs):
        data = {}
        for form in form_list:
            data.update(form.cleaned_data)
        report = DroneIncidentReport.objects.create(**data)
        context = {'report': report, 'current_page': 'incidents'} 
        
        html_string = render_to_string('flightplan/incident_report_pdf.html', context, request=self.request)
        html = HTML(string=html_string, base_url=self.request.build_absolute_uri())
        pdf_content = html.write_pdf()
        unique_id = uuid.uuid4()
        filename = f'flightplan/incident_report_{report.pk}_{unique_id}.pdf'
        filepath = os.path.join(settings.MEDIA_ROOT, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(pdf_content)
        pdf_url = os.path.join(settings.MEDIA_URL, filename)
        context = {
            'form_data': data,
            'pdf_url': pdf_url,
            'current_page': 'incidents' 
            
        }
        return render(self.request, 'flightplan/incident_report_success.html', context)


@login_required
def incident_report_success(request):
    pdf_url = request.GET.get('pdf_url', None)
    context = {'pdf_url': pdf_url, 'current_page': 'incidents'} 
    
    return render(request, 'flightplan/report_success.html', context)


@login_required
def incident_report_list(request):
    query = request.GET.get('q', '')
    reports = DroneIncidentReport.objects.all()
    if query:
        reports = reports.filter(
            Q(reported_by__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query)
        )
    context = {
        'incident_reports': reports.order_by('-report_date'),
        'search_query': query,
        'current_page': 'incidents' 
        
    }
    return render(request, 'flightplan/incident_reporting_system.html', context)


@login_required
def incident_report_detail(request, pk):
    report = get_object_or_404(DroneIncidentReport, pk=pk)
    context = {'report': report, 'current_page': 'incidents'} 
    
    return render(request, 'flightplan/incident_report_detail.html', context)


@login_required
def sop_upload(request):
    if request.method == 'POST':
        form = SOPDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "SOP added successfully.")
            return redirect('sop_list')
        else:
            messages.error(request, "There was a problem uploading the document.")
    else:
        form = SOPDocumentForm()
    context = {'form': form, 'current_page': 'sop'} 
    return render(request, 'flightplan/sop_upload.html', context)




@login_required
def sop_list(request):
    query = request.GET.get('q', '')
    sops = SOPDocument.objects.all()

    if query:
        sops = sops.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query)
        )

    sops = sops.order_by('-created_at')
    paginator = Paginator(sops, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'sops': page_obj,
        'page_obj': page_obj,
        'search_query': query,
        'current_page': 'sop'
    }
    return render(request, 'flightplan/sop_list.html', context)



@login_required
def delete_sop(request, pk):
    sop = get_object_or_404(SOPDocument, pk=pk)
    sop.delete()
    messages.success(request, f"SOP '{sop.title}' deleted successfully.")
    return redirect('sop_list') 


@login_required
def general_document_list(request):
    search_query = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '')
    documents = GeneralDocument.objects.all().order_by('-uploaded_at')
    if search_query:
        documents = documents.filter(title__icontains=search_query)
    if selected_category:
        documents = documents.filter(category=selected_category)
    categories = GeneralDocument.objects.values_list('category', flat=True).distinct()
    paginator = Paginator(documents, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'documents': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': selected_category,
        'search_query': search_query,
        'current_page': 'documents'  
    }
    return render(request, 'flightplan/general_list.html', context)


@login_required
def upload_general_document(request):
    if request.method == 'POST':
        form = GeneralDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "File added successfully.")
            return redirect('general_document_list')
        else:
            messages.error(request, "There was a problem uploading the document.")
    else:
        form = GeneralDocumentForm()
    context = {'form': form, 'current_page': 'document'}  
    return render(request, 'flightplan/upload_general.html', context)


@login_required
def delete_document(request, pk):
    doc = get_object_or_404(GeneralDocument, pk=pk)
    if request.method == 'POST':
        doc.delete()
        messages.success(request, "Document deleted successfully.")
    return redirect('general_document_list')


#=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->  E Q U I P M E N T   V I E W S


@login_required
def equipment_list(request):
    equipment = Equipment.objects.all().order_by('-purchase_date', 'name')

    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('equipment_list')
    else:
        form = EquipmentForm()

    context = {
        'equipment': equipment,
        'form': form,
        'current_page': 'equipment',
    }
    return render(request, 'flightplan/equipment_list.html', context)


@login_required
def equipment_create(request):
    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('equipment_list')
        else:
            if not form.is_valid():
                print("POST data:", request.POST)
                print("FILES data:", request.FILES)
                print("Form errors:", form.errors)

                print("Form errors:", form.errors)
    else:
        form = EquipmentForm()
    return render(request, 'flightplan/equipment_list.html', {
        'form': form,
        'equipment': Equipment.objects.all(),
    })



@login_required
def equipment_edit(request, pk):
    item = get_object_or_404(Equipment, pk=pk)

    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES, instance=item)

        if form.is_valid():
            form.save()
            return redirect('equipment_list')
    else:
        form = EquipmentForm(instance=item)

    return render(request, 'flightplan/equipment_edit.html', {
        'form': form,
        'item': item
    })
    

@login_required
def equipment_delete(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        equipment.delete()
        messages.success(request, f'Equipment "{equipment.name}" deleted.')
        return redirect('equipment_list')
    return render(request, 'flightplan/equipment_confirm_delete.html', {
        'equipment': equipment,
        'current_page': 'equipment'
    })


@login_required
def equipment_pdf(request):
    equipment = Equipment.objects.all().order_by('equipment_type', 'name')
    logo_url = request.build_absolute_uri(static('images/logo.png'))

    context = {
        'equipment': equipment,
        'logo_url': logo_url,
    }

    template = get_template('flightplan/equipment_pdf.html')
    html_string = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename=equipment_inventory.pdf'

    with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(target=tmp_file.name)
        tmp_file.seek(0)
        response.write(tmp_file.read())

    return response


@login_required
def equipment_pdf_single(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    logo_url = request.build_absolute_uri(static('images/logo.png'))

    faa_is_pdf = equipment.faa_certificate.name.lower().endswith('.pdf') if equipment.faa_certificate else False
    receipt_is_pdf = equipment.receipt.name.lower().endswith('.pdf') if equipment.receipt else False

    context = {
        'item': equipment,
        'logo_url': logo_url,
        'faa_is_pdf': faa_is_pdf,
        'receipt_is_pdf': receipt_is_pdf,
    }

    template = get_template('flightplan/equipment_pdf_single.html')
    html_string = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename={equipment.name}_equipment.pdf'

    with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
        HTML(string=html_string).write_pdf(target=tmp_file.name)
        tmp_file.seek(0)
        response.write(tmp_file.read())

    return response


import csv
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from flightplan.models import Equipment

@login_required
def export_equipment_csv(request):
    equipment = Equipment.objects.all()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="equipment.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Name',
        'Type',
        'Brand',
        'Model',
        'Serial Number',
        'FAA Number',
        'FAA Certificate URL',
        'Purchase Date',
        'Purchase Cost',
        'Receipt URL',
        'Date Sold',
        'Sale Price',
        'Deducted Full Cost',
        'Active',
        'Notes',
    ])

    for e in equipment:
        writer.writerow([
            e.name,
            e.get_equipment_type_display(),  # human-readable label for choices
            e.brand,
            e.model,
            e.serial_number,
            e.faa_number,
            e.faa_certificate.url if e.faa_certificate else '',
            e.purchase_date,
            e.purchase_cost,
            e.receipt.url if e.receipt else '',
            e.date_sold,
            e.sale_price,
            'Yes' if e.deducted_full_cost else 'No',
            'Yes' if e.active else 'No',
            e.notes.replace('\n', ' ').replace('\r', '') if e.notes else '',
        ])

    return response

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-> F L I G H T L O G   V I E W S



@login_required
def flightlog_list(request):
    location_filter = request.GET.get('location', '').strip()
    log_list = FlightLog.objects.all()

    if location_filter:
        log_list = log_list.filter(
            Q(takeoff_address__icontains=location_filter) |
            Q(takeoff_latlong__icontains=location_filter)
        )

    log_list = log_list.order_by('-flight_date')
    paginator = Paginator(log_list, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'logs': page_obj,
        'current_page': 'flightlogs',
        'location_filter': location_filter,
    }
    return render(request, 'flightplan/flightlog_list.html', context)



@login_required
def export_flightlogs_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="flight_logs.csv"'

    writer = csv.writer(response)
    fields = [field.name for field in FlightLog._meta.fields]
    writer.writerow(fields)

    for log in FlightLog.objects.all().order_by('-flight_date'):
        row = [getattr(log, field) for field in fields]
        writer.writerow(row)

    return response


@login_required
def flightlog_detail(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    context = {'log': log, 'current_page': 'flightlogs'}  
    return render(request, 'flightplan/flightlog_detail.html', context)


@login_required
def flightlog_edit(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    if request.method == 'POST':
        form = FlightLogCSVUploadForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            return redirect('flightlog_list')
    else:
        form = FlightLogCSVUploadForm(instance=log)
    context = {'form': form, 'log': log, 'current_page': 'flightlogs'}  
    return render(request, 'flightplan/flightlog_form.html', context)


@login_required
def flightlog_business(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    if request.method == 'POST':
        form = FlightLogCSVUploadForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            return redirect('flightlog_list')
    else:
        form = FlightLogCSVUploadForm(instance=log)
    context = {'form': form, 'log': log, 'current_page': 'flightlogs'}  
    return render(request, 'flightplan/flightlog_form.html', context)


@login_required
def flightlog_delete(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    if request.method == 'POST':
        log.delete()
        return redirect('flightlog_list')
    context = {'log': log, 'current_page': 'flightlogs'}  
    return render(request, 'flightplan/flightlog_confirm_delete.html', context)


@login_required
def flightlog_pdf(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    context = {'log': log, 'current_page': 'flightlogs'}  
    html_string = render_to_string('flightplan/flightlog_detail_pdf.html', context)
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp_file:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(tmp_file.name)
        tmp_file.seek(0)
        response = HttpResponse(tmp_file.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="FlightLog_{log.pk}.pdf"'
        return response

def safe_float(value):
    try:
        return float(re.sub(r'[^0-9.-]', '', value)) if value else None
    except:
        return None

def safe_int(value):
    try:
        return int(float(re.sub(r'[^0-9.-]', '', value))) if value else None
    except:
        return None



def safe_int(val):
    try:
        return int(val)
    except:
        return None

def safe_float(val):
    try:
        return float(val)
    except:
        return None




@login_required
def upload_flightlog_csv(request):
    if request.method == 'POST':
        form = FlightLogCSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['csv_file']
            decoded = file.read().decode('utf-8-sig').splitlines()
            reader = csv.DictReader(decoded)
            reader.fieldnames = [field.strip().replace('\ufeff', '') for field in reader.fieldnames]

            # Header alias mapping
            field_aliases = {
                "Flight/Service Date": "Flight Date/Time"
            }

            for row in reader:
                # Normalize column keys
                row = {field_aliases.get(k.strip(), k.strip()): (v.strip() if v else "") for k, v in row.items()}

                if not row.get("Flight Date/Time"):
                    print("Skipping row: missing Flight Date/Time")
                    continue

                try:
                    clean_dt = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', row["Flight Date/Time"])
                    dt = datetime.strptime(clean_dt, "%b %d, %Y %I:%M%p")
                    flight_date = dt.date()
                    landing_time = dt.time()
                except Exception as e:
                    print("Skipping row: invalid date/time format", e)
                    continue

                try:
                    air_seconds = safe_int(row.get("Air Seconds")) or 0
                    air_time = timedelta(seconds=air_seconds)

                    FlightLog.objects.create(
                        flight_date=flight_date,
                        flight_title=row.get("Flight Title", ""),
                        flight_description=row.get("Flight Description", ""),
                        pilot_in_command=row.get("Pilot-in-Command", ""),
                        license_number=row.get("License Number", ""),
                        takeoff_latlong=row.get("Takeoff Lat/Long", ""),
                        takeoff_address=row.get("Takeoff Address", ""),
                        landing_time=landing_time,
                        air_time=air_time,
                        above_sea_level_ft=safe_float(row.get("Above Sea Level (Feet)")),
                        drone_name=row.get("Drone Name", ""),
                        drone_type=row.get("Drone Type", ""),
                        drone_serial=row.get("Drone Serial Number", ""),
                        drone_reg_number=row.get("Drone Registration Number", ""),
                        flight_application=row.get("Flight App", ""),
                        remote_id=row.get("Remote ID", ""),
                        battery_name=row.get("Battery Name", ""),
                        battery_serial_printed=row.get("Bat Printed Serial", ""),
                        battery_serial_internal=row.get("Bat Internal Serial", ""),
                        takeoff_battery_pct=safe_int(row.get("Takeoff Bat %").replace("%", "")),
                        takeoff_mah=safe_int(row.get("Takeoff mAh")),
                        takeoff_volts=safe_float(row.get("Takeoff Volts")),
                        landing_battery_pct=safe_int(row.get("Landing Bat %").replace("%", "")),
                        landing_mah=safe_int(row.get("Landing mAh")),
                        landing_volts=safe_float(row.get("Landing Volts")),
                        max_altitude_ft=safe_float(row.get("Max Altitude (Feet)")),
                        max_distance_ft=safe_float(row.get("Max Distance (Feet)")),
                        max_battery_temp_f=safe_float(row.get("Max Bat Temp (f)")),
                        max_speed_mph=safe_float(row.get("Max Speed (mph)")),
                        total_mileage_ft=safe_float(row.get("Total Mileage (Feet)")),
                        signal_score=safe_float(row.get("Signal Score")),
                        max_compass_rate=safe_float(row.get("Max Compass Rate")),
                        avg_wind=safe_float(row.get("Avg Wind")),
                        max_gust=safe_float(row.get("Max Gust")),
                        signal_losses=safe_int(row.get("Signal Losses (>1 sec)")),
                        ground_weather_summary=row.get("Ground Weather Summary", ""),
                        ground_temp_f=safe_float(row.get("Ground Temperature (f)")),
                        visibility_miles=safe_float(row.get("Ground Visibility (Miles)")),
                        wind_speed=safe_float(row.get("Ground Wind Speed")),
                        wind_direction=row.get("Ground Wind Direction", ""),
                        cloud_cover=row.get("Cloud Cover", "").replace("%", ""),
                        humidity_pct=safe_int(row.get("Humidity", "").replace("%", "")),
                        dew_point_f=safe_float(row.get("Dew Point (f)")),
                        pressure_inhg=safe_float(row.get("Pressure")),
                        rain_rate=row.get("Rain Rate", ""),
                        rain_chance=row.get("Rain Chance", ""),
                        sunrise=row.get("Sunrise", ""),
                        sunset=row.get("Sunset", ""),
                        moon_phase=row.get("Moon Phase", ""),
                        moon_visibility=row.get("Moon Visibility", ""),
                        photos=safe_int(row.get("Photos")),
                        videos=safe_int(row.get("Videos")),
                        notes=row.get("Add Additional Notes", ""),
                        tags=row.get("Tags", ""),
                    )

                except Exception as e:
                    print("Row error:", e, row)
                    continue
            
    
            return redirect('flightlog_list')

        form = FlightLogCSVUploadForm()

#=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->     M A P S

def extract_state(address):
    """Try to pull the 2-letter state abbreviation from address like 'City, ST, USA'"""
    match = re.search(r",\s*([A-Z]{2})[, ]", address or "")
    return match.group(1) if match else None

def flight_map_view(request):
    logs = FlightLog.objects.all().order_by('-flight_date')[:100]  # limit if needed
    locations_qs = (
        FlightLog.objects
        .values('takeoff_latlong', 'takeoff_address')
        .annotate(count=Count('id'))
        .exclude(takeoff_latlong__exact="")
        .order_by('takeoff_address')
    )
    locations = list(locations_qs)

    # Extract unique states from address
    states = set()
    cities = set()
    for loc in locations:
        addr = loc.get("takeoff_address", "")
        if addr:
            cities.add(addr.strip())
            state = extract_state(addr)
            if state:
                states.add(state)

    context = {
        'locations': locations,
        'num_states': len(states),
        'num_cities': len(cities),
        'logs': logs,
    }
    return render(request, 'flightplan/map.html', context)


# PUBLIC VIEW FOR WEBSITE <------
def extract_state(address):
    match = re.search(r",\s*([A-Z]{2})[, ]", address or "")
    return match.group(1) if match else None

@xframe_options_exempt
def flight_map_embed(request):
    locations_qs = (
        FlightLog.objects
        .values('takeoff_latlong', 'takeoff_address')
        .annotate(count=Count('id'))
        .exclude(takeoff_latlong__exact="")
    )
    locations = list(locations_qs)

    states = set()
    cities = set()
    for loc in locations:
        addr = loc.get("takeoff_address", "")
        if addr:
            cities.add(addr.strip())
            state = extract_state(addr)
            if state:
                states.add(state)

    context = {
        'locations': locations,
        'num_states': len(states),
        'num_cities': len(cities),
    }
    return render(request, 'flightplan/map_embed.html', context)

