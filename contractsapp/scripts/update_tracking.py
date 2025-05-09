"""
Script for automatically checking DHL tracking status for all contracts with tracking enabled.
This can be run as a scheduled task (e.g., via cron or Celery) to keep package tracking information updated.
"""

import os
import django
import sys
from datetime import datetime

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "digital_contract_platform.settings")
django.setup()

# Import after Django setup
from contractsapp.models import Contract, ContractActivity
from contractsapp.dhl_tracking import DHLTrackingService

def update_all_tracking():
    """Update tracking status for all contracts with DHL tracking enabled"""
    print(f"[{datetime.now().isoformat()}] Starting DHL tracking update task")
    
    # Initialize the tracking service
    tracking_service = DHLTrackingService()
    
    # Get updates for all contracts with tracking
    updates = tracking_service.check_for_updates()
    
    for update in updates:
        contract = update['contract']
        tracking_info = update['tracking_info']
        
        # Create activity log for each update
        if contract.package_status == 'delivered':
            ContractActivity.objects.create(
                contract=contract,
                user=None,  # System action
                action='package_delivered',
                details=f"Paket wurde laut DHL zugestellt am {contract.last_tracking_update.strftime('%d.%m.%Y %H:%M')}"
            )
            print(f"Contract #{contract.pk} marked as delivered")
        else:
            ContractActivity.objects.create(
                contract=contract,
                user=None,  # System action
                action='tracking_updated',
                details=f"Tracking-Status aktualisiert: {contract.package_status}"
            )
            print(f"Contract #{contract.pk} updated to status: {contract.package_status}")
    
    print(f"[{datetime.now().isoformat()}] DHL tracking update complete. Updated {len(updates)} contracts.")
    return len(updates)

if __name__ == "__main__":
    update_all_tracking()
