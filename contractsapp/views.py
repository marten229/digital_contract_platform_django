from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse
from django.conf import settings
from django.core.mail import get_connection
from django.core.mail import EmailMultiAlternatives

import base64
from io import BytesIO
import os
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
from django.core.files.base import ContentFile

from .forms import ContractForm
from .models import Contract


@login_required
def contract_list(request):
    user_contracts = Contract.objects.filter(creator_address=request.user.ethereum_address)
    
    pending_contracts = user_contracts.filter(status='pending')
    accepted_contracts = user_contracts.filter(status='accepted')
    completed_contracts = user_contracts.filter(status='completed')
    
    context = {
        'pending_contracts': pending_contracts,
        'accepted_contracts': accepted_contracts,
        'completed_contracts': completed_contracts,
        'all_contracts': user_contracts,
    }
    
    return render(request, 'contractsapp/contract_list.html', context)


@login_required
def contract_upload(request):
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.creator_address = request.user.ethereum_address
            # Save the contract first, but mark it as not configured
            contract.is_configured = False
            contract.save()
            
            # Redirect to the configuration page instead of sending email immediately
            return redirect('contract_configuration', pk=contract.pk)
    else:
        form = ContractForm(initial={'creator_address': request.user.ethereum_address})
    
    return render(request, 'contractsapp/contract_upload.html', {'form': form})


@login_required
def contract_configuration(request, pk):
    """Display the contract configuration page to set signature positions"""
    contract = get_object_or_404(Contract, pk=pk, creator_address=request.user.ethereum_address)
    
    # If the contract is already configured, redirect to the detail page
    if contract.is_configured:
        messages.info(request, 'Dieser Vertrag wurde bereits konfiguriert.')
        return redirect('contract_detail', pk=contract.pk)
    
    return render(request, 'contractsapp/contract_configuration.html', {'contract': contract})


@login_required
def finish_contract_configuration(request, pk):
    """Process the final configuration and notify the partner"""
    if request.method != 'POST':
        return redirect('contract_configuration', pk=pk)
    
    contract = get_object_or_404(Contract, pk=pk, creator_address=request.user.ethereum_address)
    
    # If the contract is already configured, redirect to the detail page
    if contract.is_configured:
        messages.info(request, 'Dieser Vertrag wurde bereits konfiguriert.')
        return redirect('contract_detail', pk=contract.pk)
    
    # Get signature positions from form data
    try:
        contract.creator_signature_x = float(request.POST.get('creator_signature_x'))
        contract.creator_signature_y = float(request.POST.get('creator_signature_y'))
        contract.creator_signature_width = float(request.POST.get('creator_signature_width'))
        contract.creator_signature_height = float(request.POST.get('creator_signature_height'))
        contract.creator_signature_page = int(request.POST.get('creator_signature_page'))
        
        contract.partner_signature_x = float(request.POST.get('partner_signature_x'))
        contract.partner_signature_y = float(request.POST.get('partner_signature_y'))
        contract.partner_signature_width = float(request.POST.get('partner_signature_width'))
        contract.partner_signature_height = float(request.POST.get('partner_signature_height'))
        contract.partner_signature_page = int(request.POST.get('partner_signature_page'))
    except (ValueError, TypeError):
        messages.error(request, 'Ungültige Signaturpositionen. Bitte versuchen Sie es erneut.')
        return redirect('contract_configuration', pk=pk)
    
    # Mark contract as configured
    contract.is_configured = True
    contract.save()
    
    # Now send email to partner
    try:
        contract_url = request.build_absolute_uri(
            reverse('contract_signing', args=[contract.pk])
        )
        
        context = {
            'partner_name': contract.partner_name,
            'creator_name': request.user.get_full_name() or request.user.username,
            'contract_title': contract.title,
            'contract_url': contract_url,
            'site_name': 'DigiContract'
        }
        
        html_message = render_to_string('contractsapp/email/contract_invitation.html', context)
        plain_message = strip_tags(html_message)
        
        connection = get_connection(fail_silently=False)
        connection.open()
        
        email = EmailMultiAlternatives(
            subject=f'Einladung zur Vertragsunterzeichnung: {contract.title}',
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[contract.partner_email],
            connection=connection
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        
        connection.close()
        
        messages.success(request, 'Vertrag wurde erfolgreich konfiguriert und Ihr Partner wurde per E-Mail eingeladen.')
    except Exception as e:
        messages.warning(request, f'Vertrag wurde konfiguriert, aber die Einladungs-E-Mail konnte nicht gesendet werden. Fehler: {str(e)}')
        print(f"E-Mail-Fehler: {e}")
    
    # Check if we should redirect to signing page
    if request.POST.get('redirect_to_signing') == 'true':
        return redirect('contract_signing', pk=contract.pk)
    
    return redirect('contract_list')


def contract_detail(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    return render(request, 'contractsapp/contract_detail.html', {'contract': contract})


def contract_signing(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    return render(request, 'contractsapp/contract_signing.html', {'contract': contract})


def add_signature(request, pk):
    if request.method == 'POST':
        contract = get_object_or_404(Contract, pk=pk)
        signature_data = request.POST.get('signature')
        
        try:
            x = float(request.POST.get('x', 400))
            y = float(request.POST.get('y', 100))
            width = float(request.POST.get('width', 150))
            height = float(request.POST.get('height', 50))
            page_num = int(request.POST.get('page', 1)) - 1
        except (ValueError, TypeError):
            return HttpResponse("Ungültige Koordinaten.", status=400)
            
        if signature_data:
            try:
                header, encoded = signature_data.split(',', 1)
                signature_bytes = base64.b64decode(encoded)
            except Exception:
                return HttpResponse("Ungültige Signaturdaten.", status=400)

            try:
                signature_image_io = BytesIO(signature_bytes)
                pil_image = Image.open(signature_image_io)
                
                if pil_image.mode == 'RGBA':
                    background = Image.new('RGB', pil_image.size, (255, 255, 255))
                    background.paste(pil_image, (0, 0), pil_image)
                    pil_image = background
                
                processed_io = BytesIO()
                pil_image.save(processed_io, format='PNG')
                processed_io.seek(0)
                
                packet = BytesIO()
                
                with open(contract.pdf_file.path, "rb") as f:
                    original_pdf = PdfReader(f)
                    page_num = min(max(0, page_num), len(original_pdf.pages)-1)
                    pdf_page = original_pdf.pages[page_num]
                    pdf_width = float(pdf_page.mediabox.width)
                    pdf_height = float(pdf_page.mediabox.height)
                
                c = canvas.Canvas(packet, pagesize=(pdf_width, pdf_height))
                
                img = ImageReader(processed_io)
                c.drawImage(img, x, y, width=width, height=height)
                
                c.save()
                packet.seek(0)

                signature_pdf = PdfReader(packet)
                signature_page = signature_pdf.pages[0]

                original_pdf = PdfReader(contract.pdf_file.path)
                output = PdfWriter()
                
                page_num = min(max(0, page_num), len(original_pdf.pages)-1)

                for i in range(len(original_pdf.pages)):
                    if i == page_num:
                        page = original_pdf.pages[i]
                        page.merge_page(signature_page)
                        output.add_page(page)
                    else:
                        output.add_page(original_pdf.pages[i])

                output_stream = BytesIO()
                output.write(output_stream)
                output_stream.seek(0)
                
                try:
                    file_name = os.path.basename(contract.pdf_file.name)
                    file_path = os.path.join('contracts', f"signed_{file_name}")
                    
                    from django.core.files.storage import default_storage
                    
                    default_storage.save(file_path, ContentFile(output_stream.getvalue()))
                    
                    contract.pdf_file.name = file_path
                    contract.save()
                except Exception as e:
                    print(f"Error saving file to storage: {e}")
                    pass
                
                output_stream.seek(0)
                
                response = HttpResponse(output_stream, content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="signed_contract.pdf"'
                return response
                
            except Exception as e:
                import traceback
                print(f"Error processing signature: {e}")
                print(traceback.format_exc())
                return HttpResponse(f"Fehler bei der Signaturverarbeitung: {str(e)}", status=400)

    return HttpResponse("Fehler beim Hinzufügen der Unterschrift.", status=400)
