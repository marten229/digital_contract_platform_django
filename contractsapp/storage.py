from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os

class ContractStorage(FileSystemStorage):
    """
    Eine spezielle Storage-Klasse für Verträge, die sicherstellt, dass Dateien
    mit der richtigen Vertrags-ID benannt werden.
    """
    
    def __init__(self, *args, **kwargs):
        """Initialisiert den Storage mit dem korrekten Medienverzeichnis."""
        super().__init__(location=settings.MEDIA_ROOT, *args, **kwargs)
    
    def get_available_name(self, name, max_length=None):
        """
        Überschreibt existierende Dateien mit dem gleichen Namen,
        anstatt einen neuen Namen zu generieren.
        """
        # Wenn die Datei existiert, löschen wir sie, damit sie überschrieben wird
        self.delete(name)
        return name
    
    def save_contract_file(self, contract_id, content, is_signed=False):
        """
        Speichert eine Vertragsdatei mit der richtigen Vertrags-ID als Dateinamen.
        
        Args:
            contract_id: Die ID des Vertrags
            content: Der Dateiinhalt (File-ähnliches Objekt)
            is_signed: Ob es sich um eine signierte Version handelt
        
        Returns:
            Der relative Pfad der gespeicherten Datei
        """
        suffix = "_signed" if is_signed else ""
        file_path = f'contracts/contract_{contract_id}{suffix}.pdf'
        
        # Sicherstellen, dass der Zielordner existiert
        dir_path = os.path.dirname(os.path.join(settings.MEDIA_ROOT, file_path))
        os.makedirs(dir_path, exist_ok=True)
        
        # Datei speichern
        self.save(file_path, content)
        
        return file_path