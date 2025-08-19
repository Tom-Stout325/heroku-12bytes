import csv
from django.core.management.base import BaseCommand
from money.models import Category

class Command(BaseCommand):
    help = 'Import categories from CSV with Schedule C line numbers'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        created = 0
        skipped = 0

        with open(csv_file, newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)

            for row in reader:
                category_name = row['category'].strip()
                sched_c = row['schedule_c_line'].strip() if row.get('schedule_c_line') else ''

                category, created_flag = Category.objects.get_or_create(
                    category=category_name,
                    defaults={'schedule_c_line': sched_c or None}
                )

                if created_flag:
                    self.stdout.write(f"✅ Created: {category}")
                    created += 1
                else:
                    self.stdout.write(f"⚠️ Skipped (already exists): {category}")
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(f"\n✅ Done: {created} created, {skipped} skipped."))
