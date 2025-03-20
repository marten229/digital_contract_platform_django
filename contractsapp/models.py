from django.db import models

class Contract(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Ausstehend'),
        ('accepted', 'Akzeptiert'),
        ('rejected', 'Abgelehnt'),
        ('completed', 'Abgeschlossen'),
    )
    
    title = models.CharField(max_length=255, verbose_name="Vertragstitel")
    pdf_file = models.FileField(upload_to='contracts/', verbose_name="Vertragsdokument (PDF)")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    creator_address = models.CharField(max_length=42, verbose_name="Ihre Ethereum-Adresse", default=None)
    partner_address = models.CharField(max_length=42, verbose_name="Ethereum-Adresse des Vertragspartners", default=None)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return self.title