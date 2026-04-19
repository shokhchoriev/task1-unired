import os
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from .models import Card
from .services import import_cards_from_excel
from .utils import format_card, format_expire, format_phone, parse_balance, prepare_message


class UtilsTests(TestCase):
    def test_format_helpers(self):
        self.assertEqual(format_card("8600 1234 5678 9012"), "8600123456789012")
        self.assertEqual(format_phone("99 973 03 03"), "+998999730303")
        self.assertEqual(format_phone("973-03-03"), "+998999730303")
        self.assertEqual(format_expire("12/24"), "2024-12")
        self.assertEqual(format_expire("2026-08"), "2026-08")
        self.assertEqual(str(parse_balance("842,714,800.00")), "842714800.00")

    def test_prepare_message(self):
        message = prepare_message("8600123456789012", "5000")
        self.assertIn("8600 1234 5678 9012", message)
        self.assertIn("5,000.00 UZS", message)


class ImportServiceTests(TestCase):
    def test_import_cards_from_csv(self):
        csv_data = "\n".join(
            [
                "card_number,expire,phone,status,balance",
                "8600 1234 5678 9012,12/24,99 973 03 03,inactive,5000.00",
                "123,12/24,99 973 03 03,inactive,5000.00",
            ]
        )
        upload = SimpleUploadedFile("cards.csv", csv_data.encode("utf-8"))
        success, errors = import_cards_from_excel(upload)

        self.assertEqual(success, 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(Card.objects.count(), 1)


class CommandsTests(TestCase):
    def setUp(self):
        Card.objects.create(
            card_number="8600123456789012",
            expire="2024-12",
            phone="+998999730303",
            status="active",
            balance="5000.00",
        )

    def test_export_cards_command(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            output_path = tmp.name

        try:
            call_command("export_cards", "--status", "active", "--output", output_path)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read()
            self.assertIn("8600 1234 5678 9012", content)
        finally:
            os.remove(output_path)
