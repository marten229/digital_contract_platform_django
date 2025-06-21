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
        
    def get_tracking_info(self, tracking_number):
        """
        Get tracking information from DHL API for a given tracking number
        """
        # Check if we should use real API or dummy data
        use_dummy = os.environ.get('DHL_USE_DUMMY', 'True').lower() in ('true', '1', 'yes')
        
        if use_dummy:
            return self.get_dummy_tracking_info(tracking_number)
        else:
            return self.get_real_tracking_info(tracking_number)
    
    def get_real_tracking_info(self, tracking_number):
        """
        Get real tracking information from the DHL API
        """
        try:
            headers = {
                'DHL-API-Key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            url = f"{self.base_url}/track/{tracking_number}"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                # Process the response and return standardized format
                return self.parse_dhl_response(data)
            else:
                print(f"DHL API Error: {response.status_code} - {response.text}")
                return {'status': 'error', 'message': 'Failed to fetch tracking data'}
                
        except Exception as e:
            print(f"Error fetching tracking info: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    
    def get_dummy_tracking_info(self, tracking_number):
        """
        Return dummy tracking information for testing purposes
        """
        # For testing purposes, we'll simulate that packages are delivered
        # In a real implementation, this would query the actual DHL API
        
        # Check if we have a contract with this tracking number that should be delivered
        from .models import Contract
        try:
            contract = Contract.objects.get(tracking_number=tracking_number)
            # If the contract status is already package_delivered, keep it delivered
            if contract.status == 'package_delivered':
                status = 'delivered'
            else:
                # For new packages, simulate a progression
                dummy_statuses = ['in_transit', 'out_for_delivery', 'delivered']
                # Use a simple progression based on when the contract was created
                # For demo purposes, let's assume packages are delivered after some time
                status_index = hash(tracking_number) % len(dummy_statuses)
                status = dummy_statuses[status_index]
                
                # Override to delivered for testing Oracle functionality
                if contract.has_dhl_tracking and not contract.delivery_oracle_confirmed:
                    status = 'delivered'
        except Contract.DoesNotExist:
            status = 'delivered'  # Default to delivered for testing
        
        return {
            'tracking_number': tracking_number,
            'status': status,
            'last_update': timezone.now().isoformat(),
            'location': 'Test Location',
            'estimated_delivery': timezone.now().date().isoformat(),
            'events': [
                {
                    'timestamp': timezone.now().isoformat(),
                    'status': status,
                    'location': 'Test Location',
                    'description': f'Package is {status}'
                }
            ]
        }
    
    def parse_dhl_response(self, data):
        """
        Parse DHL API response into standardized format
        """
        # This will depend on the actual DHL API response format
        # For now, return a placeholder structure
        return {
            'tracking_number': data.get('trackingNumber', ''),
            'status': data.get('status', 'unknown').lower(),
            'last_update': data.get('lastUpdate', ''),
            'location': data.get('location', ''),
            'estimated_delivery': data.get('estimatedDelivery', ''),
            'events': data.get('events', [])
        }
    
    def update_contract_status(self, contract):
        """
        Update a contract's tracking status based on the latest DHL data
        """
        if not contract.tracking_number:
            return None
            
        tracking_info = self.get_tracking_info(contract.tracking_number)
        
        if tracking_info.get('status') == 'error':
            return tracking_info
        
        # Update contract fields
        old_status = contract.package_status
        contract.package_status = tracking_info.get('status')
        contract.last_tracking_update = timezone.now()
        
        # Update the overall contract status if package is delivered
        if tracking_info.get('status') == 'delivered' and contract.status != 'package_delivered':
            contract.status = 'package_delivered'
        
        contract.save()
        
        # Log status change if it's different
        if old_status != contract.package_status:
            print(f"Contract {contract.id} status updated: {old_status} -> {contract.package_status}")
        
        return tracking_info
    
    def check_for_updates(self):
        """
        Check for tracking updates on all contracts with DHL tracking enabled
        """
        # Get all contracts with tracking enabled
        tracking_contracts = Contract.objects.filter(
            has_dhl_tracking=True,
            tracking_number__isnull=False,
            status__in=['package_shipped', 'package_delivered']        )
        
        updates = []
        
        for contract in tracking_contracts:
            tracking_info = self.update_contract_status(contract)
            updates.append({
                'contract': contract,
                'tracking_info': tracking_info
            })            
        return updates
        
    def generate_tracking_hash(self, tracking_number, contract_id=None):
        """
        Generate a hashed value of the tracking number for blockchain storage
        Uses abi.encode equivalent hashing to prevent hash collisions
        
        Args:
            tracking_number: DHL tracking number (wird normalisiert)
            contract_id: Blockchain contract ID (required for proper hash verification)
        """
        # Using keccak256(abi.encode(contract_id, tracking_number)) equivalent in Python
        # This matches the Solidity contract's hash generation method
        from eth_abi import encode
        from eth_utils import keccak
        
        if contract_id is None:
            raise ValueError("contract_id is required for tracking hash generation")
        
        # Tracking-Nummer normalisieren (Leerzeichen entfernen) - WICHTIG für Hash-Konsistenz
        tracking_number = tracking_number.strip() if tracking_number else ""
        
        if not tracking_number:
            raise ValueError("Tracking-Nummer darf nicht leer sein")
        
        # Encode contract_id and tracking_number like in Solidity: abi.encode(uint256, string)
        # This mimics the Smart Contract's hash generation exactly
        encoded_data = encode(['uint256', 'string'], [contract_id, tracking_number])
        
        # Apply keccak256 hash
        hashed_value = keccak(encoded_data)
        
        # Return as 0x-prefixed hex string
        return '0x' + hashed_value.hex()
    
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
        
    def process_oracle_confirmation(self, contract):
        """
        Process Oracle confirmation for a contract with delivery tracking
        This would be called by a scheduled job or API endpoint
        """
        if not contract.has_dhl_tracking or not contract.tracking_number:
            return False, "No tracking information available"
              # Generate tracking hash if not already present
        if not contract.tracking_hash:
            contract.tracking_hash = self.generate_tracking_hash(contract.tracking_number, contract.blockchain_contract_id)
            
        # Get the latest tracking info
        tracking_info = self.get_tracking_info(contract.tracking_number)
        
        # Only proceed if the package is delivered
        if tracking_info.get('status') == 'delivered':
            # Update the contract status
            contract.package_status = 'delivered'
            contract.status = 'package_delivered'
            contract.last_tracking_update = timezone.now()
            contract.save()
            
            # In a real implementation, this would trigger the Oracle
            # to call confirmDeliveryByOracle on the blockchain
            
            return True, "Package confirmed as delivered by Oracle"
        
        return False, f"Package not yet delivered. Current status: {tracking_info.get('status')}"
