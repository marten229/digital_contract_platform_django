"""
Setup-Skript für den Oracle-User und die zugehörigen Ethereum-Schlüssel

Dieses Skript erstellt:
1. Einen Oracle-Benutzer in Django
2. Eine Oracle-Benutzergruppe mit entsprechenden Berechtigungen
3. Ein Ethereum-Schlüsselpaar für automatische Transaktionen
"""

import os
import sys
import django
import getpass

# Django-Umgebung einrichten
# Wir müssen den Hauptordner (digital_contract_platform) zum Python-Path hinzufügen
# Aktueller Pfad: [projektwurzel]/contractsapp/scripts/setup_oracle.py
# Wir gehen zwei Ordner nach oben (zur Projektwurzel)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'digital_contract_platform.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from oracle_service.oracle_key_manager import OracleKeyManager

User = get_user_model()

def setup_oracle():
    """Richtet den Oracle-User und die Schlüssel ein"""
    print("\n===== Oracle-User und -Schlüssel Setup =====\n")
    
    # 1. Oracle-Gruppe erstellen oder abrufen
    oracle_group, created = Group.objects.get_or_create(name='Oracle')
    if created:
        print("✓ Oracle-Gruppe wurde erstellt")
    else:
        print("ℹ Oracle-Gruppe existiert bereits")
    
    # 2. Oracle-Benutzer erstellen
    print("\n----- Oracle-Benutzer erstellen -----")
    username = input("Benutzername für Oracle (default: oracle_service): ") or "oracle_service"
    email = input("E-Mail für Oracle (default: oracle@example.com): ") or "oracle@example.com"
    
    # Prüfe, ob Benutzer bereits existiert
    try:
        oracle_user = User.objects.get(username=username)
        print(f"ℹ Benutzer {username} existiert bereits")
        update_user = input("Benutzer aktualisieren? (j/n): ").lower() == 'j'
        
        if not update_user:
            print("ℹ Benutzereinstellungen werden nicht geändert")
        else:
            # Passwort aktualisieren
            password = getpass.getpass("Neues Passwort für Oracle-User: ")
            oracle_user.set_password(password)
            oracle_user.email = email
            oracle_user.save()
            print("✓ Benutzer wurde aktualisiert")
    except User.DoesNotExist:
        # Benutzer erstellen
        password = getpass.getpass("Passwort für Oracle-User: ")
        oracle_user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        print(f"✓ Benutzer {username} wurde erstellt")
    
    # Oracle-Gruppe zuweisen
    if oracle_group not in oracle_user.groups.all():
        oracle_user.groups.add(oracle_group)
        print("✓ Benutzer zur Oracle-Gruppe hinzugefügt")
    
    # 3. Ethereum-Schlüssel erstellen
    print("\n----- Ethereum-Schlüssel für Oracle erstellen -----")
    print("Dieser Schlüssel wird für automatische Blockchain-Transaktionen verwendet.")
    
    create_key = input("Neuen Ethereum-Schlüssel erstellen? (j/n): ").lower() == 'j'
    
    if create_key:
        key_password = getpass.getpass("Passwort für die Keystore-Verschlüsselung: ")
        key_confirm = getpass.getpass("Passwort bestätigen: ")
        
        if key_password != key_confirm:
            print("❌ Passwörter stimmen nicht überein!")
            return
          # Wir erstellen den keys-Ordner im Projektstammverzeichnis
        key_dir = os.path.join(project_root, 'keys')
        os.makedirs(key_dir, exist_ok=True)
        
        key_path = os.path.join(key_dir, f'oracle_{username}.json')
        
        # Schlüssel generieren
        key_data = OracleKeyManager.generate_keystore(key_password, key_path)
        
        print(f"\n✓ Ethereum-Schlüssel wurde erstellt und gespeichert unter: {key_path}")
        print(f"✓ Oracle Ethereum-Adresse: {key_data['address']}")
        
        # Adresse dem Benutzer zuweisen
        oracle_user.ethereum_address = key_data['address']
        oracle_user.save()
        
        print("\n⚠ WICHTIG: Stellen Sie sicher, dass die folgenden Umgebungsvariablen gesetzt sind:")
        print(f"  ORACLE_KEY_PATH={key_path}")
        print(f"  ORACLE_KEY_PASSWORD=********")
    else:
        print("\nℹ Es wird kein neuer Schlüssel erstellt.")
        
        # Optional: bestehende Adresse dem Benutzer zuweisen
        addr = input("Bestehende Ethereum-Adresse für Oracle (optional): ")
        if addr and addr.startswith('0x'):
            oracle_user.ethereum_address = addr
            oracle_user.save()
            print(f"✓ Ethereum-Adresse {addr} wurde dem Oracle-Benutzer zugewiesen")
    
    print("\n===== Oracle Setup abgeschlossen =====")
    print(f"\nOracle-User: {username}")
    print(f"Oracle Ethereum-Adresse: {oracle_user.ethereum_address}")
    print("\nDieser Benutzer kann nun für automatische Oracle-Bestätigungen verwendet werden.")
    
    # Anweisungen zum Testen
    print("\n----- Nächste Schritte -----")
    print("1. Stellen Sie sicher, dass die erforderlichen Umgebungsvariablen gesetzt sind")
    print("2. Führen Sie einen Testlauf des Tracking-Skripts im Debug-Modus aus:")
    print("   python scripts/update_tracking.py --debug")
    print("3. Wenn alles funktioniert, richten Sie einen Cronjob oder Scheduled Task ein")
    

if __name__ == "__main__":
    setup_oracle()
