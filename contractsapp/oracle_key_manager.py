"""
Oracle-User-Management für automatisierte Blockchain-Transaktionen.
Ermöglicht signierte Transaktionen ohne MetaMask-Interaktion.
"""

import os
import json
from web3 import Web3
from eth_account import Account
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

class OracleKeyManager:
    """
    Verwaltet die private Key-Funktionalität für den Oracle-User,
    um automatische Transaktionen zu ermöglichen.
    """
    def __init__(self):
        # Private Key aus Umgebungsvariable oder gesicherter Quelle laden
        self.private_key = os.environ.get('ORACLE_PRIVATE_KEY')
        
        if not self.private_key:
            # Alternative: Key aus einer verschlüsselten Datei laden
            key_path = getattr(settings, 'ORACLE_KEY_PATH', None)
            key_password = os.environ.get('ORACLE_KEY_PASSWORD')
            
            # Debugging: Log versuchten Pfad
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Attempting to load Oracle key from: {key_path}")
            
            if key_path and key_password:
                # Try multiple paths to find the key file
                possible_paths = [
                    key_path,  # Try the direct path first
                ]
                
                # Handle relative paths
                if not os.path.isabs(key_path):
                    # Try relative to BASE_DIR
                    possible_paths.append(os.path.join(settings.BASE_DIR, key_path))
                    # Try in the keys folder
                    possible_paths.append(os.path.join(settings.BASE_DIR, 'keys', os.path.basename(key_path)))
                
                # Try each path
                key_found = False
                for path in possible_paths:
                    if os.path.exists(path):
                        logger.info(f"Oracle key file found at: {path}")
                        try:
                            self.private_key = self._load_key_from_file(path, key_password)
                            key_found = True
                            break
                        except Exception as e:
                            logger.error(f"Error loading key from {path}: {str(e)}")
                
                if not key_found:
                    paths_str = "\n - ".join(possible_paths)
                    logger.error(f"Oracle key file not found at any of these locations:\n - {paths_str}")
                    raise ImproperlyConfigured(f"Oracle key file not found at any of these locations:\n - {paths_str}")
            else:
                raise ImproperlyConfigured(
                    "Oracle private key not found. Set ORACLE_PRIVATE_KEY environment variable "
                    "or configure ORACLE_KEY_PATH and ORACLE_KEY_PASSWORD."
                )
                
        # Web3-Verbindung herstellen
        ethereum_node_url = getattr(settings, 'ETHEREUM_NODE_URL', 'http://localhost:8545')
        self.web3 = Web3(Web3.HTTPProvider(ethereum_node_url))
        
        # Account-Objekt initialisieren
        self.account = Account.from_key(self.private_key)
        self.address = self.account.address
        
    def _load_key_from_file(self, key_path, password):
        """Lädt einen verschlüsselten privaten Schlüssel aus einer Datei"""
        try:
            with open(key_path, 'r') as f:
                encrypted_key = json.load(f)
                
            private_key = Account.decrypt(encrypted_key, password)
            return private_key.hex()
        except Exception as e:
            raise ImproperlyConfigured(f"Failed to load Oracle private key: {str(e)}")
    
    @staticmethod
    def generate_keystore(password, output_path=None):
        """
        Generiert ein neues Ethereum-Schlüsselpaar und speichert es als verschlüsselte Keystore-Datei
        
        Verwende diese Methode einmalig, um einen Oracle-Schlüssel zu erstellen.
        """
        acct = Account.create('ENTROPY SEED')  # Hier könnte ein besserer Seed verwendet werden
        private_key = acct.key
        address = acct.address
        
        # Keystore erstellen (verschlüsselter private key)
        encrypted_key = Account.encrypt(private_key, password)
        
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(encrypted_key, f)
                
        return {
            'address': address,
            'keystore': encrypted_key
        }
    
    def sign_transaction(self, transaction):
        """
        Signiert eine Blockchain-Transaktion mit dem privaten Schlüssel
        
        Args:
            transaction: Die vorbereitete Transaktion (dict)
            
        Returns:
            Die signierte Transaktion, bereit zum Senden
        """
        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        return signed_tx
        
    def send_transaction(self, transaction):
        """
        Signiert und sendet eine Transaktion
        
        Args:
            transaction: Die vorbereitete Transaktion (dict)
            
        Returns:
            tx_hash: Der Hash der gesendeten Transaktion
        """
        signed_tx = self.sign_transaction(transaction)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        return self.web3.toHex(tx_hash)
    
    def get_address(self):
        """
        Gibt die Ethereum-Adresse des Oracle-Benutzers zurück
        
        Returns:
            str: Die Ethereum-Adresse
        """
        return self.address
