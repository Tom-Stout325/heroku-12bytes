import csv
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date
from money.models import Transaction, Category, SubCategory, Team, Invoice, Event
from django.contrib.auth.models import User
from datetime import datetime


class Command(BaseCommand):
    help = 'Import transactions from CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)
        parser.add_argument('--user-id', type=int, required=True, help='User ID to assign to transactions')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        user_id = options['user_id']
        success_count = 0
        error_count = 0

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"❌ User with ID {user_id} does not exist."))
            return

        with open(csv_file, newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)

            for row in reader:
                try:
                    date = datetime.strptime(row['date'].strip(), '%m/%d/%y').date()
                    trans_type = row['type'].strip()
                    amount = Decimal(row['amount'].strip())
                    transaction_name = row['transaction'].strip()

                    category_name = row['category'].strip()
                    sub_category_name = row['sub_category'].strip()
                    team_name = row['team'].strip()
                    event_title = row['event'].strip()
                    invoice_number = row['invoice_number'].strip()
                    transport = row['transport'].strip()

                    category = Category.objects.get(category__iexact=category_name) if category_name else None
                    sub_cat = SubCategory.objects.get(sub_cat__iexact=sub_category_name) if sub_category_name else None
                    team = Team.objects.get(name__iexact=team_name) if team_name else None
                    event = Event.objects.filter(title__iexact=event_title).order_by('-event_year').first() if event_title else None
                    invoice = Invoice.objects.get(invoice_number=invoice_number) if invoice_number else None

                    transaction = Transaction.objects.create(
                        user=user,
                        trans_type=trans_type,
                        category=category,
                        sub_cat=sub_cat,
                        amount=amount,
                        transaction=transaction_name,
                        team=team,
                        event=event,
                        date=date,
                        invoice=invoice,
                        transport_type=transport or None
                    )

                    success_count += 1
                except Exception as e:
                    error_count += 1
                    self.stderr.write(f"❌ Error importing transaction '{row.get('transaction', 'N/A')}': {e}")

        self.stdout.write(self.style.SUCCESS(f"✅ Imported {success_count} transactions."))
        if error_count:
            self.stdout.write(self.style.WARNING(f"⚠️ {error_count} transaction(s) failed to import."))
