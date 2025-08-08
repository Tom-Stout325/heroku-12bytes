import csv
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from money.models import Miles, Client, Invoice, Event


class Command(BaseCommand):
    help = 'Import mileage logs from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the mileage.csv file')
        parser.add_argument('--user-id', type=int, required=True, help='User ID to assign to each mileage entry')

    def handle(self, *args, **options):
        csv_path = options['csv_file']
        user_id = options['user_id']

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'❌ User with ID {user_id} does not exist.'))
            return

        success = 0
        skipped = 0

        with open(csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    date = datetime.strptime(row['date'], '%m/%d/%y').date()
                    begin = Decimal(row['start'])
                    end = Decimal(row['end'])
                    vehicle = row['vehicle'].strip() or "Lead Foot"
                    mileage_type = row['mileage_type'].strip() or "Taxable"
                    tax = row['deductible'].strip() or "Yes"
                    job = row.get('event', '').strip() or None

                    # Resolve Client
                    client_name = row['client'].strip()
                    client = Client.objects.filter(business__iexact=client_name).first()

                    if not client:
                        self.stderr.write(self.style.WARNING(f"⚠️ Skipped: Client '{client_name}' not found."))
                        skipped += 1
                        continue

                    # Resolve Invoice
                    invoice_number = row['invoice_number'].strip()
                    invoice = Invoice.objects.filter(invoice_number=invoice_number).first()

                    # Create mileage record
                    Miles.objects.create(
                        user=user,
                        date=date,
                        begin=begin,
                        end=end,
                        client=client,
                        invoice=invoice,
                        tax=tax,
                        job=job,
                        vehicle=vehicle,
                        mileage_type=mileage_type
                    )
                    success += 1

                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"❌ Error importing row: {row} — {e}"))
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(f'✅ Imported {success} mileage record(s).'))
        if skipped:
            self.stdout.write(self.style.WARNING(f'⚠️ Skipped {skipped} row(s) due to missing data or errors.'))


# Run Command:
#
# python manage.py import_mileage data/mileage.csv --user-id=1
#