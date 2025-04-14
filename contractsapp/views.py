from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.db.models import Q

import traceback
import base64
from io import BytesIO
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
from django.core.files.base import ContentFile
import json

from .forms import ContractForm
from .models import Contract, ContractActivity
from .blockchain import BlockchainService
from .storage import ContractStorage


@login_required
def contract_list(request):
    # Ethereum-Adresse in Kleinbuchstaben für den Vergleich mit der DB
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
    
    # Verträge anhand der Ethereum-Adressen filtern
    creator_contracts = Contract.objects.filter(creator_address=user_eth_address)
    
    partner_contracts = Contract.objects.filter(partner_address=user_eth_address)
    
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
    
    # Filter für Blockchain-Verträge hinzufügen
    blockchain_contracts = creator_contracts.filter(status='blockchain_published')
    blockchain_partner_contracts = partner_contracts.filter(status='blockchain_published')
    
    # Pending Partner Contracts: Contracts where the partner still needs to act (view, verify, sign)
    pending_partner_contracts = partner_contracts.filter(
        Q(status='invitation_sent') | 
        Q(status='viewed_by_partner') | 
        Q(status='partner_verified') | 
        Q(status='configured') # Include configured if partner can sign immediately
        # EXCLUDE signed_by_partner from this list
    )

    # Contracts signed by partner but not yet completed/published
    signed_by_partner_contracts = partner_contracts.filter(status='signed_by_partner')

    completed_partner_contracts = partner_contracts.filter(status='completed')

    # Fetch recent activities
    all_contract_pks = list(creator_contracts.values_list('pk', flat=True)) + \
                       list(partner_contracts.values_list('pk', flat=True))
    recent_activities = ContractActivity.objects.filter(
        contract_id__in=set(all_contract_pks) # Use set for efficiency
    ).select_related('contract').order_by('-timestamp')[:10]

    # Update blockchain status for relevant contracts
    # It's generally better to do this periodically or via a background task,
    # but for now, we'll update the ones being displayed.
    contracts_to_update = creator_contracts.filter(blockchain_contract_id__isnull=False) | \
                          partner_contracts.filter(blockchain_contract_id__isnull=False)
    for contract in contracts_to_update:
        contract.update_blockchain_status() # Assuming this method saves the changes

    context = {
        # Pass the QuerySets directly, not lists of dictionaries
        'pending_contracts': pending_contracts,
        'in_progress_contracts': in_progress_contracts,
        'completed_contracts': completed_contracts,
        'rejected_contracts': rejected_contracts,
        'all_contracts': creator_contracts | partner_contracts,
        'pending_partner_contracts': pending_partner_contracts,
        'signed_by_partner_contracts': signed_by_partner_contracts, # Add this new context variable
        'completed_partner_contracts': completed_partner_contracts,
        'blockchain_contracts': blockchain_contracts,
        'blockchain_partner_contracts': blockchain_partner_contracts,
        'recent_activities': recent_activities,
    }

    return render(request, 'contractsapp/contract_list.html', context)


@login_required
def contract_upload(request):      
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save(commit=False)
            # Setze nur die Ethereum-Adresse des Erstellers, nicht die FK-Beziehung
            # (Die creator FK-Spalte existiert noch nicht in der Datenbank)
            contract.creator_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
            # Setze den Status
            contract.status = 'uploaded'
            contract.is_configured = False
            
            # Explicitly set creator to None to avoid the database error
            contract.creator = None
            contract.partner = None
            
            # Now we can safely save
            contract.save()
            
            blockchain_service = BlockchainService()
            if contract.pdf_file:
                try:
                    contract.pdf_hash = blockchain_service.calculate_pdf_hash(contract.pdf_file)
                    contract.save(update_fields=['pdf_hash'])
                except Exception as e:
                    messages.warning(request, f"Fehler beim Berechnen des PDF-Hashes: {e}")
            
            ContractActivity.log(
                contract=contract,
                action='upload',
                user=request.user,
                user_role='creator',
                details=f"Vertrag '{contract.title}' wurde hochgeladen"
            )
            
            return redirect('contract_configuration', pk=contract.pk)
    else:
        form = ContractForm()
    
    return render(request, 'contractsapp/contract_upload.html', {'form': form})


@login_required
def contract_configuration(request, pk):
    """Display the contract configuration page to set signature positions"""
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
    contract = get_object_or_404(Contract, pk=pk, creator_address=user_eth_address)
    
    if contract.is_configured:
        messages.info(request, 'Dieser Vertrag wurde bereits konfiguriert.')
        return redirect('contract_detail', pk=contract.pk)
    
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
    
    # Ethereum-Adresse in Kleinbuchstaben für den Vergleich mit der DB
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
    
    contract = get_object_or_404(Contract, pk=pk, creator_address=user_eth_address)
    
    if contract.is_configured:
        messages.info(request, 'Dieser Vertrag wurde bereits konfiguriert.')
        return redirect('contract_detail', pk=contract.pk)
    
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
    
    contract.is_configured = True
    contract.status = 'configured'
    contract.save()
    
    ContractActivity.log(
        contract=contract,
        action='configure',
        user=request.user,
        user_role='creator',
        details="Vertragskonfiguration abgeschlossen"
    )
      # Da alle Partner registrierte Benutzer sind, ist keine E-Mail-Benachrichtigung mehr notwendig
    # Der Status wird direkt auf 'invitation_sent' gesetzt, um den Workflow beizubehalten
    contract.status = 'invitation_sent'
    contract.save()
      # Verwende die Ethereum-Adresse des Partners anstelle von username, da partner-Objekt null sein kann
    partner_identifier = contract.partner_address
    if contract.partner and hasattr(contract.partner, 'username'):
        partner_identifier = contract.partner.username
        
    ContractActivity.log(
        contract=contract,
        action='send_invitation',
        user=request.user,
        user_role='creator',
        details=f"Vertrag für Partner {partner_identifier} bereitgestellt"
    )
    
    messages.success(request, 'Vertrag wurde erfolgreich konfiguriert und steht dem Partner zur Verfügung.')
    
    if request.POST.get('redirect_to_signing') == 'true':
        return redirect('contract_signing', pk=contract.pk)
    
    return redirect('contract_list')


def contract_detail(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    
    activities = contract.activities.all()[:20]
    
    is_creator = False
    is_partner = False
    
    if (request.user.is_authenticated and 
        hasattr(request.user, 'ethereum_address')):
        
        # Ethereum-Adresse in Kleinbuchstaben für den Vergleich mit der DB
        user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
        
        is_creator = user_eth_address == contract.creator_address
        is_partner = user_eth_address == contract.partner_address
        
        if is_partner and contract.status == 'invitation_sent':
            contract.status = 'viewed_by_partner'
            contract.save()
            
            ContractActivity.log(
                contract=contract,
                action='view',
                user=request.user,
                details="Partner hat den Vertrag angesehen"
            )
    
    if contract.blockchain_contract_id:
        contract.update_blockchain_status()
    
    return render(request, 'contractsapp/contract_detail.html', {
        'contract': contract,
        'activities': activities,
        'is_creator': is_creator, # Pass to context
        'is_partner': is_partner  # Pass to context
    })


def contract_signing(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    
    # Ethereum-Adresse in Kleinbuchstaben für den Vergleich mit der DB
    user_eth_address = request.user.ethereum_address.lower() if request.user.is_authenticated and request.user.ethereum_address else None
    
    is_creator = user_eth_address == contract.creator_address
    
    # Für nicht eingeloggte Benutzer oder Benutzer ohne Ethereum-Adresse,
    # nehmen wir an, dass sie der Partner sind, wenn sie nicht der Ersteller sind
    is_partner = user_eth_address == contract.partner_address
    
    # Überprüfen, ob der Benutzer bereits unterschrieben hat und zur Detailseite umleiten
    if is_creator and contract.status == 'signed_by_creator':
        messages.info(request, 'Sie haben diesen Vertrag bereits unterschrieben.')
        return redirect('contract_detail', pk=contract.pk)
    elif is_partner and contract.status == 'signed_by_partner':
        messages.info(request, 'Sie haben diesen Vertrag bereits unterschrieben.')
        return redirect('contract_detail', pk=contract.pk)
    
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
        'is_partner': is_partner,
        #'blockchain_data': blockchain_data
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

        try: # Wrap the signature processing logic in a try block
            if signature_data:
                try: # Inner try block for decoding signature
                    header, encoded = signature_data.split(',', 1)
                    signature_bytes = base64.b64decode(encoded)
                except Exception:
                    return HttpResponse("Ungültige Signaturdaten.", status=400)

                try: # Inner try block for processing signature and PDF
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
                    user_eth_address = request.user.ethereum_address.lower() if request.user.is_authenticated and request.user.ethereum_address else None
                    
                    is_creator = user_eth_address == contract.creator_address
                    is_partner = user_eth_address == contract.partner_address

                    # Initialize action_type and details with default values
                    action_type = 'invalid_attempt' # Shortened value
                    details = "Attempt to sign contract with unexpected status or role."

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
                        # Allow partner to sign if status is configured, invitation_sent, viewed_by_partner, or partner_verified
                        if contract.status in ['configured', 'invitation_sent', 'viewed_by_partner', 'partner_verified']:
                            contract.status = 'signed_by_partner'
                            action_type = 'sign_partner'
                            details = "Vertrag vom Partner unterzeichnet"
                        elif contract.status == 'signed_by_creator':
                            contract.status = 'completed'
                            action_type = 'complete'
                            details = "Vertrag vollständig unterzeichnet (Partner-Signatur)"
                    else:
                        action_type = 'other'
                        details = "Unbekannte Partei hat versucht, den Vertrag zu unterzeichnen"

                    try: # Innermost try block for saving and logging
                        contract_storage = ContractStorage()
                        
                        file_path = contract_storage.save_contract_file(
                            contract.pk, 
                            ContentFile(output_stream.getvalue()), 
                            is_signed=True
                        )
                        
                        contract.pdf_file.name = file_path
                        
                        blockchain_service = BlockchainService()
                        contract.pdf_hash = blockchain_service.calculate_pdf_hash(
                            ContentFile(output_stream.getvalue())
                        )
                        
                        contract.save() # Save status and other changes
                        
                        if request.user.is_authenticated:
                            ContractActivity.log(
                                contract=contract,
                                action=action_type,
                                user=request.user,
                                details=details
                            )
                            
                            messages.success(request, "Unterschrift erfolgreich hinzugefügt.")
                        
                        blockchain_tx_hash = request.POST.get('blockchain_tx_hash')
                        blockchain_contract_id = request.POST.get('blockchain_contract_id')
                        
                        if blockchain_contract_id:
                            contract.blockchain_contract_id = int(blockchain_contract_id)
                            contract.save(update_fields=['blockchain_contract_id'])
                            
                            ContractActivity.log(
                                contract=contract,
                                action='other',
                                user=request.user,
                                details=f"Vertrag auf der Blockchain registriert: Contract ID: {blockchain_contract_id}"
                            )
                        
                    except Exception as e:
                        # Log the error more clearly
                        print(f"ERROR: Exception in innermost try block: {e}")
                        print(traceback.format_exc())
                        return HttpResponse(f"Interner Fehler beim Speichern oder Protokollieren: {str(e)}", status=500) # Return an error instead of pass

                    # Check if the client requested no file download
                    if request.POST.get('no_download') == 'true':
                        # Prüfen, ob der Benutzer eingeloggt ist
                        if request.user.is_authenticated:
                            # Für eingeloggte Benutzer: Zur Vertragsliste weiterleiten
                            redirect_url = reverse('contract_list')
                        else:
                            # Für nicht eingeloggte Benutzer: Zur Erfolgsseite weiterleiten
                            redirect_url = reverse('contract_signing_success', args=[contract.pk])
                        
                        # Return a response with a redirect URL as JSON response
                        return JsonResponse({
                            'success': True,
                            'message': 'Unterschrift erfolgreich hinzugefügt',
                            'status': contract.status,
                            'redirect_url': redirect_url
                        })
                    else:
                        # Original behavior - return the PDF for download
                        response = HttpResponse(output_stream, content_type='application/pdf')
                        response['Content-Disposition'] = 'attachment; filename="signed_contract.pdf"'
                    return response
                    
                except Exception as e: # Inner except for processing signature and PDF
                    print(f"Error processing signature: {e}")
                    print(traceback.format_exc())
                    return HttpResponse(f"Fehler bei der Signaturverarbeitung: {str(e)}", status=400)

        except Exception as e: # Outer except, now correctly aligned with the new 'try'
            error_details = traceback.format_exc()
            print(f"Error saving signature: {error_details}")

            # Log the error in your contract activity log
            if request.user.is_authenticated:
                # Assign 'error' to action_type in case of an exception before assignment
                action_type = 'error'
                ContractActivity.log(
                    contract=contract,
                    action=action_type, # Use the assigned action_type
                    user=request.user,
                    details=f"Fehler beim Speichern der Unterschrift: {str(e)}"
                )

            # Return a descriptive error to the client
            return HttpResponse(f"Fehler beim Speichern der Unterschrift: {str(e)}", status=500)

    return HttpResponse("Fehler beim Hinzufügen der Unterschrift.", status=400)


def verify_partner(request, pk):
    # Entferne die strenge AJAX-Überprüfung, damit normale POST-Anfragen funktionieren
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})
    
    contract = get_object_or_404(Contract, pk=pk)
    
    # Wenn der Partner bereits eine Adresse hat, zeigen wir direkt die Erfolgsseite
    if contract.partner_address:
        if 'X-Requested-With' in request.headers and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        else:
            messages.success(request, "Sie haben sich erfolgreich verifiziert!")
            
            # Erstelle eine spezielle Session-Variable, um das Modal beim nächsten Seitenaufruf zu verstecken
            request.session['partner_verified_for_contract'] = str(pk)
            
            # Damit die Session-Daten sofort gespeichert werden
            request.session.modified = True
              # Erzwinge eine vollständige Seiten-Neuladung, damit die Verifikation wirksam wird
            return redirect('contract_signing', pk=pk)
    
    partner_address = request.POST.get('partner_address', '').strip()
    
    errors = {}
    
    # Da Partner jetzt angemeldete Benutzer sind, ist die Prüfung von Namen und E-Mail nicht mehr erforderlich
    # Die Identität wird bereits durch die Anmeldung verifiziert
         
    if not partner_address:
        errors['address'] = 'Bitte geben Sie Ihre Ethereum Wallet-Adresse ein.'
    elif not partner_address.startswith('0x') or len(partner_address) != 42:
        errors['address'] = 'Bitte geben Sie eine gültige Ethereum-Adresse ein (beginnt mit 0x und hat 42 Zeichen).'
    else:
        try:
            from web3 import Web3
            if not Web3.is_address(partner_address):
                errors['address'] = 'Die angegebene Ethereum-Adresse ist ungültig.'
            else:
                partner_address = Web3.to_checksum_address(partner_address)
        except Exception as e:
            errors['address'] = f'Fehler bei der Überprüfung der Ethereum-Adresse: {str(e)}'
    
    if errors:
        # Bei AJAX-Anfragen JSON zurückgeben
        if 'X-Requested-With' in request.headers and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': errors})
        # Bei normalen POST-Anfragen Fehler als Messages hinzufügen und zurück zum Formular
        else:
            for key, error in errors.items():
                messages.error(request, error)
            return redirect('contract_signing', pk=pk)
    
    # Hier sind wir sicher, dass die Daten gültig sind
    contract.partner_address = partner_address
    contract.status = 'partner_verified'
    contract.save()
    
    if request.user.is_authenticated:
        ContractActivity.log(
            contract=contract,
            action='verify_partner',
            user=request.user,
            user_role='partner',
            details=f"Partner hat sich verifiziert: {partner_address}"
        )
    
    # Bei AJAX-Anfragen JSON zurückgeben
    if 'X-Requested-With' in request.headers and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    # Bei normalen POST-Anfragen erfolgreiche Nachricht anzeigen und weiterleiten
    else:
        messages.success(request, "Sie haben sich erfolgreich verifiziert. Sie können jetzt den Vertrag unterzeichnen.")
        return redirect('contract_signing', pk=pk)


def contract_signing_success(request, pk):
    """Zeigt die Erfolgsseite für die Vertragsunterzeichnung an"""
    contract = get_object_or_404(Contract, pk=pk)
    
    # Prüfe, ob der Vertrag tatsächlich unterschrieben wurde
    if contract.status in ['signed_by_partner', 'signed_by_creator', 'completed', 'blockchain_published']:
        return render(request, 'contractsapp/contract_signing_success.html', {
            'contract': contract
        })
    else:
        # Falls der Vertrag nicht unterschrieben ist, leite zur normalen Signierseite um
        return redirect('contract_signing', pk=pk)


@login_required
def update_blockchain_status(request, pk):
    """API endpoint to update blockchain status from frontend"""
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})
    
    contract = get_object_or_404(Contract, pk=pk)
    
    is_creator = request.user.ethereum_address == contract.creator_address
    is_partner = request.user.ethereum_address == contract.partner_address
    
    if not (is_creator or is_partner):
        return JsonResponse({'success': False, 'message': 'Nicht autorisiert'})
    
    blockchain_tx_hash = request.POST.get('tx_hash')
    blockchain_contract_id = request.POST.get('contract_id')
    
    if blockchain_contract_id:
        try:
            # Konvertiere zu Integer
            blockchain_contract_id = int(blockchain_contract_id)
            
            # Setze nur die Contract-ID im Contract-Objekt
            contract.blockchain_contract_id = blockchain_contract_id
            contract.status = 'blockchain_published'
            
            # Speichern der Änderungen (nur Contract-ID, keine Transaction Hash)
            contract.save(update_fields=['blockchain_contract_id', 'status'])
            
            # Protokolliere die Aktivität (ohne Transaction Hash)
            ContractActivity.log(
                contract=contract,
                action='blockchain_published',
                user=request.user,
                details=f"Vertrag auf der Blockchain registriert: Contract ID: {blockchain_contract_id}"
            )
            
            try:
                contract.update_blockchain_status()
            except Exception as e:
                print(f"Error updating blockchain status: {e}")
            
            contract.refresh_from_db()
            
            return JsonResponse({
                'success': True, 
                'contract_id': contract.blockchain_contract_id,
                'tx_hash': blockchain_tx_hash, 
                'status': contract.blockchain_status or 'Updated',
                'message': 'Blockchain-Status erfolgreich aktualisiert'
            })
            
        except (ValueError, TypeError) as e:
            print(f"Fehler bei der Konvertierung der Contract-ID: {e}")
            return JsonResponse({'success': False, 'message': f'Ungültige Contract-ID: {str(e)}'})
        except Exception as e:
            import traceback
            print(f"Allgemeiner Fehler in update_blockchain_status: {e}")
            print(traceback.format_exc())
            return JsonResponse({'success': False, 'message': f'Interner Fehler: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Keine Contract-ID erhalten. Die Transaktion wurde möglicherweise nicht bestätigt.'})


@login_required
def withdraw_funds(request, pk):
    """API endpoint to withdraw funds from a completed contract"""
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})
    
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.user.ethereum_address != contract.partner_address:
        return JsonResponse({'success': False, 'message': 'Nicht autorisiert'})
    
    if contract.blockchain_status != 'Completed':
        return JsonResponse({'success': False, 'message': 'Vertrag ist nicht abgeschlossen'})
    
    blockchain_service = BlockchainService()
    try:
        tx = blockchain_service.withdrawFunds(request.user.ethereum_address)
        return JsonResponse({'success': True, 'transaction': json.dumps(dict(tx))})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Fehler: {str(e)}'})


@login_required
def deploy_contract(request):
    if not request.user.is_superuser:
        messages.error(request, "Nur Administratoren können den Smart Contract bereitstellen.")
        return redirect('contract_list')
    
    blockchain_service = BlockchainService()
    
    if request.method == 'POST':
        deployer_address = request.POST.get('deployer_address')
        
        if not deployer_address or not deployer_address.startswith('0x'):
            messages.error(request, "Bitte geben Sie eine gültige Ethereum-Adresse ein.")
            return render(request, 'contractsapp/deploy_contract.html')
        
        try:
            tx = blockchain_service.deploy_contract(deployer_address)
            
            tx_dict = dict(tx)
            
            if 'data' in tx_dict and isinstance(tx_dict['data'], bytes):
                tx_dict['data'] = tx_dict['data'].hex()
                
            for key, value in tx_dict.items():
                if isinstance(value, bytes):
                    tx_dict[key] = value.hex()
            
            return render(request, 'contractsapp/deploy_contract.html', {
                'transaction': json.dumps(tx_dict),
                'deployer_address': deployer_address
            })
        except Exception as e:
            messages.error(request, f"Fehler bei der Vorbereitung der Bereitstellung: {str(e)}")
    
    current_address = blockchain_service.get_contract_address()
    
    return render(request, 'contractsapp/deploy_contract.html', {
        'current_address': current_address
    })


@login_required
def update_contract_address(request):
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})
    
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Nicht autorisiert'})
    
    contract_address = request.POST.get('contract_address')
    if not contract_address or not contract_address.startswith('0x'):
        return JsonResponse({'success': False, 'message': 'Ungültige Vertragsadresse'})
    
    try:
        blockchain_service = BlockchainService()
        result = blockchain_service.set_contract_address(contract_address)
        
        if result:
            
            return JsonResponse({
                'success': True, 
                'message': 'Vertragsadresse erfolgreich aktualisiert',
                'address': contract_address
            })
        else:
            return JsonResponse({'success': False, 'message': 'Fehler beim Initialisieren des Vertrags'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Fehler: {str(e)}'})


@login_required
def submit_to_blockchain(request, pk):
    # Ethereum-Adresse in Kleinbuchstaben für den Vergleich mit der DB
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
    
    contract = get_object_or_404(Contract, pk=pk, creator_address=user_eth_address)
    blockchain_service = BlockchainService()  # BlockchainService für das Template

    if contract.status != 'completed':
        messages.error(request, "Nur vollständig unterschriebene Verträge können an die Blockchain übermittelt werden.")
        return redirect('contract_detail', pk=pk)
    
    if contract.blockchain_contract_id:
        messages.info(request, "Dieser Vertrag wurde bereits an die Blockchain übermittelt.")
        return redirect('contract_detail', pk=pk)
    
    if request.method == 'POST':
        # Bestehenden Vertragsbetrag verwenden
        if not contract.contract_amount:
            messages.error(request, "Für diesen Vertrag wurde kein Betrag festgelegt. Bitte kontaktieren Sie den Support.")
            return render(request, 'contractsapp/submit_to_blockchain.html', {
                'contract': contract,
                'blockchain_service': blockchain_service
            })
        
        try:
            if not contract.partner_address:
                messages.error(request, "Der Vertragspartner muss eine Ethereum-Adresse haben.")
                return redirect('contract_detail', pk=pk)
            
            if not contract.pdf_hash:
                try:
                    contract.pdf_hash = blockchain_service.calculate_pdf_hash(contract.pdf_file)
                    contract.save(update_fields=['pdf_hash'])
                    
                    ContractActivity.log(
                        contract=contract,
                        action='blockchain',
                        user=request.user,
                        user_role='creator',
                        details="PDF-Hash wurde neu berechnet für Blockchain-Übermittlung"
                    )
                    
                    messages.success(request, "PDF-Hash wurde neu berechnet.")
                except Exception as hash_error:
                    messages.error(request, f"Fehler beim Berechnen des PDF-Hashes: {str(hash_error)}")
                    return redirect('contract_detail', pk=pk)
            
            if not contract.pdf_hash:
                messages.error(request, "Der Vertrag hat keinen gültigen PDF-Hash. Bitte kontaktieren Sie den Support.")
                return redirect('contract_detail', pk=pk)
                
            tx = blockchain_service.create_contract(
                creator_address=contract.creator_address,
                counterparty_address=contract.partner_address,
                contract_hash=contract.pdf_hash,
                amount_wei=contract.contract_amount
            )
            
            ContractActivity.log(
                contract=contract,
                action='blockchain',
                user=request.user,
                user_role='creator',
                details="Blockchain-Transaktion für Vertrag vorbereitet"
            )
            
            tx_dict = dict(tx)
            contract.blockchain_contract_id = tx_dict.get('contract_id')
            
            if contract.blockchain_contract_id:
                contract.save(update_fields=['blockchain_contract_id'])

            # Binäre Daten in Hex-Strings umwandeln
            processed_tx = {}
            for key, value in tx_dict.items():
                if isinstance(value, bytes):
                    processed_tx[key] = value.hex()
                else:
                    processed_tx[key] = value
            
            # Stelle sicher, dass die Transaktion einen 'to'-Parameter hat
            if 'to' not in processed_tx and blockchain_service.contract_address:
                processed_tx['to'] = blockchain_service.contract_address
            
            # JSON-Serialisierung für das Template
            transaction_json = json.dumps(processed_tx)
            
            return render(request, 'contractsapp/submit_to_blockchain.html', {
                'contract': contract,
                'transaction': transaction_json,
                'is_submission': True,
                'blockchain_service': blockchain_service
            })
        except Exception as e:
            ContractActivity.log(
                contract=contract,
                action='blockchain_error',
                user=request.user,
                user_role='creator',
                details=f"Fehler bei der Blockchain-Übermittlung: {str(e)}"
            )
            
            messages.error(request, f"Fehler bei der Vorbereitung der Blockchain-Transaktion: {str(e)}")
            return redirect('contract_detail', pk=pk)
    
    ContractActivity.log(
        contract=contract,
        action='blockchain',
        user=request.user,
        user_role='creator',
        details="Blockchain-Übermittlungsseite geöffnet"
    )
    
    if contract.contract_amount:
        contract.eth_amount = contract.contract_amount / (10**18)
    
    return render(request, 'contractsapp/submit_to_blockchain.html', {
        'contract': contract,
        'blockchain_service': blockchain_service
    })