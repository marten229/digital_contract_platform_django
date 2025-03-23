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
    
    # New fields for partner information
    partner_name = models.CharField(max_length=100, verbose_name="Name des Vertragspartners", default=None)
    partner_email = models.EmailField(verbose_name="E-Mail des Vertragspartners", default=None)
    
    # Make partner address optional - will be added when partner accepts the contract
    partner_address = models.CharField(max_length=42, verbose_name="Ethereum-Adresse des Vertragspartners", 
                                      blank=True, null=True, default=None)
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return self.title