import csv
from django.core.management.base import BaseCommand
from money.models import Event
from django.utils.text import slugify


class Command(BaseCommand):
    help = 'Import events from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **options):
        file_path = options['csv_file']

        with open(file_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            count = 0
            for row in reader:
                title = row['title'].strip()
                event_type = row['event_type'].strip() or 'race'
                location_city = row.get('location_city', '').strip()
                location_address = row.get('location_address', '').strip()
                airspace = row.get('airspace', '').strip()
                waiver_approved = row.get('waiver_approved', 'False').strip().lower() == 'true'
                notes = row.get('notes', '').strip()

                event, created = Event.objects.get_or_create(
                    title=title,
                    defaults={
                        'event_type': event_type,
                        'location_city': location_city,
                        'location_address': location_address,
                        'airspace': airspace,
                        'waiver_approved': waiver_approved,
                        'notes': notes,
                    }
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(f"✅ Created event: {event}"))
                    count += 1
                else:
                    self.stdout.write(f"⚠️ Skipped existing event: {event}")

            self.stdout.write(self.style.SUCCESS(f"✅ Successfully imported {count} events."))


# Run Command
# python manage.py import_events data/event.csv
#