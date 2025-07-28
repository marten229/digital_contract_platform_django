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
                'Accept': 'application/json'
            }
            
            url = f"{self.base_url}/track/shipments"
            params = {
                'trackingNumber': tracking_number,
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            logger.info(f"DHL API Request: {response.url}")
            logger.info(f"Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_dhl_response(data)
            else:
                logger.error(f"DHL API Error: {response.status_code} - {response.text}")
                return {
                    'status': 'error',
                    'message': f'DHL API Error: {response.status_code}',
                    'tracking_number': tracking_number,
                    'details': response.text if response.text else 'Keine Details verfügbar'
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
        try:
            shipments = data.get('shipments', [])
            if not shipments:
                return {
                    'status': 'not_found',
                    'message': 'Keine Sendung gefunden',
                    'tracking_number': data.get('trackingNumber', ''),
                    'events': []
                }
            
            shipment = shipments[0]
            
            events = shipment.get('events', [])
            latest_event = events[0] if events else {}
            
            status_mapping = {
                'delivered': 'delivered',
                'pre-transit': 'in_transit',
                'transit': 'in_transit',
                'out-for-delivery': 'out_for_delivery',
                'delivery-attempted': 'delivery_attempted',
                'exception': 'exception'
            }
            
            raw_status = latest_event.get('statusCode', 'unknown').lower()
            mapped_status = status_mapping.get(raw_status, 'unknown')
            
            formatted_events = []
            for event in events:
                formatted_events.append({
                    'timestamp': event.get('timestamp', ''),
                    'status': event.get('statusCode', ''),
                    'location': event.get('location', {}).get('address', {}).get('addressLocality', ''),
                    'description': event.get('description', '')
                })
            
            return {
                'tracking_number': shipment.get('id', ''),
                'status': mapped_status,
                'last_update': latest_event.get('timestamp', ''),
                'location': latest_event.get('location', {}).get('address', {}).get('addressLocality', ''),
                'estimated_delivery': shipment.get('estimatedTimeOfDelivery', ''),
                'events': formatted_events
            }
            
        except KeyError as e:
            logger.error(f"Fehler beim Parsen der DHL Response - fehlender Key: {str(e)}")
            return {
                'status': 'error',
                'message': f'Parsing-Fehler: {str(e)}',
                'tracking_number': data.get('trackingNumber', ''),
                'raw_data': data
            }
        except Exception as e:
            logger.error(f"Unerwarteter Fehler beim Parsen der DHL Response: {str(e)}")
            return {
                'status': 'error',
                'message': f'Parsing-Fehler: {str(e)}',
                'tracking_number': data.get('trackingNumber', ''),
                'raw_data': data
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
            
            tracking_number = tracking_number.strip() if tracking_number else ""
            
            if not tracking_number:
                raise ValueError("Tracking-Nummer darf nicht leer sein")
            
            logger.info(f"Hash-Generierung: contract_id={contract_id}, tracking_number='{tracking_number}'")
            
            web3_instance = Web3()
            
            tracking_bytes = tracking_number.encode('utf-8')
            hash_value = web3_instance.keccak(tracking_bytes)
            
            logger.info(f"Generierter Hash: {hash_value.hex()}")
            return hash_value
            
        except ImportError:
            logger.error("web3 nicht verfügbar - verwende SHA256 Fallback")
            tracking_number = tracking_number.strip() if tracking_number else ""
            combined = f"{contract_id}:{tracking_number}"
            hash_value = hashlib.sha256(combined.encode()).hexdigest()
            return '0x' + hash_value
        except Exception as e:
            logger.error(f"Fehler beim Generieren des Tracking-Hash: {str(e)}")
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
        
        tracking_number = tracking_number.strip()
        
        if len(tracking_number) < 8 or len(tracking_number) > 20:
            return False
        
        if not tracking_number.replace('-', '').replace(' ', '').isalnum():
            return False
        
        return True
