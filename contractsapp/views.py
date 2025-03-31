from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse
from django.conf import settings
from django.db.models import Q

import base64
from io import BytesIO
import os
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
from django.core.files.base import ContentFile

from .forms import ContractForm
from .models import Contract, ContractActivity
from .services import MailjetService


@login_required
def contract_list(request):
    # Alle Verträge, bei denen der Benutzer der Ersteller ist
    creator_contracts = Contract.objects.filter(creator_address=request.user.ethereum_address)
    
    # Alle Verträge, bei denen der Benutzer der Partner ist
    partner_contracts = Contract.objects.filter(partner_address=request.user.ethereum_address)
    
    # Kategorisieren der Verträge nach Status
    pending_contracts = creator_contracts.filter(
        Q(status='uploaded') | 
        Q(status='configured') | 
        Q(status='invitation_sent') |
        Q(status='viewed_by_partner') |
        Q(status='partner_verified')
    )
    
    in_progress_contracts = creator_contracts.filter(
        Q(status='signed_by_creator') | 
        Q(status='signed_by_partner')
    )
    
    completed_contracts = creator_contracts.filter(status='completed')
    rejected_contracts = creator_contracts.filter(status='rejected')
    
    # Verträge, bei denen der Benutzer der Partner ist
    pending_partner_contracts = partner_contracts.filter(
        ~Q(status='completed') & 
        ~Q(status='rejected')
    )
    
    completed_partner_contracts = partner_contracts.filter(status='completed')
    
    # Aktivitäten für die Dashboard-Anzeige - beschränkt auf die letzten 10
    all_user_contracts = creator_contracts | partner_contracts
    recent_activities = ContractActivity.objects.filter(
        contract__in=all_user_contracts
    ).order_by('-timestamp')[:10]
    
    context = {
        'pending_contracts': pending_contracts,
        'in_progress_contracts': in_progress_contracts,
        'completed_contracts': completed_contracts,
        'rejected_contracts': rejected_contracts,
        'all_contracts': creator_contracts,
        'pending_partner_contracts': pending_partner_contracts,
        'completed_partner_contracts': completed_partner_contracts,
        'recent_activities': recent_activities,
    }
    
    return render(request, 'contractsapp/contract_list.html', context)


@login_required
def contract_upload(request):
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.creator_address = request.user.ethereum_address
            # Status korrekt setzen
            contract.status = 'uploaded'
            contract.is_configured = False
            contract.save()
            
            # Aktivität protokollieren
            ContractActivity.log(
                contract=contract,
                action='upload',
                user=request.user,
                user_role='creator',
                details=f"Vertrag '{contract.title}' wurde hochgeladen"
            )
            
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
    
    # Aktivität protokollieren, wenn die Konfigurationsseite zum ersten Mal geöffnet wird
    if contract.status == 'uploaded':
        ContractActivity.log(
            contract=contract,
            action='configure',
            user=request.user,
            user_role='creator',
            details="Konfiguration des Vertrags begonnen"
        )
    
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
    
    # Mark contract as configured and update status
    contract.is_configured = True
    contract.status = 'configured'
    contract.save()
    
    # Aktivität protokollieren
    ContractActivity.log(
        contract=contract,
        action='configure',
        user=request.user,
        user_role='creator',
        details="Vertragskonfiguration abgeschlossen"
    )
    
    # Now send email to partner using Mailjet
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
        
        email_sent = MailjetService.send_email(
            to_email=contract.partner_email,
            to_name=contract.partner_name,
            subject=f'Einladung zur Vertragsunterzeichnung: {contract.title}',
            template_name='contractsapp/email/contract_invitation.html',
            context=context
        )
        
        if email_sent:
            # Status aktualisieren
            contract.status = 'invitation_sent'
            contract.save()
            
            # Aktivität protokollieren
            ContractActivity.log(
                contract=contract,
                action='send_invitation',
                user=request.user,
                user_role='creator',
                details=f"Einladung an {contract.partner_email} gesendet"
            )
            
            messages.success(request, 'Vertrag wurde erfolgreich konfiguriert und Ihr Partner wurde per E-Mail eingeladen.')
        else:
            messages.warning(request, 'Vertrag wurde konfiguriert, aber die Einladungs-E-Mail konnte nicht gesendet werden.')
    except Exception as e:
        messages.warning(request, f'Vertrag wurde konfiguriert, aber die Einladungs-E-Mail konnte nicht gesendet werden. Fehler: {str(e)}')
        print(f"E-Mail-Fehler: {e}")
    
    # Check if we should redirect to signing page
    if request.POST.get('redirect_to_signing') == 'true':
        return redirect('contract_signing', pk=contract.pk)
    
    return redirect('contract_list')


def contract_detail(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    
    # Aktivitäten dieses Vertrags für die Detailansicht laden
    activities = contract.activities.all()[:20]  # Die letzten 20 Aktivitäten
    
    # Wenn der Benutzer angemeldet ist und nicht der Ersteller, protokolliere die Ansicht
    if (request.user.is_authenticated and 
        hasattr(request.user, 'ethereum_address') and 
        request.user.ethereum_address != contract.creator_address):
        
        # Status von viewed_by_partner nur setzen, wenn der Partner den Vertrag zum ersten Mal ansieht
        is_partner = contract.partner_address == request.user.ethereum_address
        if is_partner and contract.status == 'invitation_sent':
            contract.status = 'viewed_by_partner'
            contract.save()
            
            # Aktivität protokollieren
            ContractActivity.log(
                contract=contract,
                action='view',
                user=request.user,
                details="Partner hat den Vertrag angesehen"
            )
    
    return render(request, 'contractsapp/contract_detail.html', {
        'contract': contract,
        'activities': activities
    })


def contract_signing(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    
    # Überprüfen, ob der aktuelle Benutzer der Ersteller des Vertrags ist
    is_creator = request.user.is_authenticated and request.user.ethereum_address == contract.creator_address
    is_partner = request.user.is_authenticated and request.user.ethereum_address == contract.partner_address
    
    # Aktivität protokollieren
    if request.user.is_authenticated:
        if is_creator:
            ContractActivity.log(
                contract=contract,
                action='view',
                user=request.user,
                user_role='creator',
                details="Ersteller hat die Signierseite geöffnet"
            )
        elif is_partner:
            # Wenn der Partner die Signierseite besucht, aktualisieren wir den Status
            if contract.status in ['invitation_sent', 'viewed_by_partner']:
                contract.status = 'viewed_by_partner'
                contract.save()
                
                ContractActivity.log(
                    contract=contract,
                    action='view',
                    user=request.user,
                    user_role='partner',
                    details="Partner hat die Signierseite geöffnet"
                )
    
    return render(request, 'contractsapp/contract_signing.html', {
        'contract': contract,
        'is_creator': is_creator,
        'is_partner': is_partner
    })


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
                
                # Bestimmen, ob der Vertrag vom Ersteller oder vom Partner signiert wird
                is_creator = (request.user.is_authenticated and 
                               request.user.ethereum_address == contract.creator_address)
                is_partner = (request.user.is_authenticated and 
                               request.user.ethereum_address == contract.partner_address)
                
                # Je nach unterzeichnender Partei den Status aktualisieren
                if is_creator:
                    if contract.status in ['configured', 'invitation_sent', 'viewed_by_partner', 'partner_verified']:
                        contract.status = 'signed_by_creator'
                        action_type = 'sign_creator'
                        details = "Vertrag vom Ersteller unterzeichnet"
                    elif contract.status == 'signed_by_partner':
                        contract.status = 'completed'
                        action_type = 'complete'
                        details = "Vertrag vollständig unterzeichnet (Ersteller-Signatur)"
                elif is_partner:
                    if contract.status in ['invitation_sent', 'viewed_by_partner', 'partner_verified']:
                        contract.status = 'signed_by_partner'
                        action_type = 'sign_partner'
                        details = "Vertrag vom Partner unterzeichnet"
                    elif contract.status == 'signed_by_creator':
                        contract.status = 'completed'
                        action_type = 'complete'
                        details = "Vertrag vollständig unterzeichnet (Partner-Signatur)"
                else:
                    action_type = 'other'
                    details = "Unbekannte Partei hat den Vertrag unterzeichnet"
                
                try:
                    # Die PDF-Datei mit der Vertrags-ID benennen
                    from .storage import ContractStorage
                    contract_storage = ContractStorage()
                    
                    # Direkt unsere spezielle Storage-Klasse verwenden
                    file_path = contract_storage.save_contract_file(
                        contract.pk, 
                        ContentFile(output_stream.getvalue()), 
                        is_signed=True
                    )
                    
                    # Update des Dateinamens im Contract-Objekt
                    contract.pdf_file.name = file_path
                    contract.save()
                    
                    # Aktivität protokollieren
                    if request.user.is_authenticated:
                        ContractActivity.log(
                            contract=contract,
                            action=action_type,
                            user=request.user,
                            details=details
                        )
                    
                    print(f"Signierte PDF für Vertrag {contract.pk} gespeichert als: {file_path}")
                except Exception as e:
                    print(f"Error saving file to storage: {e}")
                    import traceback
                    print(traceback.format_exc())
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


def verify_partner(request, pk):
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})
    
    contract = get_object_or_404(Contract, pk=pk)
    
    if contract.partner_address:
        return JsonResponse({'success': True})
    
    partner_name = request.POST.get('partner_name', '').strip()
    partner_email = request.POST.get('partner_email', '').strip()
    partner_address = request.POST.get('partner_address', '').strip()
    
    errors = {}
    
    if not partner_name:
        errors['name'] = 'Bitte geben Sie Ihren Namen ein.'
    elif partner_name != contract.partner_name:
        errors['name'] = 'Der Name stimmt nicht mit dem hinterlegten Namen überein.'
        
    if not partner_email:
        errors['email'] = 'Bitte geben Sie Ihre E-Mail-Adresse ein.'
    elif partner_email != contract.partner_email:
        errors['email'] = 'Die E-Mail-Adresse stimmt nicht mit der hinterlegten Adresse überein.'
         
    if not partner_address:
        errors['address'] = 'Bitte geben Sie Ihre Ethereum Wallet-Adresse ein.'
    elif not partner_address.startswith('0x') or len(partner_address) != 42:
        errors['address'] = 'Bitte geben Sie eine gültige Ethereum-Adresse ein (beginnt mit 0x und hat 42 Zeichen).'
    
    if errors:
        return JsonResponse({'success': False, 'errors': errors})
    
    # Partner-Adresse speichern und Status aktualisieren
    contract.partner_address = partner_address
    contract.status = 'partner_verified'
    contract.save()
    
    # Aktivität protokollieren
    if request.user.is_authenticated:
        ContractActivity.log(
            contract=contract,
            action='verify_partner',
            user=request.user,
            user_role='partner',
            details=f"Partner hat sich verifiziert: {partner_address}"
        )
    
    return JsonResponse({'success': True})
