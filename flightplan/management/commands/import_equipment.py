import csv
import os
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import urlopen

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from flightplan.models import Equipment


def norm_str(v):
    return (v or "").strip()

def parse_bool(v):
    s = norm_str(v).lower()
    if s in {"yes", "y", "true", "t", "1"}:
        return True
    if s in {"no", "n", "false", "f", "0"}:
        return False
    return None

def parse_decimal(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        # remove common formatting like commas or $ signs
        s = re.sub(r"[^0-9\.\-]", "", str(v))
        return Decimal(s) if s not in {"", "-", "."} else None
    except (InvalidOperation, ValueError):
        return None

def parse_date(v):
    s = norm_str(v)
    if not s:
        return None
    # try a few common formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # last resort: ISO-ish
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None

def safe_filename_from_url(url, fallback):
    try:
        path = urlparse(url).path
        name = os.path.basename(path)
        return name or fallback
    except Exception:
        return fallback

# Map CSV Type -> model choices (internal values)
# Your model: ('Drone','Controller','Battery','Charger','Accessory','Other')
TYPE_MAP = {
    "drone": "Drone",
    "controller": "Controller",
    "battery": "Battery",
    "charger": "Charger",
    "accessory": "Accessory",
    "other": "Other",
}

def normalize_type(v):
    s = norm_str(v).lower()
    return TYPE_MAP.get(s) or "Other"


class Command(BaseCommand):
    help = "Import Equipment from CSV"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to CSV file")
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing equipment matched by Serial Number (if present)",
        )
        parser.add_argument(
            "--download-files",
            action="store_true",
            help="Download FAA Certificate URL and Receipt URL to FileFields",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate, but do not write to the database",
        )

    def handle(self, *args, **opts):
        csv_path = opts["csv_file"]
        update_existing = opts["update_existing"]
        download_files = opts["download_files"]
        dry_run = opts["dry_run"]

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV not found: {csv_path}")

        required_headers = [
            "Name","Type","Brand","Model","Serial Number","FAA Number",
            "FAA Certificate URL","Purchase Date","Purchase Cost","Receipt URL",
            "Date Sold","Sale Price","Deducted Full Cost","Active","Notes",
        ]

        created = updated = skipped = errored = 0

        # Use a transaction so a failure doesn't half-write (unless dry-run)
        ctx = transaction.atomic() if not dry_run else nullcontext()
        with ctx:
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                # Normalize headers: strip BOM, spaces
                reader.fieldnames = [h.strip().replace("\ufeff", "") for h in reader.fieldnames]

                # Basic header check
                missing = [h for h in required_headers if h not in reader.fieldnames]
                if missing:
                    raise CommandError(f"Missing headers: {', '.join(missing)}")

                for idx, row in enumerate(reader, start=2):  # start=2 to account for header row
                    try:
                        name = norm_str(row.get("Name"))
                        if not name:
                            skipped += 1
                            continue

                        equipment_type = normalize_type(row.get("Type"))
                        brand = norm_str(row.get("Brand"))
                        model = norm_str(row.get("Model"))
                        serial_number = norm_str(row.get("Serial Number"))
                        faa_number = norm_str(row.get("FAA Number"))
                        purchase_date = parse_date(row.get("Purchase Date"))
                        purchase_cost = parse_decimal(row.get("Purchase Cost"))
                        date_sold = parse_date(row.get("Date Sold"))
                        sale_price = parse_decimal(row.get("Sale Price"))
                        deducted_full_cost = parse_bool(row.get("Deducted Full Cost")) or False
                        active = parse_bool(row.get("Active"))
                        if active is None:
                            # Default to True if omitted
                            active = True
                        notes = norm_str(row.get("Notes"))

                        faa_url = norm_str(row.get("FAA Certificate URL"))
                        receipt_url = norm_str(row.get("Receipt URL"))

                        obj = None
                        created_now = False

                        if update_existing and serial_number:
                            obj = Equipment.objects.filter(serial_number=serial_number).first()

                        if obj is None:
                            obj = Equipment(
                                name=name,
                                equipment_type=equipment_type,
                                brand=brand,
                                model=model,
                                serial_number=serial_number,
                                faa_number=faa_number,
                                purchase_date=purchase_date,
                                purchase_cost=purchase_cost,
                                date_sold=date_sold,
                                sale_price=sale_price,
                                deducted_full_cost=deducted_full_cost,
                                active=active,
                                notes=notes,
                            )
                            created_now = True
                        else:
                            obj.name = name
                            obj.equipment_type = equipment_type
                            obj.brand = brand
                            obj.model = model
                            obj.serial_number = serial_number
                            obj.faa_number = faa_number
                            obj.purchase_date = purchase_date
                            obj.purchase_cost = purchase_cost
                            obj.date_sold = date_sold
                            obj.sale_price = sale_price
                            obj.deducted_full_cost = deducted_full_cost
                            obj.active = active
                            obj.notes = notes

                        # Save now to get a PK for file saving
                        if not dry_run:
                            obj.save()

                        # Optionally download file URLs into FileFields
                        if download_files and not dry_run:
                            # FAA certificate
                            if faa_url:
                                try:
                                    with urlopen(faa_url, timeout=15) as resp:
                                        data = resp.read()
                                    fname = safe_filename_from_url(faa_url, f"faa_{obj.pk}")
                                    obj.faa_certificate.save(fname, ContentFile(data), save=True)
                                except Exception as e:
                                    self.stderr.write(f"[row {idx}] FAA download failed: {e}")

                            # Receipt
                            if receipt_url:
                                try:
                                    with urlopen(receipt_url, timeout=15) as resp:
                                        data = resp.read()
                                    fname = safe_filename_from_url(receipt_url, f"receipt_{obj.pk}")
                                    obj.receipt.save(fname, ContentFile(data), save=True)
                                except Exception as e:
                                    self.stderr.write(f"[row {idx}] Receipt download failed: {e}")

                        if created_now:
                            created += 1
                        else:
                            updated += 1 if update_existing else 0
                            if not update_existing:
                                # No update; we created a new one anyway
                                pass

                    except Exception as e:
                        errored += 1
                        self.stderr.write(f"[row {idx}] Error: {e}")

            if dry_run:
                # Force rollback by raising a controlled exception after parsing
                self.stdout.write("Dry run complete — no changes written.")

        self.stdout.write(f"✅ Created: {created}")
        if update_existing:
            self.stdout.write(f"🛠️  Updated: {updated}")
        self.stdout.write(f"⏭️  Skipped: {skipped}")
        self.stdout.write(f"❌ Errors: {errored}")


# Python <3.10 compatibility for context manager
class nullcontext:
    def __enter__(self): return None
    def __exit__(self, *args): return False
