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
                    
                    # Status aktualisieren falls geändert
                    new_status = tracking_info.get('status')
                    if new_status and new_status != contract.package_status:
                        success = self.db.update_tracking_status(
                            contract.id,
                            new_status,
                            datetime.now()
                        )
                        
                        if success:
                            updated_count += 1
                            logger.info(f"Contract {contract.id}: Status aktualisiert auf '{new_status}'")
                            
                            # Tracking-Hash setzen falls noch nicht vorhanden
                            if new_status == 'delivered' and not contract.tracking_hash:
                                tracking_hash = self.dhl_service.generate_tracking_hash(
                                    contract.tracking_number,
                                    contract.blockchain_contract_id
                                )
                                self.db.set_tracking_hash(contract.id, tracking_hash)
                                logger.info(f"Tracking-Hash für Contract {contract.id} gesetzt")
                    
                except Exception as e:
                    logger.error(f"Fehler beim Aktualisieren von Contract {contract.id}: {str(e)}")
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
                    # Prüfe ob das Paket wirklich zugestellt wurde
                    tracking_info = self.dhl_service.get_tracking_info(contract.tracking_number)
                    
                    if not self.dhl_service.is_delivered(tracking_info):
                        logger.info(f"Contract {contract.id}: Paket noch nicht zugestellt ({tracking_info.get('status')})")
                        continue
                    
                    # Tracking-Hash generieren falls nicht vorhanden
                    if not contract.tracking_hash:
                        tracking_hash = self.dhl_service.generate_tracking_hash(
                            contract.tracking_number,
                            contract.blockchain_contract_id
                        )
                        self.db.set_tracking_hash(contract.id, tracking_hash)
                        contract.tracking_hash = tracking_hash
                    
                    logger.info(f"Verarbeite Oracle-Bestätigung für Contract {contract.id}")
                    
                    if not debug:
                        # Echte Blockchain-Transaktion senden
                        tx_data = self.blockchain.prepare_oracle_confirmation_transaction(
                            oracle_address,
                            contract.blockchain_contract_id,
                            contract.tracking_number  # Originale Tracking-Nummer für Smart Contract
                        )
                        
                        tx_hash = self.key_manager.send_transaction(tx_data)
                        logger.info(f"Oracle-Bestätigung gesendet: {tx_hash}")
                    else:
                        logger.info(f"DEBUG MODE: Würde Oracle-Bestätigung für Contract {contract.id} senden")
                    
                    # Datenbank aktualisieren
                    if self.db.update_contract_oracle_confirmation(contract.id, True):
                        success_count += 1
                        logger.info(f"Contract {contract.id} als Oracle-bestätigt markiert")
                    else:
                        error_count += 1
                        logger.error(f"Fehler beim Markieren von Contract {contract.id} als bestätigt")
                
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
