"""
Encrypt existing plain card numbers and replace the plain card_number column
with card_number_encrypted (Fernet) + card_number_hash (HMAC-SHA256 search token).
"""

from django.db import migrations, models


def _encrypt_existing(apps, schema_editor):
    """Encrypt every row that still holds a plain card number."""
    from config.security import encrypt_card, decrypt_card, _search_token

    Card = apps.get_model("cards", "Card")
    for card in Card.objects.all():
        raw = card.card_number  # old plain-text DB column (still present at this point)
        if not raw:
            continue
        # If the value was already encrypted by an earlier partial run, decrypt it first.
        try:
            plain = decrypt_card(raw)
        except Exception:
            plain = raw  # it's plaintext — use as-is
        card.card_number_encrypted = encrypt_card(plain)
        card.card_number_hash = _search_token(plain)
        card.save(update_fields=["card_number_encrypted", "card_number_hash"])


def _decrypt_existing(apps, schema_editor):
    """Reverse: restore plain card numbers from encrypted values (for rollback)."""
    from config.security import decrypt_card

    Card = apps.get_model("cards", "Card")
    for card in Card.objects.all():
        if card.card_number_encrypted:
            try:
                card.card_number = decrypt_card(card.card_number_encrypted)
                card.save(update_fields=["card_number"])
            except Exception:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0004_card_tg_id_alter_card_phone"),
    ]

    operations = [
        # 1. Add the two new columns (no unique constraint yet — set after population).
        migrations.AddField(
            model_name="card",
            name="card_number_encrypted",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="card",
            name="card_number_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        # 2. Encrypt all existing rows.
        migrations.RunPython(_encrypt_existing, reverse_code=_decrypt_existing),
        # 3. Remove the old plaintext column and apply the unique constraint.
        migrations.RemoveField(
            model_name="card",
            name="card_number",
        ),
        migrations.AlterField(
            model_name="card",
            name="card_number_hash",
            field=models.CharField(
                blank=True, db_index=True, default="", max_length=64, unique=True
            ),
        ),
    ]
