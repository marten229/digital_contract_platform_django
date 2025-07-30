#!/usr/bin/env python3
"""
Oracle Service Runner

Hauptskript zum Starten des eigenständigen Oracle Service.
Dieses Skript kann in verschiedenen Modi ausgeführt werden:

1. Einzelner Durchlauf: python run_oracle.py --once
2. Kontinuierlicher Betrieb: python run_oracle.py --daemon
3. Gesundheitscheck: python run_oracle.py --health
4. Debug-Modus: python run_oracle.py --debug

Der Service überwacht DHL-Tracking-Updates und sendet Oracle-Bestätigungen
an den Smart Contract der Digital Contract Platform.
"""

import argparse
import sys
import os
import json
from datetime import datetime

# Oracle Service Module importieren
# Füge das aktuelle Verzeichnis zum Python-Pfad hinzu
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Direkte Imports aus dem aktuellen Verzeichnis
from config import OracleConfig
from logging_config import setup_logging, OracleServiceLogger
from oracle import OracleService

def main():
    """Hauptfunktion des Oracle Service Runners"""
    
    # Argument Parser konfigurieren
    parser = argparse.ArgumentParser(
        description="Digital Contract Platform Oracle Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python run_oracle.py --once              # Einmal ausführen
  python run_oracle.py --daemon            # Kontinuierlich laufen
  python run_oracle.py --debug --once      # Debug-Modus, einmal
  python run_oracle.py --health            # Gesundheitscheck
  python run_oracle.py --config            # Konfiguration anzeigen
        """
    )
    
    # Argumente definieren
    parser.add_argument(
        '--once', 
        action='store_true',
        help='Führt nur einen Oracle-Zyklus aus und beendet dann'
    )
    
    parser.add_argument(
        '--daemon', 
        action='store_true',
        help='Läuft kontinuierlich als Daemon-Prozess'
    )
    
    parser.add_argument(
        '--debug', 
        action='store_true',
        help='Debug-Modus: Keine echten Blockchain-Transaktionen'
    )
    
    parser.add_argument(
        '--health', 
        action='store_true',
        help='Führt einen Gesundheitscheck durch und zeigt den Status an'
    )
    
    parser.add_argument(
        '--config', 
        action='store_true',
        help='Zeigt die aktuelle Konfiguration an'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Überschreibt das Log-Level aus der Konfiguration'
    )
    
    parser.add_argument(
        '--log-file',
        help='Überschreibt die Log-Datei aus der Konfiguration'
    )
    
    # Argumente parsen
    args = parser.parse_args()
    
    # Mindestens eine Aktion muss gewählt werden
    if not any([args.once, args.daemon, args.health, args.config]):
        parser.print_help()
        sys.exit(1)
    
    try:
        # Konfiguration laden und validieren
        config = OracleConfig()
        
        # Kommandozeilen-Überschreibungen anwenden
        if args.log_level:
            config.LOG_LEVEL = args.log_level
        if args.log_file:
            config.LOG_FILE = args.log_file
        
        # Konfiguration validieren
        errors, warnings = config.validate()
        
        if errors:
            print("❌ Konfigurationsfehler:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        
        if warnings:
            print("⚠️  Konfigurationswarnungen:")
            for warning in warnings:
                print(f"  - {warning}")
        
        # Logging konfigurieren
        setup_logging(config)
        logger = OracleServiceLogger()
        
        # Konfiguration anzeigen
        if args.config:
            config.print_config()
            if not any([args.once, args.daemon, args.health]):
                return
        
        print(f"\n🔮 Digital Contract Platform Oracle Service")
        print(f"⏰ Gestartet am: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔧 Debug-Modus: {'Ja' if args.debug else 'Nein'}")
        
        # Oracle Service initialisieren
        try:
            oracle_service = OracleService()
            logger.log_configuration(config)
            print(f"✅ Oracle Service erfolgreich initialisiert")
            print(f"🔑 Oracle-Adresse: {oracle_service.key_manager.get_address()}")
            
        except Exception as e:
            print(f"❌ Fehler bei der Initialisierung: {str(e)}")
            logger.log_error("Initialisierung", e)
            sys.exit(1)
        
        # Gesundheitscheck
        if args.health:
            print(f"\n🏥 Führe Gesundheitscheck durch...")
            health = oracle_service.health_check()
            logger.log_health_check(health)
            
            print(f"\n📊 Gesundheitsstatus: {health['status'].upper()}")
            for check, result in health['checks'].items():
                status_icon = "✅" if result == "OK" else "❌" if "ERROR" in result else "ℹ️"
                print(f"  {status_icon} {check}: {result}")
            
            if health['errors']:
                print(f"\n❌ Gefundene Probleme:")
                for error in health['errors']:
                    print(f"  - {error}")
            
            if not any([args.once, args.daemon]):
                return
        
        # Oracle-Service ausführen
        if args.once:
            print(f"\n🔄 Führe einen Oracle-Zyklus aus...")
            results = oracle_service.run_cycle(debug=args.debug)
            
            print(f"\n📈 Zyklus-Ergebnisse:")
            print(f"  🚚 Tracking-Updates: {results['tracking_updates']}")
            print(f"  ✅ Oracle-Bestätigungen: {results['oracle_confirmations_success']}")
            print(f"  ❌ Fehler: {results['oracle_confirmations_errors']}")
            print(f"  ⏱️  Dauer: {results['duration_seconds']:.2f}s")
            
            if results['errors']:
                print(f"\n❌ Aufgetretene Fehler:")
                for error in results['errors']:
                    print(f"  - {error}")
        
        elif args.daemon:
            print(f"\n🔄 Starte kontinuierlichen Oracle-Service...")
            print(f"⏲️  Check-Intervall: {config.CHECK_INTERVAL}s")
            print(f"💡 Zum Beenden: Ctrl+C drücken")
            
            try:
                oracle_service.run_continuous(debug=args.debug)
            except KeyboardInterrupt:
                print(f"\n🛑 Oracle Service durch Benutzer beendet")
            except Exception as e:
                print(f"\n❌ Unerwarteter Fehler: {str(e)}")
                logger.log_error("Kontinuierlicher Betrieb", e)
                sys.exit(1)
        
        print(f"\n✅ Oracle Service beendet")
        
    except KeyboardInterrupt:
        print(f"\n🛑 Oracle Service durch Benutzer unterbrochen")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Kritischer Fehler: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
