"""
Blockchain-Interface für den Oracle Service

Dieses Modul stellt die Funktionalität zur Interaktion mit dem
Ethereum Smart Contract für Oracle-Bestätigungen bereit.
"""

import logging
import json
import os
from typing import Dict, Any, Optional
from web3 import Web3
from eth_account import Account
from config import OracleConfig

logger = logging.getLogger(__name__)

class BlockchainInterface:
    """
    Interface für Blockchain-Operationen des Oracle Service
    """
    
    def __init__(self):
        self.config = OracleConfig()
        
        # Web3-Verbindung initialisieren
        self.web3 = Web3(Web3.HTTPProvider(self.config.ETHEREUM_NODE_URL))
        
        if not self.web3.is_connected():
            raise ConnectionError(f"Keine Verbindung zum Ethereum-Node: {self.config.ETHEREUM_NODE_URL}")
        
        # Smart Contract ABI laden
        self.contract_abi = self._load_contract_abi()
        self.contract_address = self.config.CONTRACT_ADDRESS
        
        # Smart Contract-Instanz erstellen
        if self.contract_address and self.contract_abi:
            self.contract = self.web3.eth.contract(
                address=self.contract_address,
                abi=self.contract_abi
            )
        else:
            raise ValueError("Contract-Adresse oder ABI nicht verfügbar")
        
        logger.info(f"Blockchain-Interface initialisiert: {self.config.ETHEREUM_NODE_URL}")
        logger.info(f"Smart Contract: {self.contract_address}")
    
    def _load_contract_abi(self) -> list:
        """
        Lädt das Smart Contract ABI
        """
        # ABI aus der Hauptanwendung laden
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abi_path = os.path.join(
            project_root, 
            'contractsapp', 
            'static', 
            'contracts', 
            'DigitalContractPlatform.json'
        )
        try:
            with open(abi_path, 'r') as f:
                contract_data = json.load(f)
                return contract_data.get('abi', [])
        except FileNotFoundError:
            logger.error(f"Contract ABI nicht gefunden: {abi_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Fehler beim Parsen der Contract ABI: {str(e)}")
            raise
    
    def prepare_oracle_confirmation_transaction(self, oracle_address: str, contract_id: int, tracking_number: str) -> Dict[str, Any]:
        """
        Bereitet eine Oracle-Bestätigungstransaktion vor
        
        Args:
            oracle_address: Ethereum-Adresse des Oracle
            contract_id: Blockchain-Contract-ID
            tracking_number: Tracking-Nummer (wird normalisiert)
            
        Returns:
            Vorbereitete Transaktion
        """
        try:
            # Adresse in Checksum-Format konvertieren
            oracle_address = self.web3.to_checksum_address(oracle_address)
            
            # Tracking-Nummer normalisieren
            tracking_number = tracking_number.strip() if tracking_number else ""
            
            if not tracking_number:
                raise ValueError("Tracking-Nummer darf nicht leer sein")
            
            logger.info(f"Bereite Oracle-Bestätigung vor: Contract {contract_id}, Tracking '{tracking_number}'")
            
            # Der Smart Contract erwartet die originale Tracking-Nummer
            # Er berechnet dann intern den Hash: keccak256(abi.encode(contract_id, tracking_number))
            # und vergleicht diesen mit dem gespeicherten Hash
            
            # Debug: Hash-Vergleich vor Transaktion
            try:
                from eth_abi import encode
                from eth_utils import keccak
                
                encoded_data = encode(['uint256', 'string'], [contract_id, tracking_number])
                expected_hash = '0x' + keccak(encoded_data).hex()
                logger.info(f"Erwarteter Hash für Smart Contract Vergleich: {expected_hash}")
                
            except Exception as e:
                logger.warning(f"Hash-Debug fehlgeschlagen: {str(e)}")
            
            # Transaktion vorbereiten
            transaction = self.contract.functions.confirmDeliveryByOracle(
                contract_id, 
                tracking_number  # Originale (normalisierte) Tracking-Nummer für Smart Contract
            ).build_transaction({
                'from': oracle_address,
                'nonce': self.web3.eth.get_transaction_count(oracle_address),
                'gas': 200000,  # Ausreichend Gas für Oracle-Bestätigung
                'gasPrice': self.web3.eth.gas_price
            })
            
            logger.info(f"Oracle-Bestätigungstransaktion vorbereitet für Contract {contract_id}")
            return transaction
            
        except Exception as e:
            logger.error(f"Fehler beim Vorbereiten der Oracle-Transaktion: {str(e)}")
            raise
    
    def get_contract_info(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """
        Holt Informationen über einen Smart Contract
        
        Args:
            contract_id: Die Contract-ID
            
        Returns:
            Contract-Informationen oder None
        """
        try:
            # Annahme: Es gibt eine getContract-Funktion im Smart Contract
            contract_info = self.contract.functions.getContract(contract_id).call()
            return {
                'contract_id': contract_id,
                'status': contract_info[0] if contract_info else None,
                'delivery_confirmed': contract_info[1] if len(contract_info) > 1 else None,
                # Weitere Felder je nach Smart Contract-Struktur
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Contract-Info für {contract_id}: {str(e)}")
            return None
    
    def estimate_gas_for_oracle_confirmation(self, oracle_address: str, contract_id: int, tracking_number: str) -> int:
        """
        Schätzt die Gas-Kosten für eine Oracle-Bestätigung
        
        Args:
            oracle_address: Ethereum-Adresse des Oracle
            contract_id: Blockchain-Contract-ID
            tracking_number: Originale Tracking-Nummer
            
        Returns:
            Geschätzte Gas-Menge
        """
        try:
            oracle_address = self.web3.to_checksum_address(oracle_address)
            
            gas_estimate = self.contract.functions.confirmDeliveryByOracle(
                contract_id, 
                tracking_number
            ).estimate_gas({'from': oracle_address})
            
            # Sicherheitspuffer hinzufügen (20%)
            return int(gas_estimate * 1.2)
            
        except Exception as e:
            logger.error(f"Fehler bei Gas-Schätzung: {str(e)}")
            return 200000  # Fallback-Wert

class OracleKeyManager:
    """
    Verwaltet die privaten Schlüssel für Oracle-Transaktionen
    """
    
    def __init__(self):
        self.config = OracleConfig()
        self.web3 = Web3(Web3.HTTPProvider(self.config.ETHEREUM_NODE_URL))
        
        # Private Key laden
        self.private_key = self._load_private_key()
        self.account = Account.from_key(self.private_key)
        self.address = self.account.address
        
        logger.info(f"Oracle-Schlüssel geladen: {self.address}")
    
    def _load_private_key(self) -> str:
        """
        Lädt den privaten Schlüssel aus der Konfiguration
        """
        # Prüfe ob direkter Private Key gesetzt ist
        if self.config.ORACLE_PRIVATE_KEY:
            return self.config.ORACLE_PRIVATE_KEY
        
        # Ansonsten lade aus Keystore-Datei
        if self.config.ORACLE_KEY_PATH and self.config.ORACLE_KEY_PASSWORD:
            return self._load_key_from_file(
                self.config.ORACLE_KEY_PATH, 
                self.config.ORACLE_KEY_PASSWORD
            )
        
        raise ValueError("Weder ORACLE_PRIVATE_KEY noch ORACLE_KEY_PATH/ORACLE_KEY_PASSWORD gesetzt")
    
    def _load_key_from_file(self, key_path: str, password: str) -> str:
        """
        Lädt einen verschlüsselten privaten Schlüssel aus einer Datei
        """
        try:
            # Prüfe verschiedene mögliche Pfade
            possible_paths = [
                key_path,
                os.path.abspath(key_path)
            ]
            
            if not os.path.isabs(key_path):
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                possible_paths.extend([
                    os.path.join(project_root, key_path),
                    os.path.join(project_root, 'keys', os.path.basename(key_path))
                ])
            
            key_file_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    key_file_path = path
                    break
            
            if not key_file_path:
                raise FileNotFoundError(f"Oracle-Schlüsseldatei nicht gefunden in: {possible_paths}")
            
            with open(key_file_path, 'r') as f:
                encrypted_key = json.load(f)
            
            private_key = Account.decrypt(encrypted_key, password)
            return private_key.hex()
            
        except Exception as e:
            logger.error(f"Fehler beim Laden des Oracle-Schlüssels: {str(e)}")
            raise
    
    def sign_transaction(self, transaction: Dict[str, Any]) -> bytes:
        """
        Signiert eine Transaktion
        
        Args:
            transaction: Die Transaktionsdaten
              Returns:
            Signierte Transaktion (raw transaction)
        """
        try:
            signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
            return signed_tx.rawTransaction
        except Exception as e:
            logger.error(f"Fehler beim Signieren der Transaktion: {str(e)}")
            raise
    
    def send_transaction(self, transaction: Dict[str, Any]) -> str:
        """
        Signiert und sendet eine Transaktion
        
        Args:
            transaction: Die Transaktionsdaten
            
        Returns:
            Transaktions-Hash
        """
        try:
            # Gas-Preis leicht erhöhen für schnellere Bestätigung
            if 'gasPrice' in transaction:
                transaction['gasPrice'] = int(transaction['gasPrice'] * 1.1)
            
            # Aktuelle Nonce setzen
            transaction['nonce'] = self.web3.eth.get_transaction_count(self.address)
            
            # Transaktion signieren
            signed_tx_raw = self.sign_transaction(transaction)
            
            # Transaktion senden
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx_raw)
            
            logger.info(f"Transaktion gesendet: {Web3.to_hex(tx_hash)}")
            
            # Auf Bestätigung warten (mit Timeout)
            try:
                receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                logger.info(f"Transaktion bestätigt in Block {receipt['blockNumber']}")
            except Exception as e:
                logger.warning(f"Timeout beim Warten auf Transaktionsbestätigung: {str(e)}")
            
            return Web3.to_hex(tx_hash)
            
        except Exception as e:
            logger.error(f"Fehler beim Senden der Transaktion: {str(e)}")
            raise
    
    def get_address(self) -> str:
        """
        Gibt die Ethereum-Adresse des Oracle zurück
        """
        return self.address
    
    def get_balance(self) -> float:
        """
        Gibt den ETH-Balance des Oracle-Accounts zurück
        """
        try:
            balance_wei = self.web3.eth.get_balance(self.address)
            balance_eth = self.web3.from_wei(balance_wei, 'ether')
            return float(balance_eth)
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Balance: {str(e)}")
            return 0.0
