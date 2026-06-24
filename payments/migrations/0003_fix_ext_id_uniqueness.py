from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_add_ext_id_to_payment"),
    ]

    operations = [
        # Drop the unconditional unique constraint that was ignoring NULLs
        migrations.AlterField(
            model_name="payment",
            name="ext_id",
            field=models.CharField(max_length=100, null=True, blank=True, db_index=True),
        ),
        # Add a partial unique index: enforces uniqueness only for non-NULL values
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=["ext_id"],
                condition=models.Q(ext_id__isnull=False),
                name="unique_payment_ext_id_when_not_null",
            ),
        ),
    ]
