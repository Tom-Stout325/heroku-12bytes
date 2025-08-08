import csv
from django.core.management.base import BaseCommand
from money.models import SubCategory, Category
from django.utils.text import slugify

class Command(BaseCommand):
    help = 'Import subcategories from CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)

    def handle(self, *args, **options):
        csv_file = options['csv_file']

        with open(csv_file, newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            created, skipped = 0, 0

            for row in reader:
                sub_cat_name = row['sub_cat'].strip()
                category_name = row['category'].strip()

                # Get or create the related Category
                try:
                    category = Category.objects.get(category=category_name)
                except Category.DoesNotExist:
                    self.stderr.write(f"❌ Category '{category_name}' not found. Skipping '{sub_cat_name}'...")
                    skipped += 1
                    continue

                # Create the SubCategory
                subcategory, created_flag = SubCategory.objects.get_or_create(
                    sub_cat=sub_cat_name,
                    category=category,
                    defaults={'slug': slugify(sub_cat_name)}
                )

                if created_flag:
                    self.stdout.write(f"✅ Created: {subcategory}")
                    created += 1
                else:
                    self.stdout.write(f"⚠️ Skipped (already exists): {subcategory}")
                    skipped += 1

            self.stdout.write(self.style.SUCCESS(f"\n✅ Done: {created} created, {skipped} skipped."))



# Run Command:
# python3 manage.py import_subcategories data/subcategories.csv
#