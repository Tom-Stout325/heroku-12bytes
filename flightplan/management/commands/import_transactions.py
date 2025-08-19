import csv
from decimal import Decimal
from datetime import datetime

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from money.models import Transaction, Category, SubCategory, Team, Event


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
        warning_count = 0

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

                    category_name = row.get('category', '').strip()
                    sub_category_name = row.get('sub_category', '').strip()
                    team_name = row.get('team', '').strip()
                    event_title = row.get('event', '').strip()
                    invoice_number = row.get('invoice_number', '').strip()
                    transport = row.get('transport', '').strip()

                    category = Category.objects.filter(category__iexact=category_name).first() if category_name else None
                    sub_cat = SubCategory.objects.filter(sub_cat__iexact=sub_category_name).first() if sub_category_name else None
                    team = Team.objects.filter(name__iexact=team_name).first() if team_name else None
                    event = Event.objects.filter(title__iexact=event_title).first() if event_title else None

                    # Warn if invoice_number is provided but no event
                    if invoice_number and not event:
                        warning_count += 1
                        self.stderr.write(
                            f"⚠️ Invoice number '{invoice_number}' provided without an event for transaction '{transaction_name}'"
                        )

                    # Create transaction
                    Transaction.objects.create(
                        user=user,
                        trans_type=trans_type,
                        category=category,
                        sub_cat=sub_cat,
                        amount=amount,
                        transaction=transaction_name,
                        team=team,
                        event=event,
                        invoice_number=invoice_number or None,
                        date=date,
                        transport_type=transport or None
                    )

                    success_count += 1

                except Exception as e:
                    error_count += 1
                    self.stderr.write(self.style.ERROR(
                        f"❌ Error importing transaction '{row.get('transaction', 'N/A')}': {e}"
                    ))

        # Summary
        self.stdout.write(self.style.SUCCESS(f"\n✅ Imported {success_count} transactions."))
        if warning_count:
            self.stdout.write(self.style.WARNING(f"⚠️  {warning_count} transaction(s) had an invoice number without an event."))
        if error_count:
            self.stdout.write(self.style.WARNING(f"❌  {error_count} transaction(s) failed to import."))


# Run command:

# python3 manage.py import_transactions data/transactions.csv --user-id=1
