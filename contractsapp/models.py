from django.db import models
import os
from django.conf import settings
from .storage import ContractStorage
from django.utils import timezone
from web3 import Web3
from django.contrib.auth import get_user_model
import json

User = get_user_model()

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
        ('blockchain_published', 'Auf Blockchain veröffentlicht'),
        ('package_shipped', 'Paket versendet'),
        ('package_delivered', 'Paket geliefert'),
        ('delivery_confirmed', 'Lieferung bestätigt'),
        ('delivery_approved', 'Lieferung genehmigt'),
        ('agreement_fulfilled', 'Vereinbarung erfüllt'),
        ('rejected', 'Abgelehnt'),
    )
    title = models.CharField(max_length=255, verbose_name="Vertragstitel")
    pdf_file = models.FileField(upload_to='contracts/', verbose_name="Vertragsdokument (PDF)")
    uploaded_at = models.DateTimeField(auto_now_add=True)
      # Beziehungen zu registrierten Benutzern (optional für die Migration)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_contracts', verbose_name="Ersteller", null=True, blank=True)
    partner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='partnered_contracts', verbose_name="Partner", null=True, blank=True)
    
    # Die primären Felder für Ethereum-Adressen
    creator_address = models.CharField(max_length=42, verbose_name="Ethereum-Adresse des Erstellers", default=None)
    partner_address = models.CharField(max_length=42, verbose_name="Ethereum-Adresse des Partners", 
                                      blank=False, null=False, default=None)
    
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
    funds_withdrawn = models.BooleanField(default=False, verbose_name="Gelder wurden abgehoben")
    
    # DHL tracking fields
    has_dhl_tracking = models.BooleanField(default=False, verbose_name="DHL Tracking aktivieren")
    tracking_number = models.CharField(max_length=50, null=True, blank=True, verbose_name="DHL Tracking-Nummer")
    package_status = models.CharField(max_length=50, null=True, blank=True, verbose_name="Paketstatus")
    last_tracking_update = models.DateTimeField(null=True, blank=True, verbose_name="Letzte Tracking-Aktualisierung")
    delivery_confirmation = models.BooleanField(default=False, verbose_name="Lieferung bestätigt")
    delivery_notes = models.TextField(null=True, blank=True, verbose_name="Lieferhinweise")
    # Neues Feld für die Oracle-Bestätigung
    delivery_oracle_confirmed = models.BooleanField(default=False, verbose_name="Von Oracle bestätigt")    # Speichert den Tracking-Hash für die Blockchain-Verifikation
    tracking_hash = models.CharField(max_length=70, null=True, blank=True, verbose_name="Tracking-Hash")
    
    def __str__(self):
        return self.title
    @property
    def partner_name(self):
        """Returns a display name for the partner - either username if partner object exists, 
        or truncated ethereum address"""
        if self.partner and hasattr(self.partner, 'username'):
            return self.partner.username
        elif self.partner_address:
            return f"{self.partner_address[:6]}...{self.partner_address[-4:]}"
        return "Unbekannt"
    
    def save(self, *args, **kwargs):
        # Stelle sicher, dass Ethereum-Adressen von den Benutzerkonten übernommen werden
        if self.creator and self.creator.ethereum_address:
            self.creator_address = self.creator.ethereum_address.lower()
            
        if self.partner and self.partner.ethereum_address:
            self.partner_address = self.partner.ethereum_address.lower()
            
        # Erst speichern wir das Objekt, um die ID zu bekommen, falls es neu ist
        is_new = self.pk is None
        
        # Temporär speichern und dann wiederherstellen der creator/partner-Beziehungen
        temp_creator = self.creator
        temp_partner = self.partner
        
        # Setze die Felder auf None, damit Django nicht versucht, sie in die Datenbank zu schreiben
        self.creator = None
        self.partner = None
        
        # Speichern ohne Dateibehandlung, um eine ID zu erhalten
        super().save(*args, **kwargs)
        
        # Beziehungen wiederherstellen für weitere Code-Verwendung (aber nicht in DB)
        self.creator = temp_creator
        self.partner = temp_partner
        
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
            except Exception as e:                # Fehler protokollieren
                import traceback
                print(f"Fehler beim Speichern des Vertrags {self.pk}: {e}")
                print(traceback.format_exc())

    def get_status_display_german(self):
        """Gibt eine benutzerfreundliche deutsche Beschreibung des aktuellen Status zurück"""
        status_map = dict(self.STATUS_CHOICES)
        result = status_map.get(self.status, self.status)
        return result

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
            'blockchain_published': 'status-blockchain',
            'package_shipped': 'status-package-shipped',
            'package_delivered': 'status-package-delivered',
            'delivery_confirmed': 'status-delivery-confirmed',
            'delivery_approved': 'status-delivery-approved',
            'agreement_fulfilled': 'status-agreement-fulfilled',
            'rejected': 'status-rejected',
        }
        result = status_classes.get(self.status, 'status-default')
        return result
        
    def update_blockchain_status(self):
        """Updates the blockchain status and delivery information for this contract"""
        if self.blockchain_contract_id:
            try:
                from .blockchain import BlockchainService
                blockchain_service = BlockchainService()
                
                # Get the current status from the blockchain
                old_blockchain_status = self.blockchain_status
                self.blockchain_status = blockchain_service.get_contract_status(self.blockchain_contract_id)                  # Check if Oracle has confirmed delivery on the blockchain based on status
                try:
                    # Get complete contract details including delivery status
                    contract_details = blockchain_service.get_contract_details_extended(self.blockchain_contract_id)
                    
                    # Check if status indicates Oracle has confirmed delivery (DeliveryConfirmed or higher)
                    blockchain_status = contract_details.get('status', '')
                    delivery_confirmed_by_oracle = blockchain_status in ['DeliveryConfirmed', 'DeliveryApproved', 'Completed']
                    
                    if delivery_confirmed_by_oracle and not self.delivery_oracle_confirmed:
                        self.delivery_oracle_confirmed = True
                        if self.status != 'package_delivered':
                            self.status = 'package_delivered'
                        self.package_status = 'delivered'
                        self.last_tracking_update = timezone.now()
                        
                        # Safely handle tracking hash with length validation
                        tracking_hash_value = contract_details.get('deliveryTrackingHash', None)
                        if tracking_hash_value:
                            # Ensure the tracking hash doesn't exceed the field limit
                            if len(str(tracking_hash_value)) <= 70:
                                self.tracking_hash = tracking_hash_value
                            else:
                                print(f"Warning: Tracking hash too long ({len(str(tracking_hash_value))} chars): {tracking_hash_value}")
                                self.tracking_hash = None
                        else:
                            self.tracking_hash = None
                        ContractActivity.log(
                            contract=self,
                            action='status_change',
                            user_role='system',
                            details=f"Lieferung wurde vom Oracle auf der Blockchain bestätigt"
                        )
                        
                except Exception as oracle_e:
                    # Oracle check might fail if contract doesn't exist or network issues
                    print(f"Oracle check failed for contract {self.blockchain_contract_id}: {oracle_e}")
                  # Update general contract status based on blockchain status
                if self.blockchain_status in ['Created', 'Signed', 'DeliverySet', 'DeliveryConfirmed', 'DeliveryApproved', 'AgreementFulfilled', 'Completed'] and self.status != 'blockchain_published' and \
                   self.status not in ['package_shipped', 'package_delivered', 'delivery_confirmed']:
                    self.status = 'blockchain_published'
                    ContractActivity.log(
                        contract=self,
                        action='status_change',
                        user_role='system',
                        details=f"Vertragsstatus auf 'Auf Blockchain veröffentlicht' geändert (Blockchain-Status: {self.blockchain_status})"
                    )
                
                # Log blockchain status change if it changed
                if old_blockchain_status != self.blockchain_status:
                    ContractActivity.log(
                        contract=self,
                        action='status_change',
                        user_role='system',
                        details=f"Blockchain-Status aktualisiert: {old_blockchain_status} -> {self.blockchain_status}"
                    )
                
                # Use update_fields to avoid potential issues with large fields during save
                self.save(update_fields=['blockchain_status', 'status', 'package_status', 'tracking_hash', 'delivery_oracle_confirmed'])
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
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
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