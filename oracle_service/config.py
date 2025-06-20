"""
Konfiguration für den Oracle Service

Diese Datei enthält alle Konfigurationseinstellungen für den eigenständigen
Oracle-Dienst. Die Konfiguration wird über Umgebungsvariablen gesteuert.
"""

import os
from dotenv import load_dotenv

# Lade .env Datei aus dem Hauptprojekt
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, 'digital_contract_platform', '.env')
load_dotenv(env_path)

class OracleConfig:
    """Konfigurationsklasse für den Oracle Service"""
    
    # Datenbank-Konfiguration (aus dem Hauptprojekt)
    DB_NAME = os.environ.get('DB_NAME', 'django')
    DB_USER = os.environ.get('DB_USER', 'django')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    
    # Ethereum/Blockchain-Konfiguration
    ETHEREUM_NODE_URL = os.environ.get('ETHEREUM_NODE_URL', 'http://localhost:8545')
    CONTRACT_ADDRESS = os.environ.get('CONTRACT_ADDRESS', '')
    
    # Oracle-Schlüssel-Konfiguration
    ORACLE_KEY_PATH = os.environ.get('ORACLE_KEY_PATH', '')
    ORACLE_KEY_PASSWORD = os.environ.get('ORACLE_KEY_PASSWORD', '')
    ORACLE_PRIVATE_KEY = os.environ.get('ORACLE_PRIVATE_KEY', '')
    
    # DHL API-Konfiguration
    DHL_API_KEY = os.environ.get('DHL_API_KEY', '')
    DHL_API_SECRET = os.environ.get('DHL_API_SECRET', '')
    DHL_API_BASE_URL = os.environ.get('DHL_API_BASE_URL', 'https://api.dhl.com/tracking/v2')
    DHL_USE_DUMMY = os.environ.get('DHL_USE_DUMMY', 'True').lower() in ('true', '1', 'yes')
      # Logging-Konfiguration
    LOG_LEVEL = os.environ.get('ORACLE_LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('ORACLE_LOG_FILE', 'logs/oracle_service.log')
    
    # Service-Konfiguration
    CHECK_INTERVAL = int(os.environ.get('ORACLE_CHECK_INTERVAL', '300'))  # 5 Minuten
    MAX_RETRIES = int(os.environ.get('ORACLE_MAX_RETRIES', '3'))
    RETRY_DELAY = int(os.environ.get('ORACLE_RETRY_DELAY', '60'))  # 1 Minute
    
    @classmethod
    def validate(cls):
        """Validiert die Konfiguration und gibt Warnungen aus"""
        errors = []
        warnings = []
        
        # Pflichtfelder prüfen
        if not cls.CONTRACT_ADDRESS:
            errors.append("CONTRACT_ADDRESS ist nicht gesetzt")
        
        if not cls.ORACLE_KEY_PATH and not cls.ORACLE_PRIVATE_KEY:
            errors.append("Weder ORACLE_KEY_PATH noch ORACLE_PRIVATE_KEY ist gesetzt")
        
        if cls.ORACLE_KEY_PATH and not cls.ORACLE_KEY_PASSWORD:
            errors.append("ORACLE_KEY_PASSWORD ist erforderlich wenn ORACLE_KEY_PATH gesetzt ist")
        
        # DHL-Konfiguration prüfen
        if not cls.DHL_USE_DUMMY and not cls.DHL_API_KEY:
            warnings.append("DHL_API_KEY ist nicht gesetzt, verwende Dummy-Modus")
            cls.DHL_USE_DUMMY = True
        
        # Datenbank-Konfiguration prüfen
        if not cls.DB_PASSWORD:
            errors.append("DB_PASSWORD ist nicht gesetzt")
        
        return errors, warnings
    
    @classmethod
    def get_database_url(cls):
        """Erstellt die Datenbank-URL für SQLAlchemy"""
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
    
    @classmethod
    def print_config(cls):
        """Druckt die aktuelle Konfiguration (ohne sensible Daten)"""
        print(f"Oracle Service Konfiguration:")
        print(f"  Datenbank: {cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}")
        print(f"  Ethereum Node: {cls.ETHEREUM_NODE_URL}")
        print(f"  Contract Address: {cls.CONTRACT_ADDRESS}")
        print(f"  DHL Dummy Mode: {cls.DHL_USE_DUMMY}")
        print(f"  Check Interval: {cls.CHECK_INTERVAL}s")
        print(f"  Log Level: {cls.LOG_LEVEL}")
