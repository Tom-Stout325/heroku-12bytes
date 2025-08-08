from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.decorators.clickjacking import xframe_options_exempt
from django.template.loader import render_to_string, get_template
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.db.models import Q, Count
from django.conf import settings

from formtools.wizard.views import SessionWizardView
from weasyprint import HTML

from datetime import datetime, timedelta
import csv
import os
import re
import tempfile
import uuid
import traceback
import sys

from django.conf.urls.static import static  # if used by pdf base_url/static refs

from .forms import *
from .models import *


# -------------------------------------------------
# Helper functions (single source of truth)
# -------------------------------------------------
def safe_int(value):
    """Parse an int from mixed strings like '85%', ' 1,234 ', or None."""
    try:
        if value is None:
            return None
        s = re.sub(r'[^0-9\-]+', '', str(value))
        return int(s) if s not in ("", "-", None, "") else None
    except Exception:
        return None


def safe_float(value):
    """Parse a float from mixed strings like '1,234.56 mph', or None."""
    try:
        if value is None:
            return None
        s = re.sub(r'[^0-9\.\-]+', '', str(value))
        return float(s) if s not in ("", "-", ".", None) else None
    except Exception:
        return None


def safe_pct(value):
    """Parse a percent value that may contain '%' or whitespace."""
    return safe_int(str(value).replace('%', '')) if value is not None else None


def extract_state(address):
    """Pull a 2-letter state abbreviation from addresses like 'City, ST, USA'."""
    match = re.search(r",\s*([A-Z]{2})[, ]", address or "")
    return match.group(1) if match else None


# -------------------------------------------------
# D R O N E   P O R T A L
# -------------------------------------------------
@login_required
def drone_portal(request):
    total_flights = FlightLog.objects.count()

    # Aggregate totals
    total_flight_time = timedelta()
    total_photos = 0
    total_videos = 0
    for log in FlightLog.objects.all():
        if log.air_time:
            total_flight_time += log.air_time
        if log.photos:
            total_photos += log.photos
        if log.videos:
            total_videos += log.videos

    # Count distinct active drones (by serial)
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


# -------------------------------------------------
# D O C U M E N T S
# -------------------------------------------------
@login_required
def documents(request):
    # If this is meant to be a dedicated page, point to your documents template.
    # Keeping your original target but normalizing current_page.
    context = {'current_page': 'documents'}
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
        'current_page': 'incidents',
    }
    return render(request, 'flightplan/incident_reporting_system.html', context)


@login_required
def incident_report_pdf(request, pk):
    report = get_object_or_404(DroneIncidentReport, pk=pk)
    logo_path = request.build_absolute_uri(static("images/logo2.png"))
    context = {
        'report': report,
        'logo_path': logo_path,
        'now': datetime.now(),
        'current_page': 'incidents',
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


class IncidentReportWizard(LoginRequiredMixin, SessionWizardView):
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
            'current_page': 'incidents',
        })
        return context

    def done(self, form_list, **kwargs):
        data = {}
        for form in form_list:
            data.update(form.cleaned_data)

        report = DroneIncidentReport.objects.create(**data)

        # Build and persist PDF to media
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
        context = {'form_data': data, 'pdf_url': pdf_url, 'current_page': 'incidents'}
        return render(self.request, 'flightplan/incident_report_success.html', context)


@login_required
def incident_report_success(request):
    pdf_url = request.GET.get('pdf_url')
    context = {'pdf_url': pdf_url, 'current_page': 'incidents'}
    return render(request, 'flightplan/report_success.html', context)


@login_required
def incident_report_list(request):
    query = request.GET.get('q', '').strip()
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
        'current_page': 'incidents',
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
        messages.error(request, "There was a problem uploading the document.")
    else:
        form = SOPDocumentForm()
    return render(request, 'flightplan/sop_upload.html', {'form': form, 'current_page': 'sop'})


@login_required
def sop_list(request):
    query = request.GET.get('q', '').strip()
    sops = SOPDocument.objects.all()
    if query:
        sops = sops.filter(Q(title__icontains=query) | Q(description__icontains=query))
    sops = sops.order_by('-created_at')

    paginator = Paginator(sops, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'sops': page_obj,
        'page_obj': page_obj,
        'search_query': query,
        'current_page': 'sop',
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
    selected_category = request.GET.get('category', '').strip()

    documents = GeneralDocument.objects.all().order_by('-uploaded_at')
    if search_query:
        documents = documents.filter(title__icontains=search_query)
    if selected_category:
        documents = documents.filter(category=selected_category)

    categories = GeneralDocument.objects.values_list('category', flat=True).distinct()
    paginator = Paginator(documents, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'documents': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': selected_category,
        'search_query': search_query,
        'current_page': 'documents',
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
        messages.error(request, "There was a problem uploading the document.")
    else:
        form = GeneralDocumentForm()
    return render(request, 'flightplan/upload_general.html', {'form': form, 'current_page': 'documents'})


@login_required
def delete_document(request, pk):
    doc = get_object_or_404(GeneralDocument, pk=pk)
    if request.method == 'POST':
        doc.delete()
        messages.success(request, "Document deleted successfully.")
    return redirect('general_document_list')


# -------------------------------------------------
# E Q U I P M E N T
# -------------------------------------------------
@login_required
def equipment_list(request):
    equipment = Equipment.objects.all().order_by('-purchase_date', 'name')

    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipment added.')
            return redirect('equipment_list')
        messages.error(request, 'There was a problem saving the equipment.')
    else:
        form = EquipmentForm()

    context = {'equipment': equipment, 'form': form, 'current_page': 'equipment'}
    return render(request, 'flightplan/equipment_list.html', context)


@login_required
def equipment_create(request):
    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipment added.')
            return redirect('equipment_list')
        # Log form errors for debugging
        print("POST data:", request.POST)
        print("FILES data:", request.FILES)
        print("Form errors:", form.errors)
        messages.error(request, 'There was a problem saving the equipment.')
    else:
        form = EquipmentForm()

    return render(
        request,
        'flightplan/equipment_list.html',
        {'form': form, 'equipment': Equipment.objects.all(), 'current_page': 'equipment'}
    )


@login_required
def equipment_edit(request, pk):
    item = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipment updated.')
            return redirect('equipment_list')
        messages.error(request, 'There was a problem updating the equipment.')
    else:
        form = EquipmentForm(instance=item)

    return render(request, 'flightplan/equipment_edit.html', {'form': form, 'item': item, 'current_page': 'equipment'})


@login_required
def equipment_delete(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        name = equipment.name
        equipment.delete()
        messages.success(request, f'Equipment "{name}" deleted.')
        return redirect('equipment_list')
    return render(request, 'flightplan/equipment_confirm_delete.html', {'equipment': equipment, 'current_page': 'equipment'})


@login_required
def equipment_pdf(request):
    equipment = Equipment.objects.all().order_by('equipment_type', 'name')
    logo_url = request.build_absolute_uri(static('images/logo.png'))
    context = {'equipment': equipment, 'logo_url': logo_url}

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
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(target=tmp_file.name)
        tmp_file.seek(0)
        response.write(tmp_file.read())

    return response


@login_required
def export_equipment_csv(request):
    equipment = Equipment.objects.all()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="equipment.csv"'
    writer = csv.writer(response)

    writer.writerow([
        'Name', 'Type', 'Brand', 'Model', 'Serial Number', 'FAA Number',
        'FAA Certificate URL', 'Purchase Date', 'Purchase Cost', 'Receipt URL',
        'Date Sold', 'Sale Price', 'Deducted Full Cost', 'Active', 'Notes',
    ])

    for e in equipment:
        writer.writerow([
            e.name,
            e.get_equipment_type_display(),
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
            (e.notes or '').replace('\n', ' ').replace('\r', ''),
        ])

    return response


# -------------------------------------------------
# F L I G H T L O G S
# -------------------------------------------------
@login_required
def flightlog_list(request):
    location_filter = request.GET.get('location', '').strip()
    logs_qs = FlightLog.objects.all()

    if location_filter:
        logs_qs = logs_qs.filter(
            Q(takeoff_address__icontains=location_filter) |
            Q(takeoff_latlong__icontains=location_filter)
        )

    logs_qs = logs_qs.order_by('-flight_date')

    paginator = Paginator(logs_qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

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

    fields = [f.name for f in FlightLog._meta.fields]
    writer.writerow(fields)

    for log in FlightLog.objects.all().order_by('-flight_date'):
        writer.writerow([getattr(log, name) for name in fields])

    return response


@login_required
def flightlog_detail(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    context = {'log': log, 'current_page': 'flightlogs'}
    return render(request, 'flightplan/flightlog_detail.html', context)


@login_required
def flightlog_edit(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    # NOTE: Consider a dedicated FlightLogForm for editing instead of the CSV upload form.
    if request.method == 'POST':
        form = FlightLogCSVUploadForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            messages.success(request, 'Flight log updated.')
            return redirect('flightlog_list')
        messages.error(request, 'There was a problem updating the flight log.')
    else:
        form = FlightLogCSVUploadForm(instance=log)

    return render(request, 'flightplan/flightlog_form.html', {'form': form, 'log': log, 'current_page': 'flightlogs'})


@login_required
def flightlog_business(request, pk):
    # If this is intended to toggle business fields only, consider a dedicated form.
    log = get_object_or_404(FlightLog, pk=pk)
    if request.method == 'POST':
        form = FlightLogCSVUploadForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            messages.success(request, 'Flight log updated.')
            return redirect('flightlog_list')
        messages.error(request, 'There was a problem updating the flight log.')
    else:
        form = FlightLogCSVUploadForm(instance=log)

    return render(request, 'flightplan/flightlog_form.html', {'form': form, 'log': log, 'current_page': 'flightlogs'})


@login_required
def flightlog_delete(request, pk):
    log = get_object_or_404(FlightLog, pk=pk)
    if request.method == 'POST':
        title = log.flight_title or f'Log {pk}'
        log.delete()
        messages.success(request, f'{title} deleted.')
        return redirect('flightlog_list')
    return render(request, 'flightplan/flightlog_confirm_delete.html', {'log': log, 'current_page': 'flightlogs'})


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


# -------------------------------------------------
# F L I G H T   L O G   C S V   U P L O A D
# -------------------------------------------------
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
            field_aliases = {"Flight/Service Date": "Flight Date/Time"}

            created = 0
            skipped = 0
            errored = 0

            for raw_row in reader:
                # Normalize column keys & values
                row = {
                    field_aliases.get(k.strip(), k.strip()): (v.strip() if v else "")
                    for k, v in raw_row.items()
                }

                # Require a date/time
                if not row.get("Flight Date/Time"):
                    skipped += 1
                    continue

                # Parse datetime
                try:
                    clean_dt = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', row["Flight Date/Time"])
                    dt = datetime.strptime(clean_dt, "%b %d, %Y %I:%M%p")
                except Exception:
                    skipped += 1
                    continue

                flight_date = dt.date()
                landing_time = dt.time()

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
                        takeoff_battery_pct=safe_pct(row.get("Takeoff Bat %")),
                        takeoff_mah=safe_int(row.get("Takeoff mAh")),
                        takeoff_volts=safe_float(row.get("Takeoff Volts")),
                        landing_battery_pct=safe_pct(row.get("Landing Bat %")),
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
                        cloud_cover=safe_pct(row.get("Cloud Cover")),
                        humidity_pct=safe_pct(row.get("Humidity")),
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
                    created += 1
                except Exception as e:
                    # Keep importing; log the row for review
                    errored += 1
                    print("Row error:", e, raw_row)

            messages.success(request, f"Flight log CSV processed. Created: {created}, Skipped: {skipped}, Errors: {errored}")
            return redirect('flightlog_list')
        else:
            messages.error(request, "Invalid form submission.")
    else:
        form = FlightLogCSVUploadForm()

    # Render upload page on GET or invalid POST
    return render(request, 'flightplan/flightlog_form.html', {'form': form, 'current_page': 'flightlogs'})


# -------------------------------------------------
# M A P S
# -------------------------------------------------
@login_required
def flight_map_view(request):
    logs = FlightLog.objects.all().order_by('-flight_date')[:100]
    locations_qs = (
        FlightLog.objects
        .values('takeoff_latlong', 'takeoff_address')
        .annotate(count=Count('id'))
        .exclude(takeoff_latlong__exact="")
        .order_by('takeoff_address')
    )
    locations = list(locations_qs)

    # Extract unique states/cities
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


# Public embed (no login)
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
