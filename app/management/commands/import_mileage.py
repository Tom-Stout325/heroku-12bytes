import csv
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from money.models import Miles, Client, Invoice


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

        success_count = 0
        skipped_count = 0

        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    date = datetime.strptime(row['date'], '%m/%d/%y').date()
                    begin = Decimal(row['start'])
                    end = Decimal(row['end'])

                    client_name = row.get('client', '').strip()
                    client = Client.objects.filter(business__iexact=client_name).first()
                    if not client:
                        self.stderr.write(f"⚠️ Skipped: Client '{client_name}' not found.")
                        skipped_count += 1
                        continue

                    invoice_number = row.get('invoice_number', '').strip()
                    invoice = Invoice.objects.filter(invoice_number=invoice_number).first() if invoice_number else None

                    deductible = row.get('deductible', 'Yes').strip() or 'Yes'
                    event = row.get('event', '').strip() or None
                    vehicle = row.get('vehicle', 'Lead Foot').strip() or 'Lead Foot'
                    mileage_type = row.get('mileage_type', 'Taxable').strip() or 'Taxable'

                    Miles.objects.create(
                        user=user,
                        date=date,
                        begin=begin,
                        end=end,
                        client=client,
                        invoice=invoice,
                        tax=deductible,
                        job=event,
                        vehicle=vehicle,
                        mileage_type=mileage_type,
                    )

                    success_count += 1

                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"❌ Error importing row: {row} — {e}"))
                    skipped_count += 1

        self.stdout.write(self.style.SUCCESS(f"\n✅ Imported {success_count} mileage record(s)."))
        if skipped_count:
            self.stdout.write(self.style.WARNING(f"⚠️ Skipped {skipped_count} row(s) due to errors or missing data."))
