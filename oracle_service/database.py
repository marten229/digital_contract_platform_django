"""
Datenbank-Interface für den Oracle Service (READ-ONLY)

Dieses Modul stellt eine schreibgeschützte Verbindung zur PostgreSQL-Datenbank der 
Digital Contract Platform her und stellt nur Lesemethoden zum Abrufen von 
Contract-Informationen bereit.

WICHTIG: Der Oracle Service schreibt NICHT in die Datenbank, sondern sendet
alle Updates nur über die Blockchain!
"""

import logging
from sqlalchemy import create_engine, Column, String, Boolean, BigInteger, DateTime, Float, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import List, Optional
from config import OracleConfig

logger = logging.getLogger(__name__)

Base = declarative_base()

class Contract(Base):
    """SQLAlchemy Model für die contractsapp_contract Tabelle"""
    __tablename__ = 'contractsapp_contract'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    status = Column(String(20))
    
    # Ethereum-Adressen
    creator_address = Column(String(42))
    partner_address = Column(String(42))
    
    # Blockchain-Felder
    blockchain_contract_id = Column(BigInteger)
    blockchain_status = Column(String(20))
    
    # DHL Tracking-Felder
    has_dhl_tracking = Column(Boolean, default=False)
    tracking_number = Column(String(50))
    package_status = Column(String(50))
    last_tracking_update = Column(DateTime)
    delivery_oracle_confirmed = Column(Boolean, default=False)
    tracking_hash = Column(String(66))
    
    # Zeitstempel
    uploaded_at = Column(DateTime)
    last_updated = Column(DateTime)

class DatabaseInterface:
    """
    READ-ONLY Interface für die Datenbankoperationen des Oracle Service
    
    Wichtig: Alle Schreiboperationen sind deaktiviert. Der Oracle Service
    liest nur aus der Datenbank und sendet Updates über die Blockchain.
    """
    
    def __init__(self):
        self.config = OracleConfig()
        database_url = self.config.get_database_url()        
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        logger.info(f"Datenbankverbindung initialisiert: {self.config.DB_HOST}:{self.config.DB_PORT}/{self.config.DB_NAME}")
    
    def get_session(self):
        """Erstellt eine neue Datenbank-Session"""
        return self.SessionLocal()
    
    def get_pending_oracle_confirmations(self) -> List[Contract]:
        """
        Holt alle Verträge, die auf Oracle-Bestätigung warten
        
        Da der Oracle Service Read-Only ist, prüfen wir nur die grundlegenden
        Voraussetzungen aus der Datenbank. Die tatsächliche Delivery-Prüfung
        erfolgt über das DHL-Tracking im Oracle Service.
        
        Returns:
            Liste von Contract-Objekten
        """
        with self.get_session() as session:
            contracts = session.query(Contract).filter(
                Contract.has_dhl_tracking == True,
                Contract.tracking_number.isnot(None),
                Contract.delivery_oracle_confirmed == False,
                Contract.blockchain_contract_id.isnot(None),
                # Verträge die mindestens 'package_shipped' sind oder bereits geliefert
                Contract.status.in_(['package_shipped', 'package_delivered'])
            ).all()
            
            # Detach from session so they can be used outside
            for contract in contracts:
                session.expunge(contract)
            
            return contracts
    
    def get_contracts_needing_tracking_update(self) -> List[Contract]:
        """
        Holt alle Verträge mit aktiviertem DHL-Tracking, die noch nicht zugestellt sind
        
        Returns:
            Liste von Contract-Objekten
        """
        with self.get_session() as session:
            contracts = session.query(Contract).filter(
                Contract.has_dhl_tracking == True,
                Contract.tracking_number.isnot(None),
                Contract.status.in_(['package_shipped', 'package_delivered'])
            ).all()            
            # Detach from session
            for contract in contracts:
                session.expunge(contract)
            
            return contracts
    
    def get_contract_by_id(self, contract_id: int) -> Optional[Contract]:
        """
        Holt einen einzelnen Vertrag anhand der ID
        
        Args:
            contract_id: ID des Vertrags
            
        Returns:
            Contract-Objekt oder None
        """
        try:
            with self.get_session() as session:
                contract = session.query(Contract).filter(Contract.id == contract_id).first()
                if contract:
                    session.expunge(contract)
                return contract
        except Exception as e:
            logger.error(f"Fehler beim Abrufen von Contract {contract_id}: {str(e)}")
            return None
    
    def test_connection(self) -> bool:
        """
        Testet die Datenbankverbindung
        
        Returns:
            True wenn Verbindung erfolgreich, False sonst
        """
        try:
            with self.get_session() as session:
                # Einfache Abfrage um Verbindung zu testen
                from sqlalchemy import text
                result = session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Datenbankverbindung fehlgeschlagen: {str(e)}")
            return False
