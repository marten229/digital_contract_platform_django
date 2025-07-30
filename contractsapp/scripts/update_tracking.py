#!/usr/bin/env python
"""
DHL Tracking Updates and Oracle Confirmation Script

This script serves two purposes:
1. Automatically checking DHL tracking status for all contracts with tracking enabled
2. Processing Oracle confirmations for delivered packages on the blockchain

Features:
- Updates tracking status via DHL API
- Logs delivery status changes
- Generates tracking hashes for blockchain verification
- Processes Oracle confirmations for delivered packages
- Creates blockchain transactions for delivery confirmations
- Updates contract status in the database

Usage:
    python update_tracking.py [--debug]

Options:
    --debug     Run in debug mode (no actual blockchain transactions)

Schedule this script to run at regular intervals (e.g., every hour via cron or Celery)
to keep tracking information updated and process confirmations in a timely manner.

Example cron setup:
    0 * * * * cd /path/to/project && python contractsapp/scripts/update_tracking.py

Requirements:
    - Access to DHL API
    - Oracle user with Ethereum address and sufficient ETH for transactions
    - Oracle user must be in the 'Oracle' group
"""

import os
import django
import sys
import logging
import json
import argparse
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "digital_contract_platform.settings")
django.setup()

from contractsapp.models import Contract, ContractActivity
from contractsapp.dhl_tracking import DHLTrackingService
from contractsapp.blockchain import BlockchainService
from django.contrib.auth import get_user_model

User = get_user_model()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"tracking_updates_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('tracking_updates')

def get_oracle_user():
    """Get the oracle user from the database"""
    try:
        oracle_user = User.objects.filter(groups__name='Oracle').first()
        if not oracle_user:
            logger.error("No Oracle user found. Please create a user and assign it to the Oracle group.")
            return None
        
        if not oracle_user.ethereum_address:
            logger.error(f"Oracle user {oracle_user.username} does not have an Ethereum address.")
            return None
            
        return oracle_user
    except Exception as e:
        logger.error(f"Error getting Oracle user: {str(e)}")
        return None


def process_oracle_confirmations(debug=False):
    """
    Process delivery confirmations as Oracle for contracts that have been delivered
    Using direct key management
    """
    from oracle_service.oracle_key_manager import OracleKeyManager
    import traceback
    
    try:
        logger.info("Initializing Oracle key manager for blockchain transactions")
        
        oracle_key_manager = OracleKeyManager()
        oracle_address = oracle_key_manager.get_address()
        
        oracle_user = get_oracle_user()
        
        logger.info(f"Oracle successfully initialized with address: {oracle_address}")
    except Exception as e:
        logger.error(f"Failed to initialize Oracle key manager: {str(e)}")
        logger.error(traceback.format_exc())
        return False
    
    pending_contracts = Contract.objects.filter(
        has_dhl_tracking=True,
        tracking_number__isnull=False,
        status='package_delivered',
        delivery_oracle_confirmed=False
    )
    
    logger.info(f"Found {len(pending_contracts)} contracts pending Oracle confirmation")
    
    if not pending_contracts:
        return True
    
    tracking_service = DHLTrackingService()
    blockchain_service = BlockchainService()
    
    processed_count = 0
    error_count = 0
    
    for contract in pending_contracts:
        try:
            success, message = tracking_service.process_oracle_confirmation(contract)
            
            if success:
                logger.info(f"Processing Oracle confirmation for contract {contract.id}")
                if not debug:
                    tx_data = blockchain_service.confirm_delivery_by_oracle(
                        oracle_address,
                        contract.blockchain_contract_id,
                        contract.tracking_hash
                    )
                    
                    tx_hash = oracle_key_manager.send_transaction(tx_data)
                    logger.info(f"Oracle confirmation transaction sent: {tx_hash}")
                
                else:
                    logger.info(f"DEBUG MODE: Would send Oracle confirmation for contract {contract.id}")
                
                try:
                    contract.delivery_oracle_confirmed = True
                    contract.save()
                    ContractActivity.log(
                        contract=contract,
                        user=oracle_user,
                        action='oracle_confirmation',
                        user_role='oracle',
                        details=f"Oracle bestätigt Lieferung für Tracking #{contract.tracking_number}"
                    )
                    processed_count += 1
                    logger.info(f"Successfully processed contract {contract.id}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error updating contract status: {str(e)}")
            else:
                logger.warning(f"Contract {contract.id} not ready for confirmation: {message}")
            
        except Exception as e:
            error_count += 1
            logger.error(f"Error processing contract {contract.id}: {str(e)}")
    
    logger.info(f"Oracle confirmation process completed: {processed_count} processed, {error_count} errors")
    return processed_count > 0 or error_count == 0


def update_all_tracking(debug=False):
    """Update tracking status for all contracts with DHL tracking enabled"""
    logger.info("Starting DHL tracking update task")
    
    tracking_service = DHLTrackingService()
    
    updates = tracking_service.check_for_updates()
    
    for update in updates:
        contract = update['contract']
        tracking_info = update['tracking_info']
        if contract.package_status == 'delivered':
            ContractActivity.log(
                contract=contract,
                action='package_delivered',
                user_role='system',
                details=f"Paket wurde laut DHL zugestellt am {contract.last_tracking_update.strftime('%d.%m.%Y %H:%M')}"
            )
            logger.info(f"Contract #{contract.pk} marked as delivered")
        else:
            ContractActivity.log(
                contract=contract,
                action='tracking_updated',
                user_role='system',
                details=f"Tracking-Status aktualisiert: {contract.package_status}"
            )
            logger.info(f"Contract #{contract.pk} updated to status: {contract.package_status}")
    
    logger.info(f"DHL tracking update complete. Updated {len(updates)} contracts.")
    
    if process_oracle_confirmations(debug=debug):
        logger.info("Oracle confirmation process completed successfully")
    else:
        logger.warning("Oracle confirmation process completed with issues")
    
    return len(updates)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DHL Tracking Update and Oracle Confirmation Script")
    parser.add_argument('--debug', action='store_true', help='Run in debug mode (no blockchain transactions)')
    args = parser.parse_args()
    
    if args.debug:
        logger.info("Running in DEBUG mode")
    
    update_all_tracking(debug=args.debug)
