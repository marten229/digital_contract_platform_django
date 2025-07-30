import requests
import os
import hashlib
from datetime import datetime
from django.utils import timezone
from django.db.models import Q
from .models import Contract

class DHLTrackingService:
    """
    Service to handle DHL tracking functionality.
    This includes checking tracking status and updating contract states.
    """
    def __init__(self):
        # Load settings from environment variables
        # Base URL for the DHL API
        self.base_url = os.environ.get('DHL_API_BASE_URL', "https://api.dhl.com/tracking/v2")
        # Load API credentials from environment variables
        self.api_key = os.environ.get('DHL_API_KEY', '')
        self.api_secret = os.environ.get('DHL_API_SECRET', '')
    
        
    def generate_tracking_hash(self, tracking_number, contract_id=None):
        """
        Generate a hashed value of the tracking number for blockchain storage
        Uses keccak256 hashing to match the smart contract requirements
        
        Args:
            tracking_number: DHL tracking number (wird normalisiert)
            contract_id: Blockchain contract ID (required for proper hash verification)
        """
        if contract_id is None:
            raise ValueError("contract_id is required for tracking hash generation")
        
        # Tracking-Nummer normalisieren (Leerzeichen entfernen) - WICHTIG für Hash-Konsistenz
        tracking_number = tracking_number.strip() if tracking_number else ""
        
        if not tracking_number:
            raise ValueError("Tracking-Nummer darf nicht leer sein")
        
        # Use keccak256 hash like the smart contract expects
        from web3 import Web3
        
        # Create Web3 instance just for hash calculation
        web3_instance = Web3()
        
        # Calculate keccak256 hash of tracking number
        tracking_bytes = tracking_number.encode('utf-8')
        hash_value = web3_instance.keccak(tracking_bytes)
        
        # Return as 0x-prefixed hex string (66 characters: 0x + 64 hex chars)
        return hash_value.hex()
    
    def confirm_delivery(self, contract, confirmed=True, notes=None):
        """
        Seller confirms the delivery is complete and correct
        """
        if contract.status != 'package_delivered':
            return False, "Package has not been delivered yet"
            
        contract.delivery_confirmation = confirmed
        if notes:
            contract.delivery_notes = notes
            
        if confirmed:
            contract.status = 'delivery_confirmed'
            # This will trigger the approveDeliveryAsCreator function on the blockchain
            # The actual blockchain transaction will be created in the view
        else:
            # If not confirmed, handle dispute
            pass
            
        contract.save()
        return True, "Delivery confirmation updated"
