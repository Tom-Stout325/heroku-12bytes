import csv
from decimal import Decimal
from django.core.management.base import BaseCommand
from money.models import Client, Invoice, Service, Event
from datetime import datetime


class Command(BaseCommand):
    help = 'Import invoices from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']
        success_count = 0
        error_count = 0

        with open(csv_file, newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)

            for row in reader:
                try:
                    invoice_number = row['invoice_number'].strip()
                    client_id = int(row['client_id'].strip())
                    event_id = int(row['event_id'].strip())
                    location = row['location'].strip()
                    service_name = row['service'].strip()
                    amount = float(row['amount'].strip())

                    # Correct date parsing format: MM/DD/YY
                    date = datetime.strptime(row['date'].strip(), '%m/%d/%y')
                    due = datetime.strptime(row['due'].strip(), '%m/%d/%y')
                    paid_date_str = row['paid_date'].strip()
                    paid_date = datetime.strptime(paid_date_str, '%m/%d/%y') if paid_date_str else None

                    status = row['status'].strip()

                    client = Client.objects.get(pk=client_id)
                    event = Event.objects.get(pk=event_id)
                    service = Service.objects.get(service=service_name)

                    Invoice.objects.create(
                        invoice_number=invoice_number,
                        client=client,
                        event=event,
                        location=location,
                        service=service,
                        amount=amount,
                        date=date,
                        due=due,
                        paid_date=paid_date,
                        status=status
                    )

                    success_count += 1
                except Exception as e:
                    error_count += 1
                    self.stderr.write(f"❌ Error importing invoice '{row.get('invoice_number', 'N/A')}': {e}")

        self.stdout.write(self.style.SUCCESS(f"✅ Imported {success_count} invoices."))
        if error_count:
            self.stdout.write(self.style.WARNING(f"⚠️ {error_count} invoice(s) failed to import."))
