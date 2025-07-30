"""
Logging-Konfiguration für den Oracle Service

Konfiguriert strukturiertes Logging für alle Oracle-Service-Komponenten.
"""

import logging
import logging.handlers
import os
from datetime import datetime
from config import OracleConfig

def setup_logging(config: OracleConfig = None):
    """
    Konfiguriert das Logging-System für den Oracle Service
    
    Args:
        config: OracleConfig-Instanz (optional)
    """
    if config is None:
        config = OracleConfig()
    
    # Root Logger konfigurieren
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    
    # Entferne existierende Handler
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Formatter erstellen
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console Handler mit UTF-8 Encoding
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Für Windows: UTF-8 Encoding setzen um Unicode-Zeichen zu unterstützen
    import sys
    if hasattr(console_handler.stream, 'reconfigure'):
        try:
            console_handler.stream.reconfigure(encoding='utf-8')
        except:
            pass  # Fallback falls reconfigure nicht verfügbar
    
    root_logger.addHandler(console_handler)
      # File Handler mit Rotation
    if config.LOG_FILE:
        # Logs-Verzeichnis erstellen falls nicht vorhanden
        log_dir = os.path.dirname(config.LOG_FILE) if os.path.dirname(config.LOG_FILE) else 'logs'
        
        # Absoluter Pfad für Log-Verzeichnis falls relativ
        if not os.path.isabs(log_dir):
            current_dir = os.path.dirname(os.path.abspath(__file__))
            log_dir = os.path.join(current_dir, log_dir)
        
        os.makedirs(log_dir, exist_ok=True)
        
        # Vollständiger Log-Datei-Pfad
        if not os.path.isabs(config.LOG_FILE):
            current_dir = os.path.dirname(os.path.abspath(__file__))
            log_file_path = os.path.join(current_dir, config.LOG_FILE)
        else:
            log_file_path = config.LOG_FILE
          # Rotating File Handler (max 10MB, 5 Backups) mit UTF-8 Encoding
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'  # UTF-8 für Unicode-Unterstützung
        )
        file_handler.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Spezielle Logger für externe Bibliotheken weniger verbose machen
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('web3').setLevel(logging.WARNING)
    
    # Oracle-Service-Logger
    oracle_logger = logging.getLogger('oracle_service')
    oracle_logger.info("Logging konfiguriert")
    
    return root_logger

class OracleServiceLogger:
    """
    Spezieller Logger für Oracle-Service-Events
    """
    
    def __init__(self, name: str = 'oracle_service'):
        self.logger = logging.getLogger(name)
    
    def log_cycle_start(self, cycle_number: int):
        """Loggt den Start eines Oracle-Zyklus"""
        self.logger.info(f"=== Oracle-Zyklus #{cycle_number} gestartet ===")
    
    def log_cycle_end(self, cycle_number: int, duration: float, results: dict):
        """Loggt das Ende eines Oracle-Zyklus"""
        self.logger.info(
            f"=== Oracle-Zyklus #{cycle_number} beendet nach {duration:.2f}s === "
            f"Tracking-Updates: {results.get('tracking_updates', 0)}, "
            f"Oracle-Bestätigungen: {results.get('oracle_confirmations_success', 0)}, "
            f"Fehler: {results.get('oracle_confirmations_errors', 0)}"
        )
    
    def log_tracking_update(self, contract_id: int, old_status: str, new_status: str):
        """Loggt ein Tracking-Update"""
        self.logger.info(f"Contract {contract_id}: Tracking-Status {old_status} -> {new_status}")
    
    def log_oracle_confirmation(self, contract_id: int, tx_hash: str):
        """Loggt eine Oracle-Bestätigung"""
        self.logger.info(f"Oracle-Bestätigung für Contract {contract_id}: {tx_hash}")
    
    def log_error(self, operation: str, error: Exception, contract_id: int = None):
        """Loggt einen Fehler"""
        if contract_id:
            self.logger.error(f"Fehler bei {operation} für Contract {contract_id}: {str(error)}")
        else:
            self.logger.error(f"Fehler bei {operation}: {str(error)}")
    
    def log_health_check(self, health_status: dict):
        """Loggt einen Gesundheitscheck"""
        status = health_status.get('status', 'unknown')
        if status == 'healthy':
            self.logger.info("Gesundheitscheck: Alle Systeme OK")
        elif status == 'warning':
            self.logger.warning(f"Gesundheitscheck: Warnungen - {health_status.get('errors', [])}")
        else:
            self.logger.error(f"Gesundheitscheck: Fehler - {health_status.get('errors', [])}")
    
    def log_configuration(self, config: OracleConfig):
        """Loggt die aktuelle Konfiguration"""
        self.logger.info("Oracle Service Konfiguration:")
        self.logger.info(f"  Datenbank: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
        self.logger.info(f"  Ethereum Node: {config.ETHEREUM_NODE_URL}")
        self.logger.info(f"  Contract Address: {config.CONTRACT_ADDRESS}")
        self.logger.info(f"  DHL Dummy Mode: {config.DHL_USE_DUMMY}")
        self.logger.info(f"  Check Interval: {config.CHECK_INTERVAL}s")
        self.logger.info(f"  Log Level: {config.LOG_LEVEL}")

def create_daily_log_file(base_name: str = "oracle_service") -> str:
    """
    Erstellt einen täglichen Log-Dateinamen
    
    Args:
        base_name: Basis-Name für die Log-Datei
        
    Returns:
        Pfad zur Log-Datei
    """
    today = datetime.now().strftime('%Y%m%d')
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(current_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    return os.path.join(logs_dir, f"{base_name}_{today}.log")
