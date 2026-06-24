import uuid

from django.db import migrations, models


def populate_ext_ids(apps, schema_editor):
    """Generate unique ext_id values for any pre-existing Payment rows."""
    Payment = apps.get_model("payments", "Payment")
    for payment in Payment.objects.filter(ext_id__isnull=True):
        payment.ext_id = uuid.uuid4()
        payment.save(update_fields=["ext_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        # 1. Add column as nullable so existing rows don't need a value yet.
        migrations.AddField(
            model_name="payment",
            name="ext_id",
            field=models.UUIDField(null=True, blank=True),
        ),
        # 2. Backfill existing rows with unique UUIDs.
        migrations.RunPython(populate_ext_ids, migrations.RunPython.noop),
        # 3. Now enforce uniqueness + non-nullable + index.
        migrations.AlterField(
            model_name="payment",
            name="ext_id",
            field=models.UUIDField(default=uuid.uuid4, unique=True, db_index=True),
        ),
        # 4. Add refund tracking field.
        migrations.AddField(
            model_name="payment",
            name="refund_id",
            field=models.CharField(blank=True, max_length=200),
        ),
        # 5. Extend status choices with REFUNDED.
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
