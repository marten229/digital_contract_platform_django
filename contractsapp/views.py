import base64
from io import BytesIO
import os
from PIL import Image
import os
from django.core.files import File
from django.core.files.base import ContentFile
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter

from .forms import ContractForm
from .models import Contract


@login_required
def contract_upload(request):
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save(commit=False)
            # Set the creator's address from the authenticated user
            contract.creator_address = request.user.ethereum_address
            contract.save()
            messages.success(request, 'Vertrag wurde hochgeladen und Ihr Partner wurde eingeladen.')
            return redirect('contract_list')  # Redirect to contract list page
    else:
        # Pre-fill the creator's address with the user's ethereum address
        form = ContractForm(initial={'creator_address': request.user.ethereum_address})
    
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
    Die signierte PDF wird gespeichert und als Download angeboten.
    """
    if request.method == 'POST':
        contract = get_object_or_404(Contract, pk=pk)
        signature_data = request.POST.get('signature')
        
        # Get coordinates from the request (these are now in PDF coordinates)
        try:
            x = float(request.POST.get('x', 400))
            y = float(request.POST.get('y', 100))  # PDF coordinates (bottom-left origin)
            width = float(request.POST.get('width', 150))
            height = float(request.POST.get('height', 50))
            page_num = int(request.POST.get('page', 1)) - 1  # Convert to 0-based index
        except (ValueError, TypeError):
            return HttpResponse("Ungültige Koordinaten.", status=400)
            
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
                
                # Get the original PDF dimensions to ensure correct signature placement
                with open(contract.pdf_file.path, "rb") as f:
                    original_pdf = PdfReader(f)
                    # Use the page we'll be adding the signature to
                    page_num = min(max(0, page_num), len(original_pdf.pages)-1)
                    pdf_page = original_pdf.pages[page_num]
                    # Get PDF page dimensions (width, height in points)
                    pdf_width = float(pdf_page.mediabox.width)
                    pdf_height = float(pdf_page.mediabox.height)
                
                # Create canvas with the same dimensions as the original PDF page
                c = canvas.Canvas(packet, pagesize=(pdf_width, pdf_height))
                
                # Use the PDF coordinates directly
                img = ImageReader(processed_io)
                c.drawImage(img, x, y, width=width, height=height)
                
                c.save()
                packet.seek(0)

                # Das erzeugte Unterschriften-PDF auslesen
                signature_pdf = PdfReader(packet)
                signature_page = signature_pdf.pages[0]

                # Original-PDF laden und die Unterschrift auf der gewählten Seite einfügen
                original_pdf = PdfReader(contract.pdf_file.path)
                output = PdfWriter()
                
                # Make sure the page number is valid
                page_num = min(max(0, page_num), len(original_pdf.pages)-1)

                # Add all pages, merging signature on the selected page
                for i in range(len(original_pdf.pages)):
                    if i == page_num:
                        # Add signature to this page
                        page = original_pdf.pages[i]
                        page.merge_page(signature_page)
                        output.add_page(page)
                    else:
                        # Add unmodified page
                        output.add_page(original_pdf.pages[i])

                # Create a BytesIO object for the response
                output_stream = BytesIO()
                output.write(output_stream)
                output_stream.seek(0)
                
                # FIXED: Instead of trying to replace the file directly, save to a new one
                try:

                    
                    # Create a new file path for the signed version
                    file_name = os.path.basename(contract.pdf_file.name)
                    file_path = os.path.join('contracts', f"signed_{file_name}")
                    
                    # Save the signed version to storage using Django's storage system
                    from django.core.files.storage import default_storage
                    
                    # Save the BytesIO content to the storage
                    default_storage.save(file_path, ContentFile(output_stream.getvalue()))
                    
                    # Update the contract to point to the new file
                    contract.pdf_file.name = file_path
                    contract.save()
                except Exception as e:
                    print(f"Error saving file to storage: {e}")
                    # If updating the file fails, continue with download only
                    pass
                
                # Reset the BytesIO position for response
                output_stream.seek(0)
                
                # Prepare the response with the same content
                response = HttpResponse(output_stream, content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="signed_contract.pdf"'
                return response
                
            except Exception as e:
                # Log the error for debugging
                import traceback
                print(f"Error processing signature: {e}")
                print(traceback.format_exc())
                return HttpResponse(f"Fehler bei der Signaturverarbeitung: {str(e)}", status=400)

    return HttpResponse("Fehler beim Hinzufügen der Unterschrift.", status=400)
