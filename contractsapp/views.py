import base64
from io import BytesIO
import os
from PIL import Image  # Add this import

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter

from .forms import ContractForm
from .models import Contract


def contract_upload(request):
    """
    Zeigt ein Formular zum Hochladen eines Vertrags (PDF) an und speichert diesen.
    Nach erfolgreichem Upload wird zur Detailseite weitergeleitet.
    """
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save()
            return redirect('contract_detail', pk=contract.pk)
    else:
        form = ContractForm()
    return render(request, 'contractsapp/contract_upload.html', {'form': form})


def contract_detail(request, pk):
    """
    Zeigt die Detailansicht eines Vertrags an.
    Hier wird das PDF eingebettet und ein Button zum Hinzufügen der Unterschrift angezeigt.
    """
    contract = get_object_or_404(Contract, pk=pk)
    return render(request, 'contractsapp/contract_detail.html', {'contract': contract})


def add_signature(request, pk):
    """
    Nimmt die per POST übermittelte Unterschrift (als Base64-String) entgegen,
    erstellt ein PDF mit der Unterschrift an einer vorgegebenen Position und
    fügt dieses mit dem Original-PDF zusammen.
    Anschließend wird das resultierende PDF als Download angeboten.
    """
    if request.method == 'POST':
        contract = get_object_or_404(Contract, pk=pk)
        signature_data = request.POST.get('signature')
        if signature_data:
            try:
                # Entferne den Data-URL-Header (z. B. "data:image/png;base64,")
                header, encoded = signature_data.split(',', 1)
                signature_bytes = base64.b64decode(encoded)
            except Exception:
                return HttpResponse("Ungültige Signaturdaten.", status=400)

            try:
                # Convert to PIL Image for better handling
                signature_image_io = BytesIO(signature_bytes)
                pil_image = Image.open(signature_image_io)
                
                # Convert to RGB if has transparency (RGBA)
                if pil_image.mode == 'RGBA':
                    # Create white background
                    background = Image.new('RGB', pil_image.size, (255, 255, 255))
                    # Paste the image on the background using the alpha channel
                    background.paste(pil_image, (0, 0), pil_image)
                    pil_image = background
                
                # Save processed image to memory
                processed_io = BytesIO()
                pil_image.save(processed_io, format='PNG')
                processed_io.seek(0)
                
                # Erstelle ein PDF, das die Unterschrift enthält.
                packet = BytesIO()
                c = canvas.Canvas(packet, pagesize=letter)
                # Position und Größe der Unterschrift anpassen (hier: rechts unten)
                x = 400  # x-Position
                y = 100  # y-Position
                width = 150  # Breite der Unterschrift
                height = 50  # Höhe der Unterschrift
                
                # Use the processed image
                img = ImageReader(processed_io)
                c.drawImage(img, x, y, width=width, height=height)
                
                c.save()
                packet.seek(0)

                # Das erzeugte Unterschriften-PDF auslesen
                signature_pdf = PdfReader(packet)
                signature_page = signature_pdf.pages[0]

                # Original-PDF laden und die Unterschrift auf der ersten Seite einfügen
                with open(contract.pdf_file.path, "rb") as f:
                    original_pdf = PdfReader(f)
                    output = PdfWriter()

                    # Unterschrift auf der ersten Seite einfügen
                    page = original_pdf.pages[0]
                    page.merge_page(signature_page)
                    output.add_page(page)

                    # Weitere Seiten (falls vorhanden) unverändert hinzufügen
                    for i in range(1, len(original_pdf.pages)):
                        output.add_page(original_pdf.pages[i])

                    output_stream = BytesIO()
                    output.write(output_stream)
                    output_stream.seek(0)

                response = HttpResponse(output_stream, content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="signed_contract.pdf"'
                return response
                
            except Exception as e:
                # Log the error for debugging
                print(f"Error processing signature: {e}")
                return HttpResponse(f"Fehler bei der Signaturverarbeitung: {str(e)}", status=400)

    return HttpResponse("Fehler beim Hinzufügen der Unterschrift.", status=400)
