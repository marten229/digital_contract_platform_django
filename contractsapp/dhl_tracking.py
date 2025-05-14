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
                'Accept': 'application/json'
            }
            
            if self.api_secret:
                headers['DHL-API-Secret'] = self.api_secret
            
            response = requests.get(
                f"{self.base_url}/track?trackingNumber={tracking_number}", 
                headers=headers
            )
            
            # Check if the request was successful
            if response.status_code == 200:
                data = response.json()
                
                # Map DHL API response to our simplified format
                shipments = data.get('shipments', [])
                if shipments:
                    shipment = shipments[0]  # Get first shipment
                    status = self._map_dhl_status(shipment.get('status', {}).get('statusCode', ''))
                    events = []
                    
                    for event in shipment.get('events', []):
                        events.append({
                            'timestamp': event.get('timestamp', ''),
                            'status': event.get('description', ''),
                            'location': event.get('location', {}).get('address', {}).get('addressLocality', '')
                        })
                    
                    return {
                        'tracking_number': tracking_number,
                        'status': status,
                        'estimated_delivery': shipment.get('estimatedTimeOfDelivery', ''),
                        'last_update': events[0].get('timestamp') if events else timezone.now().isoformat(),
                        'location': events[0].get('location') if events else '',
                        'events': events
                    }
            
            # If we reach here, there was an error or no shipments found
            print(f"DHL API Error: {response.status_code} - {response.text}")
            return self.get_dummy_tracking_info(tracking_number, status='unknown')
            
        except Exception as e:
            print(f"Error calling DHL API: {str(e)}")
            # Fallback to dummy data in case of errors
            return self.get_dummy_tracking_info(tracking_number, status='unknown')
    
    def _map_dhl_status(self, dhl_status_code):
        """Maps DHL status codes to our simplified status values"""
        # Map the DHL status codes to our simplified status values
        # This is a simplified mapping and should be expanded based on actual DHL codes
        status_mapping = {
            'pre-transit': 'initialized',
            'transit': 'in_transit',
            'delivered': 'delivered',
            'out-for-delivery': 'out_for_delivery',
            'failure': 'failed',
            'unknown': 'unknown'
        }
        
        # Default to 'in_transit' if we don't recognize the status
        return status_mapping.get(dhl_status_code.lower(), 'in_transit')
    
    def get_dummy_tracking_info(self, tracking_number, status=None):
        """
        Returns simulated tracking data for development/testing
        """
        # For development/demo purposes, return simulated data
        return {
            'tracking_number': tracking_number,
            'status': status or 'delivered',  # Options: in_transit, out_for_delivery, delivered
            'estimated_delivery': '2025-05-05T12:00:00Z',
            'last_update': timezone.now().isoformat(),
            'location': 'Sorting center',
            'events': [
                {
                    'timestamp': timezone.now().isoformat(),
                    'status': 'Package received at sorting center',
                    'location': 'Berlin Sorting Center'
                }
            ]
        }
    
    def update_contract_status(self, contract):
        """
        Update the contract status based on the current tracking status
        """
        if not contract.has_dhl_tracking or not contract.tracking_number:
            return
            
        tracking_info = self.get_tracking_info(contract.tracking_number)
        
        # Update contract with tracking info
        contract.package_status = tracking_info.get('status', 'unknown')
        contract.last_tracking_update = timezone.now()
        
        # If package is delivered, update contract status
        if tracking_info.get('status') == 'delivered':
            contract.status = 'package_delivered'
            # Automatic fulfillment for seller - awaiting confirmation
        
        contract.save()
        
        return tracking_info
    
    def check_for_updates(self):
        """
        Bulk check for tracking updates on all contracts with DHL tracking enabled
        """
        # Find all contracts with DHL tracking that haven't been marked as delivered yet
        tracking_contracts = Contract.objects.filter(
            has_dhl_tracking=True,
            tracking_number__isnull=False,
        ).exclude(
            Q(status='package_delivered') | 
            Q(status='delivery_confirmed')
        )
        
        updates = []
        for contract in tracking_contracts:
            tracking_info = self.update_contract_status(contract)
            updates.append({
                'contract': contract,
                'tracking_info': tracking_info
            })
            
        return updates
        
    def generate_tracking_hash(self, tracking_number):
        """
        Generate a hashed value of the tracking number for blockchain storage
        Uses abi.encode equivalent hashing to prevent hash collisions
        """
        # Using keccak256(abi.encode(tracking_number)) equivalent in Python
        # This is compatible with the Solidity contract's verification method
        from eth_abi import encode
        from eth_utils import keccak
        
        # Encode the tracking number as a string (bytes32)
        # This mimics abi.encode in Solidity
        encoded_data = encode(['string'], [tracking_number])
        
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
