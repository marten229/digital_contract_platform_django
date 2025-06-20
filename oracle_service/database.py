"""
Datenbank-Interface für den Oracle Service

Dieses Modul stellt eine Verbindung zur PostgreSQL-Datenbank der 
Digital Contract Platform her und stellt Methoden zum Abrufen 
und Aktualisieren von Contract-Informationen bereit.
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
    """Interface für die Datenbankoperationen des Oracle Service"""
    
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
        
        Returns:
            Liste von Contract-Objekten
        """
        with self.get_session() as session:
            contracts = session.query(Contract).filter(
                Contract.has_dhl_tracking == True,
                Contract.tracking_number.isnot(None),
                Contract.status == 'package_delivered',
                Contract.delivery_oracle_confirmed == False,
                Contract.blockchain_contract_id.isnot(None)
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
    
    def update_contract_oracle_confirmation(self, contract_id: int, confirmed: bool = True) -> bool:
        """
        Markiert einen Vertrag als Oracle-bestätigt
        
        Args:
            contract_id: ID des Vertrags
            confirmed: Bestätigungsstatus
            
        Returns:
            True wenn erfolgreich, False sonst
        """
        try:
            with self.get_session() as session:
                contract = session.query(Contract).filter(Contract.id == contract_id).first()
                if contract:
                    contract.delivery_oracle_confirmed = confirmed
                    session.commit()
                    logger.info(f"Contract {contract_id} Oracle-Bestätigung auf {confirmed} gesetzt")
                    return True
                else:
                    logger.warning(f"Contract {contract_id} nicht gefunden")
                    return False
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Oracle-Bestätigung für Contract {contract_id}: {str(e)}")
            return False
    
    def update_tracking_status(self, contract_id: int, status: str, last_update: datetime = None) -> bool:
        """
        Aktualisiert den Tracking-Status eines Vertrags
        
        Args:
            contract_id: ID des Vertrags
            status: Neuer Tracking-Status
            last_update: Zeitpunkt der letzten Aktualisierung
            
        Returns:
            True wenn erfolgreich, False sonst
        """
        try:
            with self.get_session() as session:
                contract = session.query(Contract).filter(Contract.id == contract_id).first()
                if contract:
                    old_status = contract.package_status
                    contract.package_status = status
                    contract.last_tracking_update = last_update or datetime.now()
                    
                    # Update overall contract status if package is delivered
                    if status == 'delivered' and contract.status != 'package_delivered':
                        contract.status = 'package_delivered'
                        logger.info(f"Contract {contract_id} Status auf 'package_delivered' gesetzt")
                    
                    session.commit()
                    
                    if old_status != status:
                        logger.info(f"Contract {contract_id} Tracking-Status: {old_status} -> {status}")
                    
                    return True
                else:
                    logger.warning(f"Contract {contract_id} nicht gefunden")
                    return False
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Tracking-Status für Contract {contract_id}: {str(e)}")
            return False
    
    def set_tracking_hash(self, contract_id: int, tracking_hash: str) -> bool:
        """
        Setzt den Tracking-Hash für einen Vertrag
        
        Args:
            contract_id: ID des Vertrags
            tracking_hash: Der generierte Tracking-Hash
            
        Returns:
            True wenn erfolgreich, False sonst
        """
        try:
            with self.get_session() as session:
                contract = session.query(Contract).filter(Contract.id == contract_id).first()
                if contract:
                    contract.tracking_hash = tracking_hash
                    session.commit()
                    logger.info(f"Tracking-Hash für Contract {contract_id} gesetzt")
                    return True
                else:
                    logger.warning(f"Contract {contract_id} nicht gefunden")
                    return False
        except Exception as e:
            logger.error(f"Fehler beim Setzen des Tracking-Hash für Contract {contract_id}: {str(e)}")
            return False
    
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
