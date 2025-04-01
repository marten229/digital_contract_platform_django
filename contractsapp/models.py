from django.db import models
import os
from django.conf import settings
from .storage import ContractStorage
from django.utils import timezone

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
        ('draft', 'Entwurf'),
        ('uploaded', 'Hochgeladen'),
        ('configured', 'Konfiguriert'),
        ('invitation_sent', 'Einladung gesendet'),
        ('viewed_by_partner', 'Vom Partner angesehen'),
        ('partner_verified', 'Partner verifiziert'),
        ('signed_by_creator', 'Vom Ersteller unterschrieben'),
        ('signed_by_partner', 'Vom Partner unterschrieben'),
        ('completed', 'Vollständig unterschrieben'),
        ('rejected', 'Abgelehnt'),
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
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    last_updated = models.DateTimeField(auto_now=True)
    
    # New blockchain-related fields
    blockchain_contract_id = models.BigIntegerField(null=True, blank=True, verbose_name="Blockchain-Vertrags-ID")
    pdf_hash = models.CharField(max_length=66, null=True, blank=True, verbose_name="PDF-Hash")
    blockchain_status = models.CharField(max_length=20, null=True, blank=True, verbose_name="Blockchain-Status")
    contract_amount = models.BigIntegerField(null=True, blank=True, verbose_name="Vertragsbetrag (Wei)")
    transaction_hash = models.CharField(max_length=66, null=True, blank=True, verbose_name="Transaktions-Hash")

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
                        
                        # If the PDF file has changed, recalculate its hash
                        if hasattr(self.pdf_file, 'file') and hasattr(self.pdf_file.file, 'read'):
                            # Import here to avoid circular imports
                            from .blockchain import BlockchainService
                            blockchain_service = BlockchainService()
                            self.pdf_hash = blockchain_service.calculate_pdf_hash(self.pdf_file)
                        
                        # Speichern ohne rekursiven Aufruf der save-Methode
                        super().save(update_fields=['pdf_file', 'pdf_hash'])
                    
                    # Protokollieren für Debugging
                    print(f"Vertrag {self.pk} gespeichert: {self.pdf_file.name}")
            except Exception as e:
                # Fehler protokollieren
                import traceback
                print(f"Fehler beim Speichern des Vertrags {self.pk}: {e}")
                print(traceback.format_exc())
                
    def get_status_display_german(self):
        """Gibt eine benutzerfreundliche deutsche Beschreibung des aktuellen Status zurück"""
        status_map = dict(self.STATUS_CHOICES)
        return status_map.get(self.status, self.status)
    
    def get_status_class(self):
        """Gibt eine CSS-Klasse basierend auf dem Status zurück"""
        status_classes = {
            'draft': 'status-draft',
            'uploaded': 'status-uploaded',
            'configured': 'status-configured',
            'invitation_sent': 'status-invitation',
            'viewed_by_partner': 'status-viewed',
            'partner_verified': 'status-verified',
            'signed_by_creator': 'status-signed-creator',
            'signed_by_partner': 'status-signed-partner',
            'completed': 'status-completed',
            'rejected': 'status-rejected',
        }
        return status_classes.get(self.status, 'status-default')
        
    def update_blockchain_status(self):
        """Updates the blockchain status for this contract"""
        if self.blockchain_contract_id:
            try:
                from .blockchain import BlockchainService
                blockchain_service = BlockchainService()
                
                # Get the current status from the blockchain
                self.blockchain_status = blockchain_service.get_contract_status(self.blockchain_contract_id)
                self.save(update_fields=['blockchain_status'])
                return True
            except Exception as e:
                print(f"Error updating blockchain status: {e}")
                return False
        return False


class ContractActivity(models.Model):
    """Modell für die Protokollierung aller Aktivitäten an einem Vertrag"""
    
    ACTION_CHOICES = (
        ('create', 'Vertrag erstellt'),
        ('upload', 'Vertrag hochgeladen'),
        ('configure', 'Vertrag konfiguriert'),
        ('send_invitation', 'Einladung gesendet'),
        ('view', 'Vertrag angesehen'),
        ('verify_partner', 'Partner verifiziert'),
        ('sign_creator', 'Vom Ersteller unterschrieben'),
        ('sign_partner', 'Vom Partner unterschrieben'),
        ('complete', 'Vertrag abgeschlossen'),
        ('reject', 'Vertrag abgelehnt'),
        ('status_change', 'Status geändert'),
        ('other', 'Sonstige Aktivität'),
    )
    
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='activities')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)
    user_address = models.CharField(max_length=42, null=True, blank=True, 
                                   help_text="Ethereum-Adresse des Benutzers, der die Aktion ausgeführt hat")
    user_role = models.CharField(max_length=10, choices=(
        ('creator', 'Ersteller'),
        ('partner', 'Partner'),
        ('system', 'System'),
    ), default='system')
    details = models.TextField(blank=True, null=True, 
                              help_text="Zusätzliche Details zur Aktivität")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Vertragsaktivität"
        verbose_name_plural = "Vertragsaktivitäten"
    
    def __str__(self):
        return f"{self.get_action_display()} - {self.contract.title} ({self.timestamp.strftime('%d.%m.%Y %H:%M')})"
        
    @classmethod
    def log(cls, contract, action, user=None, user_role='system', details=None):
        """Hilfsmethode zum einfachen Protokollieren einer Vertragsaktivität"""
        user_address = None
        if user and hasattr(user, 'ethereum_address'):
            user_address = user.ethereum_address
            if user_role == 'system' and contract.creator_address == user_address:
                user_role = 'creator'
            elif user_role == 'system' and contract.partner_address == user_address:
                user_role = 'partner'
                
        return cls.objects.create(
            contract=contract,
            action=action,
            user_address=user_address,
            user_role=user_role,
            details=details
        )