"""
Encrypt existing plain card numbers and replace the plain card_number column
with card_number_encrypted (Fernet) + card_number_hash (HMAC-SHA256 search token).
"""

from django.db import migrations, models


def _deduplicate_card_phones(apps, schema_editor):
    """Re-run phone deduplication: required because the table is rebuilt
    below (to add the encryption columns) using a schema where `phone`
    is unique, and duplicate phone values can still be present."""
    Card = apps.get_model("cards", "Card")

    rows = list(Card.objects.order_by("id").values_list("id", "phone"))
    normalized = [(row_id, (phone or "").strip()) for row_id, phone in rows]
    existing_non_empty = [phone for _, phone in normalized if phone]
    reserved = set(existing_non_empty)
    kept = set()

    updates = []

    for row_id, phone in normalized:
        if phone and phone not in kept:
            kept.add(phone)
            updates.append((row_id, phone))
            continue

        seed = row_id or 1
        candidate = f"+998{seed:09d}"
        while candidate in reserved:
            seed += 1
            candidate = f"+998{seed:09d}"

        reserved.add(candidate)
        updates.append((row_id, candidate))

    for row_id, phone in updates:
        if phone != dict(rows).get(row_id):
            Card.objects.filter(id=row_id).update(phone=phone)


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
        # 0. Deduplicate phone numbers (table rebuild below requires phone uniqueness).
        migrations.RunPython(_deduplicate_card_phones, migrations.RunPython.noop),
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
