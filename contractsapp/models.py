from django.db import models
import os
from django.conf import settings
from .storage import ContractStorage

def contract_pdf_file_path(instance, filename):
    # Dateiendung (.pdf) vom Dateinamen extrahieren
    ext = filename.split('.')[-1]
    
    # Wenn das Objekt bereits eine ID hat (bei Updates), verwende diese
    if instance.pk:
        return f'contracts/contract_{instance.pk}.{ext}'
    
    # Bei der ersten Erstellung müssen wir die ID nach dem Speichern setzen
    # Verwenden wir einen temporären Namen, der später aktualisiert wird
    return f'contracts/temp_{filename}'

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
    
    # Fields for signature positions
    creator_signature_x = models.FloatField(null=True, blank=True)
    creator_signature_y = models.FloatField(null=True, blank=True)
    creator_signature_width = models.FloatField(null=True, blank=True)
    creator_signature_height = models.FloatField(null=True, blank=True)
    creator_signature_page = models.IntegerField(null=True, blank=True)
    
    partner_signature_x = models.FloatField(null=True, blank=True)
    partner_signature_y = models.FloatField(null=True, blank=True)
    partner_signature_width = models.FloatField(null=True, blank=True)
    partner_signature_height = models.FloatField(null=True, blank=True)
    partner_signature_page = models.IntegerField(null=True, blank=True)
    
    # Flag to track if the contract is in configuration state (uploaded but not yet finalized)
    is_configured = models.BooleanField(default=False)
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return self.title
        
    def save(self, *args, **kwargs):
        # Erst speichern wir das Objekt, um die ID zu bekommen, falls es neu ist
        is_new = self.pk is None
        
        # Speichern ohne Dateibehandlung, um eine ID zu erhalten
        super().save(*args, **kwargs)
        
        # Nach dem Speichern, wenn ein PDF vorhanden ist, mit der richtigen ID speichern
        if self.pdf_file:
            try:
                # Nur bei neuen Objekten oder wenn die PDF-Datei verändert wurde
                if is_new or 'pdf_file' in kwargs.get('update_fields', []):
                    # Die ContractStorage-Klasse instanziieren
                    contract_storage = ContractStorage()
                    
                    # Die Datei mit ContractStorage speichern
                    # Bei einer neuen Datei lesen wir die Datei aus der Feldquelle
                    if hasattr(self.pdf_file, 'file') and hasattr(self.pdf_file.file, 'read'):
                        # Position am Dateianfang sicherstellen
                        self.pdf_file.file.seek(0)
                        
                        # Datei mit der Vertrags-ID speichern
                        file_path = contract_storage.save_contract_file(
                            self.pk, 
                            self.pdf_file, 
                            is_signed='signed' in self.pdf_file.name
                        )
                        
                        # PDF-Dateinamen im Modell aktualisieren
                        self.pdf_file.name = file_path
                        
                        # Speichern ohne rekursiven Aufruf der save-Methode
                        super().save(update_fields=['pdf_file'])
                    
                    # Protokollieren für Debugging
                    print(f"Vertrag {self.pk} gespeichert: {self.pdf_file.name}")
            except Exception as e:
                # Fehler protokollieren
                import traceback
                print(f"Fehler beim Speichern des Vertrags {self.pk}: {e}")
                print(traceback.format_exc())