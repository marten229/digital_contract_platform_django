"""
Hauptklasse des Oracle Service

Diese Klasse orchestriert alle Operationen des Oracle Service:
- Abfrage von Tracking-Updates
- Oracle-Bestätigungen auf der Blockchain
- Datenbankaktualisierungen
"""

import logging
import time
from datetime import datetime
from typing import List, Tuple, Optional
from config import OracleConfig
from database import DatabaseInterface, Contract
from dhl_tracking import DHLTrackingService
from blockchain import BlockchainInterface, OracleKeyManager

logger = logging.getLogger(__name__)

class OracleService:
    """
    Hauptklasse des Oracle Service
    
    Koordiniert alle Oracle-Operationen und läuft als eigenständiger Dienst.
    """
    
    def __init__(self):
        self.config = OracleConfig()
        
        # Komponenten initialisieren
        try:
            self.db = DatabaseInterface()
            self.dhl_service = DHLTrackingService()
            self.blockchain = BlockchainInterface()
            self.key_manager = OracleKeyManager()
            
            logger.info("Oracle Service erfolgreich initialisiert")
            logger.info(f"Oracle-Adresse: {self.key_manager.get_address()}")
            
        except Exception as e:
            logger.error(f"Fehler bei der Initialisierung des Oracle Service: {str(e)}")
            raise
    
    def check_tracking_updates(self) -> int:
        """
        Prüft alle Verträge auf Tracking-Updates
        
        Returns:
            Anzahl der aktualisierten Verträge
        """
        logger.info("Starte Tracking-Update-Prüfung")
        
        try:
            # Hole alle Verträge mit aktiviertem Tracking
            contracts = self.db.get_contracts_needing_tracking_update()
            logger.info(f"Gefunden: {len(contracts)} Verträge mit aktivem Tracking")
            
            updated_count = 0
            
            for contract in contracts:
                try:
                    # Tracking-Info abrufen
                    tracking_info = self.dhl_service.get_tracking_info(contract.tracking_number)                    
                    if tracking_info.get('status') == 'error':
                        logger.warning(f"Tracking-Fehler für Contract {contract.id}: {tracking_info.get('message')}")
                        continue
                    
                    # Status prüfen (nur lesen, nicht mehr in DB schreiben)
                    new_status = tracking_info.get('status')
                    if new_status and new_status != contract.package_status:
                        updated_count += 1
                        logger.info(f"Contract {contract.id}: Status-Änderung erkannt '{contract.package_status}' -> '{new_status}' (nur Blockchain-Update)")
                        
                        # Tracking-Hash generieren falls Status 'delivered'
                        if new_status == 'delivered' and not contract.tracking_hash:
                            tracking_hash = self.dhl_service.generate_tracking_hash(
                                contract.tracking_number,
                                contract.blockchain_contract_id
                            )
                            logger.info(f"Tracking-Hash für Contract {contract.id} generiert (nur für Blockchain)")
                    
                except Exception as e:
                    logger.error(f"Fehler beim Prüfen von Contract {contract.id}: {str(e)}")
                    continue
            
            logger.info(f"Tracking-Update abgeschlossen: {updated_count} Verträge aktualisiert")
            return updated_count
            
        except Exception as e:
            logger.error(f"Fehler bei Tracking-Update-Prüfung: {str(e)}")
            return 0
    
    def process_oracle_confirmations(self, debug: bool = False) -> Tuple[int, int]:
        """
        Verarbeitet ausstehende Oracle-Bestätigungen
        
        Args:
            debug: Wenn True, werden keine echten Blockchain-Transaktionen gesendet
            
        Returns:
            Tuple von (erfolgreiche_bestätigungen, fehler_anzahl)
        """
        logger.info("Starte Oracle-Bestätigungsverarbeitung")
        
        try:
            # Hole Verträge die auf Oracle-Bestätigung warten
            contracts = self.db.get_pending_oracle_confirmations()
            logger.info(f"Gefunden: {len(contracts)} Verträge für Oracle-Bestätigung")
            
            if not contracts:
                return 0, 0
            
            success_count = 0
            error_count = 0
            oracle_address = self.key_manager.get_address()
            
            for contract in contracts:
                try:                    
                    tracking_info = self.dhl_service.get_tracking_info(contract.tracking_number)
                    
                    if not self.dhl_service.is_delivered(tracking_info):
                        logger.info(f"Contract {contract.id}: Paket noch nicht zugestellt ({tracking_info.get('status')})")
                        continue
                    
                    logger.info(f"Verarbeite Oracle-Bestätigung für Contract {contract.id}")
                    
                    # Tracking-Nummer aus Datenbank lesen und analysieren
                    tracking_number = contract.tracking_number
                    
                    logger.info(f"🔍 TRACKING DEBUG für Contract {contract.id}:")
                    logger.info(f"  - Database Contract ID: {contract.id}")
                    logger.info(f"  - Blockchain Contract ID: {contract.blockchain_contract_id}")
                    logger.info(f"  - Tracking Number (raw): '{tracking_number}'")
                    logger.info(f"  - Tracking Number length: {len(tracking_number) if tracking_number else 0}")
                    logger.info(f"  - Tracking Number (bytes): {tracking_number.encode('utf-8') if tracking_number else b''}")
                    logger.info(f"  - Stored Tracking Hash: {contract.tracking_hash}")
                    
                    if not tracking_number:
                        logger.error(f"❌ Contract {contract.id}: Keine Tracking-Nummer vorhanden")
                        error_count += 1
                        continue
                    
                    # Hash mit der EXAKTEN Tracking-Nummer aus der DB berechnen
                    try:
                        from eth_abi import encode
                        from eth_utils import keccak
                        
                        # Hash berechnen mit exakt der Tracking-Nummer aus der DB
                        encoded_data = encode(['uint256', 'string'], [contract.blockchain_contract_id, tracking_number])
                        calculated_hash = '0x' + keccak(encoded_data).hex()
                        
                        logger.info(f"  - Berechneter Hash: {calculated_hash}")
                        logger.info(f"  - Hash Match: {'✅ JA' if calculated_hash == contract.tracking_hash else '❌ NEIN'}")
                        
                        if calculated_hash != contract.tracking_hash:
                            logger.error(f"❌ HASH MISMATCH DETECTED!")
                            logger.error(f"   Expected: {contract.tracking_hash}")
                            logger.error(f"   Calculated: {calculated_hash}")
                            logger.error(f"   Tracking Number: '{tracking_number}'")
                            logger.error(f"   Contract ID: {contract.blockchain_contract_id}")
                            
                            # Teste verschiedene Varianten
                            variants = [
                                ("stripped", tracking_number.strip()),
                                ("upper", tracking_number.upper()),
                                ("lower", tracking_number.lower()),
                            ]
                            
                            logger.error(f"   Teste Varianten:")
                            for name, variant in variants:
                                variant_encoded = encode(['uint256', 'string'], [contract.blockchain_contract_id, variant])
                                variant_hash = '0x' + keccak(variant_encoded).hex()
                                match = "✅" if variant_hash == contract.tracking_hash else "❌"
                                logger.error(f"     {match} {name}: '{variant}' -> {variant_hash}")
                            
                            error_count += 1
                            continue
                        
                    except Exception as e:
                        logger.error(f"❌ Fehler bei Hash-Berechnung: {str(e)}")
                        error_count += 1
                        continue
                    
                    if not debug:
                        # Echte Blockchain-Transaktion senden
                        logger.info(f"Sende Oracle-Bestätigung für Contract {contract.blockchain_contract_id} an Blockchain mit Tracking-Nummer '{tracking_number}'")
                        
                        # Debug: Hash-Generierung testen
                        generated_hash = self.dhl_service.generate_tracking_hash(tracking_number, contract.blockchain_contract_id)
                        logger.info(f"Debug: Generierter Hash für Contract {contract.blockchain_contract_id} mit Tracking '{tracking_number}': {generated_hash}")
                        
                        # Debug: Auch den Hash aus der Hauptanwendung simulieren
                        try:
                            from eth_abi import encode
                            from eth_utils import keccak
                            encoded_data = encode(['uint256', 'string'], [contract.blockchain_contract_id, tracking_number])
                            expected_hash = '0x' + keccak(encoded_data).hex()
                            logger.info(f"Debug: Erwarteter Hash (wie Smart Contract): {expected_hash}")
                        except Exception as e:
                            logger.error(f"Debug: Fehler bei Hash-Vergleich: {str(e)}")
                        
                        tx_data = self.blockchain.prepare_oracle_confirmation_transaction(
                            oracle_address,
                            contract.blockchain_contract_id,
                            tracking_number,
                        )
                        
                        tx_hash = self.key_manager.send_transaction(tx_data)
                        logger.info(f"Oracle-Bestätigung gesendet: {tx_hash}")
                    else:
                        logger.info(f"DEBUG MODE: Würde Oracle-Bestätigung für Contract {contract.id} senden")
                        # Debug: Hash-Generierung auch im Debug-Modus testen
                        generated_hash = self.dhl_service.generate_tracking_hash(tracking_number, contract.blockchain_contract_id)
                        logger.info(f"DEBUG: Hash für Contract {contract.blockchain_contract_id} mit Tracking '{tracking_number}': {generated_hash}")
                        
                        # Debug: Auch den Hash aus der Hauptanwendung simulieren
                        try:
                            from eth_abi import encode
                            from eth_utils import keccak
                            encoded_data = encode(['uint256', 'string'], [contract.blockchain_contract_id, tracking_number])
                            expected_hash = '0x' + keccak(encoded_data).hex()
                            logger.info(f"DEBUG: Erwarteter Hash (wie Smart Contract): {expected_hash}")
                        except Exception as e:
                            logger.error(f"DEBUG: Fehler bei Hash-Vergleich: {str(e)}")
                    
                    # Kein Datenbankupdate mehr - nur Blockchain-Bestätigung
                    success_count += 1
                    logger.info(f"Contract {contract.id} Oracle-Bestätigung an Blockchain gesendet")
                
                except Exception as e:
                    error_count += 1
                    logger.error(f"Fehler bei Oracle-Bestätigung für Contract {contract.id}: {str(e)}")
                    continue
            
            logger.info(f"Oracle-Bestätigung abgeschlossen: {success_count} erfolgreich, {error_count} Fehler")
            return success_count, error_count
            
        except Exception as e:
            logger.error(f"Fehler bei Oracle-Bestätigungsverarbeitung: {str(e)}")
            return 0, 1
    
    def run_cycle(self, debug: bool = False) -> dict:
        """
        Führt einen kompletten Oracle-Service-Zyklus aus
        
        Args:
            debug: Debug-Modus aktivieren
            
        Returns:
            Dictionary mit Ergebnissen
        """
        start_time = datetime.now()
        logger.info(f"Starte Oracle-Service-Zyklus (Debug: {debug})")
        
        results = {
            'start_time': start_time,
            'tracking_updates': 0,
            'oracle_confirmations_success': 0,
            'oracle_confirmations_errors': 0,
            'errors': []
        }
        
        try:
            # 1. Tracking-Updates prüfen
            results['tracking_updates'] = self.check_tracking_updates()
            
            # 2. Oracle-Bestätigungen verarbeiten
            success, errors = self.process_oracle_confirmations(debug)
            results['oracle_confirmations_success'] = success
            results['oracle_confirmations_errors'] = errors
            
        except Exception as e:
            error_msg = f"Fehler im Oracle-Service-Zyklus: {str(e)}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        results['end_time'] = end_time
        results['duration_seconds'] = duration
        
        logger.info(f"Oracle-Service-Zyklus abgeschlossen in {duration:.2f}s")
        return results
    
    def run_continuous(self, debug: bool = False):
        """
        Läuft kontinuierlich und führt regelmäßig Oracle-Zyklen aus
        
        Args:
            debug: Debug-Modus aktivieren
        """
        logger.info(f"Starte kontinuierlichen Oracle-Service (Intervall: {self.config.CHECK_INTERVAL}s)")
        
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                logger.info(f"--- Oracle-Zyklus #{cycle_count} ---")
                
                try:
                    results = self.run_cycle(debug)
                    
                    # Ergebnisse loggen
                    logger.info(
                        f"Zyklus #{cycle_count} Ergebnisse: "
                        f"Tracking-Updates: {results['tracking_updates']}, "
                        f"Oracle-Bestätigungen: {results['oracle_confirmations_success']}, "
                        f"Fehler: {results['oracle_confirmations_errors']}"
                    )
                    
                except Exception as e:
                    logger.error(f"Fehler in Zyklus #{cycle_count}: {str(e)}")
                
                # Warten bis zum nächsten Zyklus
                logger.info(f"Warte {self.config.CHECK_INTERVAL}s bis zum nächsten Zyklus...")
                time.sleep(self.config.CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("Oracle-Service durch Benutzer beendet")
        except Exception as e:
            logger.error(f"Unerwarteter Fehler im kontinuierlichen Betrieb: {str(e)}")
            raise
    
    def health_check(self) -> dict:
        """
        Führt einen Gesundheitscheck des Oracle Service durch
        
        Returns:
            Dictionary mit Gesundheitsstatus
        """
        health = {
            'timestamp': datetime.now(),
            'status': 'healthy',
            'checks': {},
            'errors': []
        }
        
        # Datenbankverbindung testen
        try:
            if self.db.test_connection():
                health['checks']['database'] = 'OK'
            else:
                health['checks']['database'] = 'ERROR'
                health['status'] = 'unhealthy'
                health['errors'].append('Datenbankverbindung fehlgeschlagen')
        except Exception as e:
            health['checks']['database'] = 'ERROR'
            health['status'] = 'unhealthy'
            health['errors'].append(f'Datenbankfehler: {str(e)}')
        
        # Blockchain-Verbindung testen
        try:
            if self.blockchain.web3.is_connected():
                health['checks']['blockchain'] = 'OK'
            else:
                health['checks']['blockchain'] = 'ERROR'
                health['status'] = 'unhealthy'
                health['errors'].append('Blockchain-Verbindung fehlgeschlagen')
        except Exception as e:
            health['checks']['blockchain'] = 'ERROR'
            health['status'] = 'unhealthy'
            health['errors'].append(f'Blockchain-Fehler: {str(e)}')
        
        # Oracle-Balance prüfen
        try:
            balance = self.key_manager.get_balance()
            health['checks']['oracle_balance'] = f'{balance:.4f} ETH'
            
            # Warnung bei niedrigem Balance
            if balance < 0.01:  # Weniger als 0.01 ETH
                health['status'] = 'warning'
                health['errors'].append(f'Niedriger ETH-Balance: {balance:.4f} ETH')
                
        except Exception as e:
            health['checks']['oracle_balance'] = 'ERROR'
            health['status'] = 'unhealthy'
            health['errors'].append(f'Balance-Fehler: {str(e)}')
        
        return health
