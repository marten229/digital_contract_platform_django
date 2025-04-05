from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.db.models import Q

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
from .services import MailjetService
from .blockchain import BlockchainService


@login_required
def contract_list(request):
    creator_contracts = Contract.objects.filter(creator_address=request.user.ethereum_address)
    
    partner_contracts = Contract.objects.filter(partner_address=request.user.ethereum_address)
    
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
    
    pending_partner_contracts = partner_contracts.filter(
        ~Q(status='completed') & 
        ~Q(status='rejected') &
        ~Q(status='blockchain_published')
    )
    
    completed_partner_contracts = partner_contracts.filter(status='completed')
    
    all_user_contracts = creator_contracts | partner_contracts
    recent_activities = ContractActivity.objects.filter(
        contract__in=all_user_contracts
    ).order_by('-timestamp')[:10]
    
    for contract in all_user_contracts:
        if contract.blockchain_contract_id:
            contract.update_blockchain_status()
    
    context = {
        'pending_contracts': pending_contracts,
        'in_progress_contracts': in_progress_contracts,
        'completed_contracts': completed_contracts,
        'rejected_contracts': rejected_contracts,
        'all_contracts': creator_contracts,
        'pending_partner_contracts': pending_partner_contracts,
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
            contract.creator_address = request.user.ethereum_address
            contract.status = 'uploaded'
            contract.is_configured = False
            
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
        form = ContractForm(initial={'creator_address': request.user.ethereum_address})
    
    return render(request, 'contractsapp/contract_upload.html', {'form': form})


@login_required
def contract_configuration(request, pk):
    """Display the contract configuration page to set signature positions"""
    contract = get_object_or_404(Contract, pk=pk, creator_address=request.user.ethereum_address)
    
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
    
    contract = get_object_or_404(Contract, pk=pk, creator_address=request.user.ethereum_address)
    
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
            contract.status = 'invitation_sent'
            contract.save()
            
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
    
    if request.POST.get('redirect_to_signing') == 'true':
        return redirect('contract_signing', pk=contract.pk)
    
    return redirect('contract_list')


def contract_detail(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    
    activities = contract.activities.all()[:20]
    
    if (request.user.is_authenticated and 
        hasattr(request.user, 'ethereum_address') and 
        request.user.ethereum_address != contract.creator_address):
        
        is_partner = contract.partner_address == request.user.ethereum_address
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
        'activities': activities
    })


def contract_signing(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    
    is_creator = request.user.is_authenticated and request.user.ethereum_address == contract.creator_address
    is_partner = request.user.is_authenticated and request.user.ethereum_address == contract.partner_address
    
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
    
    blockchain_data = {}
    if contract.pdf_hash and contract.contract_amount:
        if is_creator and contract.status in ['configured', 'invitation_sent', 'viewed_by_partner', 'partner_verified']:
            if contract.partner_address:
                blockchain_service = BlockchainService()
                try:
                    tx = blockchain_service.create_contract(
                        creator_address=contract.creator_address,
                        counterparty_address=contract.partner_address,
                        contract_hash=contract.pdf_hash,
                        amount_wei=contract.contract_amount
                    )
                    blockchain_data = {
                        'transaction': json.dumps(dict(tx)),
                        'contract_hash': contract.pdf_hash,
                        'amount_wei': contract.contract_amount
                    }
                except Exception as e:
                    messages.error(request, f"Fehler bei der Blockchain-Transaktion: {e}")
        elif is_partner and contract.status in ['viewed_by_partner', 'partner_verified']:
            if contract.blockchain_contract_id:
                blockchain_service = BlockchainService()
                try:
                    tx = blockchain_service.sign_contract(
                        partner_address=contract.partner_address,
                        contract_id=contract.blockchain_contract_id
                    )
                    blockchain_data = {
                        'transaction': json.dumps(dict(tx)),
                        'contract_id': contract.blockchain_contract_id
                    }
                except Exception as e:
                    messages.error(request, f"Fehler bei der Blockchain-Transaktion: {e}")
    
    return render(request, 'contractsapp/contract_signing.html', {
        'contract': contract,
        'is_creator': is_creator,
        'is_partner': is_partner,
        'blockchain_data': blockchain_data
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
                
                is_creator = (request.user.is_authenticated and 
                               request.user.ethereum_address == contract.creator_address)
                is_partner = (request.user.is_authenticated and 
                               request.user.ethereum_address == contract.partner_address)
                
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
                    from .storage import ContractStorage
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
                    
                    contract.save()
                    
                    if request.user.is_authenticated:
                        ContractActivity.log(
                            contract=contract,
                            action=action_type,
                            user=request.user,
                            details=details
                        )
                    
                    blockchain_tx_hash = request.POST.get('blockchain_tx_hash')
                    blockchain_contract_id = request.POST.get('blockchain_contract_id')
                    
                    if blockchain_tx_hash:
                        contract.transaction_hash = blockchain_tx_hash
                        if blockchain_contract_id:
                            contract.blockchain_contract_id = int(blockchain_contract_id)
                        contract.save(update_fields=['transaction_hash', 'blockchain_contract_id'])
                        
                        ContractActivity.log(
                            contract=contract,
                            action='other',
                            user=request.user,
                            details=f"Vertrag auf der Blockchain registriert: TX {blockchain_tx_hash[:10]}..."
                        )
                    
                except Exception as e:
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
        return JsonResponse({'success': False, 'errors': errors})
    
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
    
    return JsonResponse({'success': True})


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
    
    if blockchain_tx_hash:
        # Print debug information
        print(f"Aktualisiere Blockchain-Status von Contract {pk}")
        print(f"Frontend TX Hash: {blockchain_tx_hash}")
        print(f"Frontend Contract ID: {blockchain_contract_id}")
        
        contract.transaction_hash = blockchain_tx_hash
        
        if blockchain_contract_id:
            contract.blockchain_contract_id = int(blockchain_contract_id)
        
        # Explizit speichern und sicherstellen, dass die Daten gespeichert werden
        contract.save(update_fields=['transaction_hash', 'blockchain_contract_id'])
        print(f"Daten gespeichert: TX Hash={contract.transaction_hash}, Contract ID={contract.blockchain_contract_id}")
        
        # Status aktualisieren und Status auf "blockchain_published" setzen
        contract.status = 'blockchain_published'
        contract.save(update_fields=['status'])
        
        contract.update_blockchain_status()
        
        ContractActivity.log(
            contract=contract,
            action='blockchain_published',
            user=request.user,
            details=f"Vertrag wurde auf der Blockchain registriert: TX {blockchain_tx_hash[:10]}..."
        )
        
        return JsonResponse({
            'success': True, 
            'contract_id': contract.blockchain_contract_id,
            'status': contract.blockchain_status
        })
    
    return JsonResponse({'success': False, 'message': 'Keine Transaktionsdaten erhalten'})


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
    contract = get_object_or_404(Contract, pk=pk, creator_address=request.user.ethereum_address)

    if contract.status != 'completed':
        messages.error(request, "Nur vollständig unterschriebene Verträge können an die Blockchain übermittelt werden.")
        return redirect('contract_detail', pk=pk)
    
    if contract.blockchain_contract_id:
        messages.info(request, "Dieser Vertrag wurde bereits an die Blockchain übermittelt.")
        return redirect('contract_detail', pk=pk)
    
    if request.method == 'POST':
        contract_amount = request.POST.get('contract_amount')
        try:
            amount_wei = int(float(contract_amount) * 10**18)
            contract.contract_amount = amount_wei
            contract.save(update_fields=['contract_amount'])
            
            ContractActivity.log(
                contract=contract,
                action='blockchain',
                user=request.user,
                user_role='creator',
                details=f"Vertragswert festgelegt: {contract_amount} ETH"
            )
        except (ValueError, TypeError):
            messages.error(request, "Bitte geben Sie einen gültigen Betrag ein.")
            return render(request, 'contractsapp/submit_to_blockchain.html', {'contract': contract})
        
        blockchain_service = BlockchainService()
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

            # Debugging logs to ensure data is being processed correctly
            print(f"Blockchain transaction response: {tx_dict}")

            # Save blockchain details
            contract.blockchain_contract_id = tx_dict.get('contract_id')
            contract.transaction_hash = tx_dict.get('transaction_hash')

            if not contract.blockchain_contract_id or not contract.transaction_hash:
                print("Error: Missing blockchain_contract_id or transaction_hash in response.")
            else:
                print(f"Saving contract with ID: {contract.blockchain_contract_id} and TX hash: {contract.transaction_hash}")

            contract.save(update_fields=['blockchain_contract_id', 'transaction_hash'])

            for key, value in tx_dict.items():
                if isinstance(value, bytes):
                    tx_dict[key] = value.hex()
            
            return render(request, 'contractsapp/submit_to_blockchain.html', {
                'contract': contract,
                'transaction': json.dumps(tx_dict),
                'is_submission': True
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
    
    return render(request, 'contractsapp/submit_to_blockchain.html', {'contract': contract})