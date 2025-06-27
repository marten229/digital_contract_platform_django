"""
DHL Tracking Service für den Oracle Service

Eigenständige DHL-Tracking-Funktionalität die unabhängig von der
Hauptanwendung läuft und nur die notwendigen Tracking-Informationen abruft.
"""

import requests
import logging
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from config import OracleConfig

logger = logging.getLogger(__name__)

class DHLTrackingService:
    """
    Service zur Abfrage von DHL-Tracking-Informationen
    
    Dieser Service läuft eigenständig und hat keine Django-Abhängigkeiten.
    """
    
    def __init__(self):
        self.config = OracleConfig()
        self.base_url = self.config.DHL_API_BASE_URL
        self.api_key = self.config.DHL_API_KEY
        self.api_secret = self.config.DHL_API_SECRET
        self.use_dummy = self.config.DHL_USE_DUMMY
        
        logger.info(f"DHL Tracking Service initialisiert (Dummy Mode: {self.use_dummy})")
    
    def get_tracking_info(self, tracking_number: str) -> Dict[str, Any]:
        """
        Holt Tracking-Informationen für eine bestimmte Tracking-Nummer
        
        Args:
            tracking_number: Die DHL-Tracking-Nummer
            
        Returns:
            Dictionary mit Tracking-Informationen
        """
        if self.use_dummy:
            return self._get_dummy_tracking_info(tracking_number)
        else:
            return self._get_real_tracking_info(tracking_number)
    
    def _get_real_tracking_info(self, tracking_number: str) -> Dict[str, Any]:
        """
        Holt echte Tracking-Informationen von der DHL API
        """
        try:
            headers = {
                'DHL-API-Key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            url = f"{self.base_url}/track/{tracking_number}"
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_dhl_response(data)
            else:
                logger.error(f"DHL API Error: {response.status_code} - {response.text}")
                return {
                    'status': 'error',
                    'message': f'DHL API Error: {response.status_code}',
                    'tracking_number': tracking_number
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Netzwerk-Fehler bei DHL API: {str(e)}")
            return {
                'status': 'error',
                'message': f'Netzwerk-Fehler: {str(e)}',
                'tracking_number': tracking_number
            }
        except Exception as e:
            logger.error(f"Unerwarteter Fehler bei DHL API: {str(e)}")
            return {
                'status': 'error',
                'message': f'Unerwarteter Fehler: {str(e)}',
                'tracking_number': tracking_number
            }
    
    def _get_dummy_tracking_info(self, tracking_number: str) -> Dict[str, Any]:
        """
        Erstellt Dummy-Tracking-Informationen für Tests
        """
        
        return {
            'tracking_number': tracking_number,
            'status': 'delivered',
            'last_update': datetime.now().isoformat(),
            'location': 'Test-Standort',
            'estimated_delivery': datetime.now().date().isoformat(),
            'events': [
                {
                    'timestamp': datetime.now().isoformat(),
                    'status': 'delivered',
                    'location': 'Test-Standort',
                    'description': f'Paket ist delivered'
                }
            ]
        }
    
    def _parse_dhl_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parst die DHL API-Antwort in ein standardisiertes Format
        """
        # Dies hängt vom tatsächlichen DHL API-Antwortformat ab
        # Placeholder-Implementierung
        return {            'tracking_number': data.get('trackingNumber', ''),
            'status': data.get('status', 'unknown').lower(),
            'last_update': data.get('lastUpdate', ''),
            'location': data.get('location', ''),
            'estimated_delivery': data.get('estimatedDelivery', ''),
            'events': data.get('events', [])
        }
    
    def generate_tracking_hash(self, tracking_number: str, contract_id: int) -> str:
        """
        Generiert einen Tracking-Hash, der mit dem Smart Contract kompatibel ist
        
        Verwendet keccak256 Hash der Tracking-Nummer direkt
        
        Args:
            tracking_number: Die DHL-Tracking-Nummer (wird normalisiert)
            contract_id: Die Blockchain-Contract-ID (für Kompatibilität)
            
        Returns:
            Hex-String des Hashes (als bytes32)
        """
        try:
            from web3 import Web3
            
            # Tracking-Nummer normalisieren (Leerzeichen entfernen)
            tracking_number = tracking_number.strip() if tracking_number else ""
            
            if not tracking_number:
                raise ValueError("Tracking-Nummer darf nicht leer sein")
            
            logger.info(f"Hash-Generierung: contract_id={contract_id}, tracking_number='{tracking_number}'")
            
            # Create Web3 instance for keccak calculation
            web3_instance = Web3()
            
            # Calculate keccak256 hash of tracking number
            tracking_bytes = tracking_number.encode('utf-8')
            hash_value = web3_instance.keccak(tracking_bytes)
            
            logger.info(f"Generierter Hash: {hash_value.hex()}")
            return hash_value
            
        except ImportError:
            logger.error("web3 nicht verfügbar - verwende SHA256 Fallback")
            # Fallback für den Fall, dass web3 nicht verfügbar ist
            tracking_number = tracking_number.strip() if tracking_number else ""
            combined = f"{contract_id}:{tracking_number}"
            hash_value = hashlib.sha256(combined.encode()).hexdigest()
            return '0x' + hash_value
        except Exception as e:
            logger.error(f"Fehler beim Generieren des Tracking-Hash: {str(e)}")
            # Fallback
            tracking_number = tracking_number.strip() if tracking_number else ""
            combined = f"{contract_id}:{tracking_number}"
            hash_value = hashlib.sha256(combined.encode()).hexdigest()
            return '0x' + hash_value
    
    def is_delivered(self, tracking_info: Dict[str, Any]) -> bool:
        """
        Prüft ob ein Paket laut Tracking-Info zugestellt wurde
        
        Args:
            tracking_info: Tracking-Informationen
            
        Returns:
            True wenn zugestellt, False sonst
        """
        if tracking_info.get('status') == 'error':
            return False
        
        return tracking_info.get('status', '').lower() == 'delivered'
    
    def validate_tracking_number(self, tracking_number: str) -> bool:
        """
        Validiert eine DHL-Tracking-Nummer
        
        Args:
            tracking_number: Die zu validierende Tracking-Nummer
            
        Returns:
            True wenn gültig, False sonst
        """
        if not tracking_number or len(tracking_number.strip()) == 0:
            return False
        
        # Einfache Validierung - in Realität würde man das DHL-Format prüfen
        tracking_number = tracking_number.strip()
        
        # DHL-Tracking-Nummern sind typischerweise 10-12 Zeichen
        if len(tracking_number) < 8 or len(tracking_number) > 20:
            return False
        
        # Sollte alphanumerisch sein
        if not tracking_number.replace('-', '').replace(' ', '').isalnum():
            return False
        
        return True
