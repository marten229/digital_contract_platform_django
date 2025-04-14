# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contractsapp', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='creator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='created_contracts', to=settings.AUTH_USER_MODEL, verbose_name='Ersteller'),
        ),
        migrations.AlterField(
            model_name='contract',
            name='partner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='partnered_contracts', to=settings.AUTH_USER_MODEL, verbose_name='Partner'),
        ),
    ]
