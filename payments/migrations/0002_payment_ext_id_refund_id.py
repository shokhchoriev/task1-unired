"""
Combined migration merging shokh + izzatilla work:
  - ext_id: CharField(null=True, blank=True, max_length=100), unique only when non-NULL
             (izzatilla's approach — allows any external ID format, avoids NULL-unique issues)
  - refund_id: CharField for storing Stripe refund IDs (shokh)
  - status: adds REFUNDED choice (shokh)

Two-step ext_id rollout (null first, backfill, then constrain) is safe for existing rows.
"""

import uuid

from django.db import migrations, models


def populate_ext_ids(apps, schema_editor):
    """Generate unique ext_ids for any pre-existing Payment rows."""
    Payment = apps.get_model("payments", "Payment")
    for payment in Payment.objects.filter(ext_id__isnull=True):
        payment.ext_id = str(uuid.uuid4())
        payment.save(update_fields=["ext_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        # ── ext_id ────────────────────────────────────────────────────────────
        # Step 1: add as nullable so existing rows don't need a value yet.
        migrations.AddField(
            model_name="payment",
            name="ext_id",
            field=models.CharField(max_length=100, null=True, blank=True, db_index=True),
        ),
        # Step 2: backfill existing rows with UUIDs.
        migrations.RunPython(populate_ext_ids, migrations.RunPython.noop),
        # Step 3: add partial unique constraint (enforced only for non-NULL values).
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=["ext_id"],
                condition=models.Q(ext_id__isnull=False),
                name="unique_payment_ext_id_when_not_null",
            ),
        ),
        # ── refund_id ─────────────────────────────────────────────────────────
        migrations.AddField(
            model_name="payment",
            name="refund_id",
            field=models.CharField(blank=True, max_length=200),
        ),
        # ── status: add REFUNDED choice ───────────────────────────────────────
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("success", "Success"),
                    ("failed", "Failed"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="pending",
                max_length=10,
            ),
        ),
    ]
