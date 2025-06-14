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
from .dhl_tracking import DHLTrackingService


@login_required
def contract_list(request):
    """
    <summary>
     Displays the main dashboard for the logged-in user, showing lists of contracts categorized by status and role (creator/partner).
     It fetches contracts associated with the user's Ethereum address, updates their blockchain status if applicable, and retrieves recent activities.
    </summary>
    <param name="request">The HttpRequest object containing user session and authentication data.</param>
    <returns>An HttpResponse object rendering the 'contract_list.html' template with categorized contract lists and recent activities.</returns>
    """
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None

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

    # Blockchain-Verträge inkl. solcher mit Versandstatus (package_shipped, package_delivered, delivery_confirmed)
    blockchain_contracts = creator_contracts.filter(
        Q(status='blockchain_published') |
        Q(status='package_shipped') |
        Q(status='package_delivered') |
        Q(status='delivery_confirmed')
    )
    blockchain_partner_contracts = partner_contracts.filter(
        Q(status='blockchain_published') |
        Q(status='package_shipped') |
        Q(status='package_delivered') |
        Q(status='delivery_confirmed')
    )

    pending_partner_contracts = partner_contracts.filter(
        Q(status='invitation_sent') |
        Q(status='viewed_by_partner') |
        Q(status='partner_verified') |
        Q(status='configured') |
        Q(status='signed_by_creator')

    )


    signed_by_partner_contracts = partner_contracts.filter(status='signed_by_partner')

    completed_partner_contracts = partner_contracts.filter(status='completed')    
    all_contract_pks = list(creator_contracts.values_list('pk', flat=True)) + \
                       list(partner_contracts.values_list('pk', flat=True))
    recent_activities = ContractActivity.objects.filter(
        contract_id__in=set(all_contract_pks)
    ).select_related('contract').order_by('-timestamp')[:10]
    contracts_to_update = creator_contracts.exclude(blockchain_status__isnull=True) | \
                          partner_contracts.exclude(blockchain_status__isnull=True)
    for contract in contracts_to_update:
        contract.update_blockchain_status()

        if contract.blockchain_status == 'Completed':
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("SELECT funds_withdrawn FROM contractsapp_contract WHERE id = %s", [contract.pk])
                    result = cursor.fetchone()
                    if result and result[0]:
                        contract.funds_withdrawn = True
            except Exception as e:
                print(f"Fehler beim Aktualisieren des funds_withdrawn Status: {e}")    # Filter contracts with DHL tracking status
    all_contracts = creator_contracts | partner_contracts
    
    # Contracts with tracking number but no DHL status yet (just shipped)
    shipped_contracts = all_contracts.filter(
        status='package_shipped',
        tracking_number__isnull=False
    ).exclude(
        Q(package_status='in_transit') |
        Q(package_status='out_for_delivery') |
        Q(package_status='delivered') |
        Q(package_status='failed')
    )
    
    # Contracts with DHL tracking that are in different shipping statuses
    in_transit_contracts = all_contracts.filter(has_dhl_tracking=True, package_status='in_transit')
    out_for_delivery_contracts = all_contracts.filter(has_dhl_tracking=True, package_status='out_for_delivery')
    
    # Get all delivered contracts, including those that are awaiting confirmation and those that are already confirmed
    delivered_contracts = all_contracts.filter(
        has_dhl_tracking=True,
        package_status='delivered'
    ).filter(
        Q(status='package_delivered') | Q(status='delivery_confirmed')
    )
    
    failed_delivery_contracts = all_contracts.filter(has_dhl_tracking=True, package_status='failed')
    context = {
        'pending_contracts': pending_contracts,
        'in_progress_contracts': in_progress_contracts,
        'completed_contracts': completed_contracts,
        'rejected_contracts': rejected_contracts,
        'all_contracts': all_contracts,
        'pending_partner_contracts': pending_partner_contracts,
        'signed_by_partner_contracts': signed_by_partner_contracts,
        'shipped_contracts': shipped_contracts,
        'in_transit_contracts': in_transit_contracts,
        'out_for_delivery_contracts': out_for_delivery_contracts, 
        'delivered_contracts': delivered_contracts,
        'failed_delivery_contracts': failed_delivery_contracts,
        'completed_partner_contracts': completed_partner_contracts,
        'blockchain_contracts': blockchain_contracts,
        'blockchain_partner_contracts': blockchain_partner_contracts,
        'recent_activities': recent_activities,
    }

    return render(request, 'contractsapp/contract_list.html', context)


@login_required
def contract_upload(request):
    """
    <summary>
     Handles the contract upload process.
     On GET request, it displays the upload form.
     On POST request, it validates the form, saves the new contract with 'uploaded' status,
     associates it with the logged-in user as the creator, calculates the PDF hash, logs the activity,
     and redirects to the contract configuration page.
     </summary>
    <param name="request">The HttpRequest object containing form data (POST) or session data (GET).</param>
    <returns>An HttpResponse object rendering the 'contract_upload.html' template (GET or invalid POST) or an HttpResponseRedirect to the 'contract_configuration' view (valid POST).</returns>
    """
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.creator_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None

            contract.status = 'uploaded'
            contract.is_configured = False

            contract.creator = None
            contract.partner = None

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
    """
    <summary>
     Displays the contract configuration interface for the contract creator.
     It fetches the contract specified by 'pk' and ensures the current user is the creator.
     If the contract is already configured, it redirects to the detail view.
     Logs the start of the configuration process if the status is 'uploaded'.
     </summary>
    <param name="request">The HttpRequest object containing user session data.</param>
    <param name="pk">The primary key of the Contract to be configured.</param>
    <returns>An HttpResponse object rendering the 'contract_configuration.html' template or an HttpResponseRedirect to the 'contract_detail' view.</returns>
    """
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
    """
    <summary>
     Handles the submission of the contract configuration form (POST request).
     It saves the signature placement coordinates provided by the creator, marks the contract as configured,
     updates its status to 'invitation_sent', logs the completion activity, and redirects either to the signing page or the contract list.
     Ensures the user is the creator and the contract isn't already configured.
     </summary>
    <param name="request">The HttpRequest object containing the POST data with signature coordinates.</param>
    <param name="pk">The primary key of the Contract being configured.</param>
    <returns>An HttpResponseRedirect to the 'contract_signing' or 'contract_list' view on success, or back to 'contract_configuration' on error.</returns>
    """
    if request.method != 'POST':
        return redirect('contract_configuration', pk=pk)

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
    contract.has_dhl_tracking = 'has_dhl_tracking' in request.POST
    tracking_number = request.POST.get('tracking_number', '').strip()    
    if tracking_number:
        from .dhl_tracking import DHLTrackingService
        tracking_service = DHLTrackingService()
        
        contract.tracking_number = tracking_number
        contract.tracking_hash = tracking_service.generate_tracking_hash(tracking_number)
        contract.package_status = 'initialized'
        tracking_details = f"DHL Tracking aktiviert mit Tracking-Nummer: {tracking_number}"
    elif contract.has_dhl_tracking:
        tracking_details = "DHL Tracking aktiviert (Tracking-Nummer noch nicht hinzugefügt)"
    else:
        tracking_details = None
    
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

    contract.status = 'invitation_sent'
    contract.save()

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
    """
    <summary>
     Displays the detailed view of a specific contract.
     It fetches the contract by its primary key, retrieves recent activities, and determines if the logged-in user is the creator or partner.
     If the user is the partner and views the contract for the first time ('invitation_sent' status), the status is updated to 'viewed_by_partner'.
     It also updates and displays the contract's blockchain status if applicable.
     </summary>
    <param name="request">The HttpRequest object containing user session data.</param>
    <param name="pk">The primary key of the Contract to display.</param>
    <returns>An HttpResponse object rendering the 'contract_detail.html' template with contract details, activities, and user role flags.</returns>
    """
    contract = get_object_or_404(Contract, pk=pk)

    activities = contract.activities.all()[:20]

    is_creator = False
    is_partner = False

    if (request.user.is_authenticated and
        hasattr(request.user, 'ethereum_address')):

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

        if contract.blockchain_status == 'Completed':
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("SELECT funds_withdrawn FROM contractsapp_contract WHERE id = %s", [contract.pk])
                    result = cursor.fetchone()
                    if result and result[0]:
                        contract.funds_withdrawn = True
            except Exception as e:
                print(f"Fehler beim Aktualisieren des funds_withdrawn Status: {e}")

    return render(request, 'contractsapp/contract_detail.html', {
        'contract': contract,
        'activities': activities,
        'is_creator': is_creator,
        'is_partner': is_partner
    })


def contract_signing(request, pk):
    """
    <summary>
     Displays the contract signing interface.
     It fetches the contract by its primary key and determines if the current user is the creator or partner.
     Prevents users from accessing the signing page if they have already signed.
     Logs an activity when a user (creator or partner) opens the signing page.
     Updates the contract status to 'viewed_by_partner' if the partner opens it for the first time.
     </summary>
    <param name="request">The HttpRequest object containing user session data.</param>
    <param name="pk">The primary key of the Contract to be signed.</param>
    <returns>An HttpResponse object rendering the 'contract_signing.html' template or an HttpResponseRedirect to the 'contract_detail' view if already signed.</returns>
    """
    contract = get_object_or_404(Contract, pk=pk)

    user_eth_address = request.user.ethereum_address.lower() if request.user.is_authenticated and request.user.ethereum_address else None

    is_creator = user_eth_address == contract.creator_address

    is_partner = user_eth_address == contract.partner_address

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
    })


def add_signature(request, pk):
    """
    <summary>
     Processes and adds a signature image (provided as base64 data) to the contract's PDF file.
     It receives the signature data, coordinates, and page number via POST request.
     The signature image is decoded, processed (converted to PNG if needed), and merged onto the specified page of the original PDF.
     The updated PDF is saved, replacing the old one. The contract status is updated based on who signed (creator or partner) and the previous status.
     Logs the signing activity. Handles potential blockchain transaction info passed from the frontend.
     </summary>
    <param name="request">The HttpRequest object containing POST data: 'signature' (base64 image), 'x', 'y', 'width', 'height', 'page', optionally 'blockchain_tx_hash', 'blockchain_contract_id', 'no_download'.</param>
    <param name="pk">The primary key of the Contract to add the signature to.</param>
    <returns>
     - An HttpResponse with the signed PDF as an attachment if 'no_download' is not 'true'.
     - A JsonResponse indicating success and providing a redirect URL if 'no_download' is 'true'.
     - An HttpResponse with an error message (status 400 or 500) if processing fails.
     </returns>
    """
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

        try:
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
                    user_eth_address = request.user.ethereum_address.lower() if request.user.is_authenticated and request.user.ethereum_address else None

                    is_creator = user_eth_address == contract.creator_address
                    is_partner = user_eth_address == contract.partner_address

                    action_type = 'invalid_attempt'
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

                    try:
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
                        print(f"ERROR: Exception in innermost try block: {e}")
                        print(traceback.format_exc())
                        return HttpResponse(f"Interner Fehler beim Speichern oder Protokollieren: {str(e)}", status=500) # Return an error instead of pass

                    if request.POST.get('no_download') == 'true':
                        if request.user.is_authenticated:
                            redirect_url = reverse('contract_list')
                        else:
                            redirect_url = reverse('contract_signing_success', args=[contract.pk])

                        return JsonResponse({
                            'success': True,
                            'message': 'Unterschrift erfolgreich hinzugefügt',
                            'status': contract.status,
                            'redirect_url': redirect_url
                        })
                    else:
                        response = HttpResponse(output_stream, content_type='application/pdf')
                        response['Content-Disposition'] = 'attachment; filename="signed_contract.pdf"'
                    return response

                except Exception as e:
                    print(f"Error processing signature: {e}")
                    print(traceback.format_exc())
                    return HttpResponse(f"Fehler bei der Signaturverarbeitung: {str(e)}", status=400)

        except Exception as e:
            error_details = traceback.format_exc()
            print(f"Error saving signature: {error_details}")

            if request.user.is_authenticated:
                action_type = 'error'
                ContractActivity.log(
                    contract=contract,
                    action=action_type,
                    user=request.user,
                    details=f"Fehler beim Speichern der Unterschrift: {str(e)}"
                )

            return HttpResponse(f"Fehler beim Speichern der Unterschrift: {str(e)}", status=500)

    return HttpResponse("Fehler beim Hinzufügen der Unterschrift.", status=400)


def verify_partner(request, pk):
    """
    <summary>
     Verifies the partner's Ethereum address for a specific contract.
     Handles POST requests, expecting 'partner_address'. Validates the address format and checksum.
     If valid, saves the address to the contract, updates the status to 'partner_verified', and logs the activity.
     Can respond with JSON for AJAX requests or redirect with messages for standard form submissions.
     If the partner address is already set, it confirms verification.
     </summary>
    <param name="request">The HttpRequest object, potentially containing 'partner_address' in POST data and 'X-Requested-With' header for AJAX.</param>
    <param name="pk">The primary key of the Contract for which the partner is being verified.</param>
    <returns>
     - A JsonResponse indicating success or failure (with errors) for AJAX requests.
     - An HttpResponseRedirect to the 'contract_signing' view with success or error messages for standard requests.
     </returns>
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})

    contract = get_object_or_404(Contract, pk=pk)

    if contract.partner_address:
        if 'X-Requested-With' in request.headers and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        else:
            messages.success(request, "Sie haben sich erfolgreich verifiziert!")

            request.session['partner_verified_for_contract'] = str(pk)

            request.session.modified = True
            return redirect('contract_signing', pk=pk)

    partner_address = request.POST.get('partner_address', '').strip()

    errors = {}

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
        if 'X-Requested-With' in request.headers and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': errors})
        else:
            for key, error in errors.items():
                messages.error(request, error)
            return redirect('contract_signing', pk=pk)

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

    if 'X-Requested-With' in request.headers and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    else:
        messages.success(request, "Sie haben sich erfolgreich verifiziert. Sie können jetzt den Vertrag unterzeichnen.")
        return redirect('contract_signing', pk=pk)


def contract_signing_success(request, pk):
    """
    <summary>
     Displays a success page after a contract has been signed (or is completed/on blockchain).
     This is typically shown to users who signed without being logged in, after the signature is processed via AJAX.
     It fetches the contract and checks if its status indicates signing is done.
     </summary>
    <param name="request">The HttpRequest object.</param>
    <param name="pk">The primary key of the Contract that was signed.</param>
    <returns>An HttpResponse object rendering the 'contract_signing_success.html' template if the status is appropriate, otherwise redirects to 'contract_signing'.</returns>
    """
    contract = get_object_or_404(Contract, pk=pk)

    if contract.status in ['signed_by_partner', 'signed_by_creator', 'completed', 'blockchain_published']:
        return render(request, 'contractsapp/contract_signing_success.html', {
            'contract': contract
        })
    else:
        return redirect('contract_signing', pk=pk)


@login_required
def update_blockchain_status(request, pk):
    """
    <summary>
     Handles AJAX POST requests to update the contract's blockchain-related information.
     It expects either a 'contract_id' (when the contract is first registered on the blockchain) or 'withdrawal_completed' flag.
     Verifies the user is either the creator or partner. Updates the contract's `blockchain_contract_id`, `status`, or `funds_withdrawn` field accordingly.
     Logs relevant activities. Can trigger an update of the contract's blockchain status from the chain.
     </summary>
    <param name="request">The HttpRequest object, expected to be AJAX POST, containing 'contract_id' or 'withdrawal_completed', and optionally 'tx_hash'.</param>
    <param name="pk">The primary key of the Contract to update.</param>
    <returns>A JsonResponse indicating success or failure, potentially including updated status information.</returns>
    """
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})

    contract = get_object_or_404(Contract, pk=pk)

    is_creator = request.user.ethereum_address == contract.creator_address
    is_partner = request.user.ethereum_address == contract.partner_address

    if not (is_creator or is_partner):        return JsonResponse({'success': False, 'message': 'Nicht autorisiert'})
    
    blockchain_tx_hash = request.POST.get('tx_hash')
    blockchain_contract_id = request.POST.get('contract_id')
    withdrawal_completed = request.POST.get('withdrawal_completed') == 'true'
    tracking_set = request.POST.get('tracking_set') == 'true'
    tracking_number = request.POST.get('tracking_number', '')

    if tracking_set:
        # Save tracking number to database ONLY after successful blockchain transaction
        if tracking_number:
            from .dhl_tracking import DHLTrackingService
            tracking_service = DHLTrackingService()
            
            contract.tracking_number = tracking_number
            contract.tracking_hash = tracking_service.generate_tracking_hash(tracking_number)
            contract.status = 'package_shipped'
            contract.save()
            
            ContractActivity.log(
                contract=contract,
                action='tracking_blockchain_success',
                user=request.user,
                user_role='partner',
                details=f"Tracking-Nummer erfolgreich auf Blockchain hinterlegt und in DB gespeichert: {tracking_number}, TX: {blockchain_tx_hash}"
            )
        else:
            ContractActivity.log(
                contract=contract,
                action='tracking_blockchain_success',
                user=request.user,
                user_role='partner',
                details=f"Tracking-Hash erfolgreich auf Blockchain hinterlegt: Transaction Hash: {blockchain_tx_hash}"
            )

        return JsonResponse({
            'success': True,
            'message': 'Tracking-Nummer erfolgreich auf Blockchain hinterlegt und in Datenbank gespeichert'
        })

    if withdrawal_completed:
        contract.funds_withdrawn = True
        contract.save(update_fields=['funds_withdrawn'])

        ContractActivity.log(
            contract=contract,
            action='blockchain_withdraw_success',
            user=request.user,
            user_role='partner',
            details=f"Vertragsgelder erfolgreich abgehoben: Transaction Hash: {blockchain_tx_hash}"
        )

        return JsonResponse({
            'success': True,
            'message': 'Abhebungsstatus erfolgreich aktualisiert'
        })

    if blockchain_contract_id:
        try:
            blockchain_contract_id = int(blockchain_contract_id)

            contract.blockchain_contract_id = blockchain_contract_id
            contract.status = 'blockchain_published'

            contract.save(update_fields=['blockchain_contract_id', 'status'])

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
    """
    <summary>
     Handles AJAX POST requests for the partner to initiate the fund withdrawal process from the blockchain smart contract.
     Verifies the user is the partner and the contract's blockchain status is 'Completed'.
     Calls the `withdrawFunds` method of the BlockchainService to prepare the transaction.
     </summary>
    <param name="request">The HttpRequest object, expected to be AJAX POST.</param>
    <param name="pk">The primary key of the Contract from which funds are to be withdrawn.</param>
    <returns>A JsonResponse containing the prepared transaction details on success, or an error message on failure.</returns>
    """
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})
    
    contract = get_object_or_404(Contract, pk=pk)

    if request.user.ethereum_address != contract.partner_address:
        return JsonResponse({'success': False, 'message': 'Nicht autorisiert'})

    if contract.blockchain_status != 'Completed':
        return JsonResponse({'success': False, 'message': 'Vertrag ist nicht abgeschlossen'})

    blockchain_service = BlockchainService()
    try:
        tx = blockchain_service.withdrawFunds(request.user.ethereum_address, contract.blockchain_contract_id)
        return JsonResponse({'success': True, 'transaction': json.dumps(dict(tx))})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Fehler: {str(e)}'})


@login_required
def deploy_contract(request):
    """
    Admin-only view to deploy the main smart contract to the blockchain.
    """
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
    
    # Get default oracle address from settings if available
    from django.conf import settings
    default_oracle_address = getattr(settings, 'DEFAULT_ORACLE_ADDRESS', '')

    return render(request, 'contractsapp/deploy_contract.html', {
        'current_address': current_address,
        'default_oracle_address': default_oracle_address
    })


@login_required
def update_contract_address(request):
    """
    <summary>
     Admin-only AJAX endpoint to update the application's configured smart contract address after deployment.
     Requires superuser privileges. Handles POST requests containing the new 'contract_address'.
     Validates the address and calls the BlockchainService to update the configuration (likely stored in settings or a configuration file/database).
     </summary>
    <param name="request">The HttpRequest object, expected to be AJAX POST, containing 'contract_address'.</param>
    <returns>A JsonResponse indicating success or failure, including the updated address on success.</returns>
    """
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
    """
    <summary>
     View for the contract creator to initiate the process of registering a completed contract on the blockchain.
     Ensures the contract is 'completed' and not already on the blockchain.
     On GET, displays contract details and the submission form.
     On POST, validates necessary conditions (partner address, amount, PDF hash), calculates hash if missing,
     and calls the BlockchainService to prepare the `create_contract` transaction.
     Renders the transaction details for the creator to execute via their wallet. Logs activities.
     </summary>
    <param name="request">The HttpRequest object.</param>
    <param name="pk">The primary key of the Contract to be submitted.</param>
    <returns>An HttpResponse object rendering the 'submit_to_blockchain.html' template, potentially including transaction details, or an HttpResponseRedirect on error/invalid state.</returns>
    """
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None

    contract = get_object_or_404(Contract, pk=pk, creator_address=user_eth_address)
    blockchain_service = BlockchainService()

    if contract.status != 'completed':
        messages.error(request, "Nur vollständig unterschriebene Verträge können an die Blockchain übermittelt werden.")
        return redirect('contract_detail', pk=pk)

    if contract.blockchain_contract_id:
        messages.info(request, "Dieser Vertrag wurde bereits an die Blockchain übermittelt.")
        return redirect('contract_detail', pk=pk)

    if request.method == 'POST':
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

            processed_tx = {}
            for key, value in tx_dict.items():
                if isinstance(value, bytes):
                    processed_tx[key] = value.hex()
                else:
                    processed_tx[key] = value

            if 'to' not in processed_tx and blockchain_service.contract_address:
                processed_tx['to'] = blockchain_service.contract_address

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


@login_required
def sign_blockchain_contract(request, pk):
    """
    <summary>
     View for the contract partner to initiate the signing of the contract on the blockchain.
     Ensures the contract exists on the blockchain (`blockchain_contract_id` is set) and its status is 'Created'.
     On GET, displays contract details and the signing form/button.
     On POST, calls the BlockchainService to prepare the `sign_contract` transaction.
     Renders the transaction details for the partner to execute via their wallet. Logs activities. Includes Etherscan links.
     </summary>
    <param name="request">The HttpRequest object.</param>
    <param name="pk">The primary key of the Contract to be signed on the blockchain.</param>
    <returns>An HttpResponse object rendering the 'sign_blockchain_contract.html' template, potentially including transaction details, or an HttpResponseRedirect on error/invalid state.</returns>
    """
    from django.conf import settings

    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None

    contract = get_object_or_404(Contract, pk=pk, partner_address=user_eth_address)
    blockchain_service = BlockchainService()

    if not contract.blockchain_contract_id:
        messages.error(request, "Dieser Vertrag wurde noch nicht auf der Blockchain registriert.")
        return redirect('contract_detail', pk=pk)

    if contract.blockchain_status != 'Created':
        messages.info(request, "Dieser Vertrag benötigt keine Signatur mehr auf der Blockchain.")
        return redirect('contract_detail', pk=pk)

    network = getattr(settings, 'ETHEREUM_NETWORK', 'sepolia')
    if network == 'mainnet':
        explorer_url = f"https://etherscan.io/address/{blockchain_service.contract_address}"
        tx_explorer_base = "https://etherscan.io/tx/"
    else:
        explorer_url = f"https://{network}.etherscan.io/address/{blockchain_service.contract_address}"
        tx_explorer_base = f"https://{network}.etherscan.io/tx/"

    if request.method == 'POST':
        try:
            tx = blockchain_service.sign_contract(
                partner_address=contract.partner_address,
                contract_id=contract.blockchain_contract_id
            )

            ContractActivity.log(
                contract=contract,
                action='blockchain_sign',
                user=request.user,
                user_role='partner',
                details="Blockchain-Signatur für Vertrag vorbereitet"
            )

            tx_dict = dict(tx)

            processed_tx = {}
            for key, value in tx_dict.items():
                if isinstance(value, bytes):
                    processed_tx[key] = value.hex()
                else:
                    processed_tx[key] = value

            if 'to' not in processed_tx and blockchain_service.contract_address:
                processed_tx['to'] = blockchain_service.contract_address

            transaction_json = json.dumps(processed_tx)

            return render(request, 'contractsapp/sign_blockchain_contract.html', {
                'contract': contract,
                'transaction': transaction_json,
                'is_submission': True,
                'blockchain_service': blockchain_service,
                'explorer_url': explorer_url,
                'tx_explorer_base': tx_explorer_base
            })
        except Exception as e:
            ContractActivity.log(
                contract=contract,
                action='blockchain_error',
                user=request.user,
                user_role='partner',
                details=f"Fehler bei der Blockchain-Signatur: {str(e)}"
            )

            messages.error(request, f"Fehler bei der Vorbereitung der Blockchain-Signatur: {str(e)}")
            return redirect('contract_detail', pk=pk)

    ContractActivity.log(
        contract=contract,
        action='blockchain_sign_view',
        user=request.user,
        user_role='partner',
        details="Blockchain-Signaturseite geöffnet"
    )

    return render(request, 'contractsapp/sign_blockchain_contract.html', {
        'contract': contract,
        'blockchain_service': blockchain_service,
        'explorer_url': explorer_url,
        'tx_explorer_base': tx_explorer_base
    })


@login_required
def confirm_contract_completion(request, pk):
    """
    <summary>
     View for the contract creator to confirm the completion of the contract on the blockchain.
     Ensures the contract is on the blockchain and its status is 'Signed'.
     On GET, displays contract details and the confirmation form/button.
     On POST, calls the BlockchainService to prepare the `confirm_completion` transaction.
     Renders the transaction details for the creator to execute via their wallet. Logs activities. Includes Etherscan links.
     </summary>
    <param name="request">The HttpRequest object.</param>
    <param name="pk">The primary key of the Contract to be confirmed as completed on the blockchain.</param>
    <returns>An HttpResponse object rendering the 'confirm_contract_completion.html' template, potentially including transaction details, or an HttpResponseRedirect on error/invalid state.</returns>
    """
    from django.conf import settings

    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None

    contract = get_object_or_404(Contract, pk=pk, creator_address=user_eth_address)
    blockchain_service = BlockchainService()

    if not contract.blockchain_contract_id:
        messages.error(request, "Dieser Vertrag wurde noch nicht auf der Blockchain registriert.")
        return redirect('contract_detail', pk=pk)

    if contract.blockchain_status != 'Signed':
        if contract.blockchain_status == 'Created':
            messages.info(request, "Dieser Vertrag muss zuerst vom Partner auf der Blockchain signiert werden.")
        elif contract.blockchain_status == 'Completed':
            messages.info(request, "Dieser Vertrag wurde bereits als erfüllt bestätigt.")
        else:
            messages.info(request, "Dieser Vertrag kann nicht als erfüllt bestätigt werden.")
        return redirect('contract_detail', pk=pk)

    network = getattr(settings, 'ETHEREUM_NETWORK', 'sepolia')
    if network == 'mainnet':
        explorer_url = f"https://etherscan.io/address/{blockchain_service.contract_address}"
        tx_explorer_base = "https://etherscan.io/tx/"
    else:
        explorer_url = f"https://{network}.etherscan.io/address/{blockchain_service.contract_address}"
        tx_explorer_base = f"https://{network}.etherscan.io/tx/"

    if request.method == 'POST':
        try:
            tx = blockchain_service.confirm_completion(
                creator_address=contract.creator_address,
                contract_id=contract.blockchain_contract_id
            )

            ContractActivity.log(
                contract=contract,
                action='blockchain_complete',
                user=request.user,
                user_role='creator',
                details="Blockchain-Vertragserfüllung vorbereitet"
            )

            tx_dict = dict(tx)

            processed_tx = {}
            for key, value in tx_dict.items():
                if isinstance(value, bytes):
                    processed_tx[key] = value.hex()
                else:
                    processed_tx[key] = value

            if 'to' not in processed_tx and blockchain_service.contract_address:
                processed_tx['to'] = blockchain_service.contract_address

            transaction_json = json.dumps(processed_tx)

            return render(request, 'contractsapp/confirm_contract_completion.html', {
                'contract': contract,
                'transaction': transaction_json,
                'is_submission': True,
                'blockchain_service': blockchain_service,
                'explorer_url': explorer_url,
                'tx_explorer_base': tx_explorer_base
            })
        except Exception as e:
            ContractActivity.log(
                contract=contract,
                action='blockchain_error',
                user=request.user,
                user_role='creator',
                details=f"Fehler bei der Blockchain-Vertragserfüllung: {str(e)}"
            )

            messages.error(request, f"Fehler bei der Vorbereitung der Blockchain-Vertragserfüllung: {str(e)}")
            return redirect('contract_detail', pk=pk)
    ContractActivity.log(
        contract=contract,
        action='blockchain_complete_view',
        user=request.user,
        user_role='creator',
        details="Blockchain-Vertragserfüllungsseite geöffnet"
    )

    return render(request, 'contractsapp/confirm_contract_completion.html', {
        'contract': contract,
        'blockchain_service': blockchain_service,
        'explorer_url': explorer_url,
        'tx_explorer_base': tx_explorer_base
    })


@login_required
def withdraw_contract_funds(request, pk):
    """
    <summary>
     View for the contract partner to initiate the withdrawal of funds from a completed contract on the blockchain.
     Ensures the contract is on the blockchain and its status is 'Completed'.
     On GET, displays contract details and the withdrawal form/button.
     On POST, calls the BlockchainService to prepare the `withdrawFunds` transaction.
     Renders the transaction details for the partner to execute via their wallet. Logs activities. Includes Etherscan links.
     </summary>
    <param name="request">The HttpRequest object.</param>
    <param name="pk">The primary key of the Contract from which funds are to be withdrawn.</param>
    <returns>An HttpResponse object rendering the 'withdraw_contract_funds.html' template, potentially including transaction details, or an HttpResponseRedirect on error/invalid state.</returns>
    """
    from django.conf import settings

    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
    
    contract = get_object_or_404(Contract, pk=pk, partner_address=user_eth_address)
    blockchain_service = BlockchainService()

    if not contract.blockchain_contract_id:
        messages.error(request, "Dieser Vertrag wurde noch nicht auf der Blockchain registriert.")
        return redirect('contract_detail', pk=pk)

    if contract.blockchain_status != 'Completed':
        if contract.blockchain_status == 'Created':
            messages.info(request, "Dieser Vertrag muss zuerst signiert werden, bevor Gelder abgehoben werden können.")
        elif contract.blockchain_status == 'Signed':
            messages.info(request, "Der Vertrag muss zuerst vom Ersteller als erfüllt bestätigt werden.")
        else:
            messages.info(request, "Aus diesem Vertrag können keine Gelder abgehoben werden.")
        return redirect('contract_detail', pk=pk)

    network = getattr(settings, 'ETHEREUM_NETWORK', 'sepolia')
    if network == 'mainnet':
        explorer_url = f"https://etherscan.io/address/{blockchain_service.contract_address}"
        tx_explorer_base = "https://etherscan.io/tx/"
    else:
        explorer_url = f"https://{network}.etherscan.io/address/{blockchain_service.contract_address}"
        tx_explorer_base = f"https://{network}.etherscan.io/tx/"

    if request.method == 'POST':
        try:
            tx = blockchain_service.withdrawFunds(
                partner_address=contract.partner_address,
                contract_id=contract.blockchain_contract_id
            )

            ContractActivity.log(
                contract=contract,
                action='blockchain_withdraw',
                user=request.user,
                user_role='partner',
                details="Blockchain-Geldabhebung vorbereitet"
            )

            tx_dict = dict(tx)

            processed_tx = {}
            for key, value in tx_dict.items():
                if isinstance(value, bytes):
                    processed_tx[key] = value.hex()
                else:
                    processed_tx[key] = value

            if 'to' not in processed_tx and blockchain_service.contract_address:
                processed_tx['to'] = blockchain_service.contract_address

            transaction_json = json.dumps(processed_tx)

            return render(request, 'contractsapp/withdraw_contract_funds.html', {
                'contract': contract,
                'transaction': transaction_json,
                'is_submission': True,
                'blockchain_service': blockchain_service,
                'explorer_url': explorer_url,
                'tx_explorer_base': tx_explorer_base
            })
        except Exception as e:
            ContractActivity.log(
                contract=contract,
                action='blockchain_error',
                user=request.user,
                user_role='partner',
                details=f"Fehler bei der Blockchain-Geldabhebung: {str(e)}"
            )

            messages.error(request, f"Fehler bei der Vorbereitung der Blockchain-Geldabhebung: {str(e)}")
            return redirect('contract_detail', pk=pk)

    ContractActivity.log(
        contract=contract,
        action='blockchain_view',
        user=request.user,
        user_role='partner',
        details="Blockchain-Geldabhebungsseite geöffnet"
    )

    return render(request, 'contractsapp/withdraw_contract_funds.html', {
        'contract': contract,
        'blockchain_service': blockchain_service,
        'explorer_url': explorer_url,
        'tx_explorer_base': tx_explorer_base
    })


@login_required
def void_blockchain_contract(request, pk):
    """
    <summary>
     View for the contract creator to initiate the voiding (cancellation) of a contract on the blockchain.
     Ensures the contract is on the blockchain and its status is not 'Completed' or already 'Cancelled'.
     On GET, displays contract details and the voiding form/button.
     On POST, calls the BlockchainService to prepare the `deactivate_contract` transaction.
     Renders the transaction details for the creator to execute via their wallet. Logs activities. Includes Etherscan links.
     </summary>
    <param name="request">The HttpRequest object.</param>
    <param name="pk">The primary key of the Contract to be voided on the blockchain.</param>
    <returns>An HttpResponse object rendering the 'void_blockchain_contract.html' template, potentially including transaction details, or an HttpResponseRedirect on error/invalid state.</returns>
    """
    from django.conf import settings

    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None

    contract = get_object_or_404(Contract, pk=pk, creator_address=user_eth_address)
    blockchain_service = BlockchainService()

    if not contract.blockchain_contract_id:
        messages.error(request, "Dieser Vertrag wurde noch nicht auf der Blockchain registriert.")
        return redirect('contract_detail', pk=pk)

    if contract.blockchain_status == 'Completed':
        messages.error(request, "Abgeschlossene Verträge können nicht nichtig gemacht werden.")
        return redirect('contract_detail', pk=pk)

    if contract.blockchain_status == 'Cancelled':
        messages.info(request, "Dieser Vertrag wurde bereits als nichtig markiert.")
        return redirect('contract_detail', pk=pk)

    network = getattr(settings, 'ETHEREUM_NETWORK', 'sepolia')
    if network == 'mainnet':
        explorer_url = f"https://etherscan.io/address/{blockchain_service.contract_address}"
        tx_explorer_base = "https://etherscan.io/tx/"
    else:
        explorer_url = f"https://{network}.etherscan.io/address/{blockchain_service.contract_address}"
        tx_explorer_base = f"https://{network}.etherscan.io/tx/"

    if request.method == 'POST':
        try:
            tx = blockchain_service.deactivate_contract(
                creator_address=contract.creator_address,
                contract_id=contract.blockchain_contract_id
            )

            ContractActivity.log(
                contract=contract,
                action='blockchain_void',
                user=request.user,
                user_role='creator',
                details="Blockchain-Vertragsnichtigkeit vorbereitet"
            )

            tx_dict = dict(tx)

            processed_tx = {}
            for key, value in tx_dict.items():
                if isinstance(value, bytes):
                    processed_tx[key] = value.hex()
                else:
                    processed_tx[key] = value

            if 'to' not in processed_tx and blockchain_service.contract_address:
                processed_tx['to'] = blockchain_service.contract_address

            transaction_json = json.dumps(processed_tx)

            return render(request, 'contractsapp/void_blockchain_contract.html', {
                'contract': contract,
                'transaction': transaction_json,
                'is_submission': True,
                'blockchain_service': blockchain_service,
                'explorer_url': explorer_url,
                'tx_explorer_base': tx_explorer_base
            })
        except Exception as e:
            ContractActivity.log(
                contract=contract,
                action='blockchain_error',
                user=request.user,
                user_role='creator',
                details=f"Fehler bei der Blockchain-Vertragsnichtigkeit: {str(e)}"
            )

            messages.error(request, f"Fehler bei der Vorbereitung der Blockchain-Vertragsnichtigkeit: {str(e)}")
            return redirect('contract_detail', pk=pk)

    ContractActivity.log(
        contract=contract,
        action='blockchain_view',
        user=request.user,
        user_role='creator',
        details="Blockchain-Vertragsannullierungsseite geöffnet"
    )

    return render(request, 'contractsapp/void_blockchain_contract.html', {
        'contract': contract,
        'blockchain_service': blockchain_service,
        'explorer_url': explorer_url,
        'tx_explorer_base': tx_explorer_base
    })


@login_required
def update_tracking_status(request, pk):
    """
    Manually updates the tracking status for a contract
    """
    contract = get_object_or_404(Contract, pk=pk)
    
    # Check if user is the creator of this contract
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
    if contract.creator_address != user_eth_address:
        messages.error(request, "Sie haben keine Berechtigung, diesen Vertrag zu aktualisieren.")
        return redirect('contract_detail', pk=pk)
    
    # Only update if contract has DHL tracking enabled and a tracking number
    if not contract.has_dhl_tracking or not contract.tracking_number:
        messages.error(request, "Dieser Vertrag hat kein DHL-Tracking aktiviert.")
        return redirect('contract_detail', pk=pk)
    
    # Update tracking status
    tracking_service = DHLTrackingService()
    tracking_info = tracking_service.update_contract_status(contract)
    
    # Create activity log
    ContractActivity.log(
        contract=contract,
        user=request.user,
        action='tracking_updated',
        details=f"Tracking-Status aktualisiert: {contract.package_status}"
    )
    
    messages.success(request, f"Tracking-Status aktualisiert: {contract.package_status}")
    return redirect('contract_detail', pk=pk)


@login_required
def confirm_delivery(request, pk):
    """
    Seller confirms that the package has been delivered correctly
    """
    contract = get_object_or_404(Contract, pk=pk)
    
    # Check if user is the creator (seller) of this contract
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
    if contract.creator_address != user_eth_address:
        messages.error(request, "Sie haben keine Berechtigung, diese Lieferung zu bestätigen.")
        return redirect('contract_detail', pk=pk)
    
    # Only allow confirmation if package is marked as delivered
    if contract.status != 'package_delivered':
        messages.error(request, "Das Paket wurde noch nicht als geliefert markiert.")
        return redirect('contract_detail', pk=pk)
    
    if request.method == 'POST':
        is_confirmed = request.POST.get('is_confirmed') == 'true'
        delivery_notes = request.POST.get('delivery_notes', '')
        
        tracking_service = DHLTrackingService()
        success, message = tracking_service.confirm_delivery(
            contract, 
            confirmed=is_confirmed, 
            notes=delivery_notes
        )
        
        if success and is_confirmed:
            # Initiiere die Blockchain-Transaktion zur Bestätigung der Lieferung
            blockchain_service = BlockchainService()
            try:
                tx_data = blockchain_service.approve_delivery_as_creator(
                    user_eth_address,
                    contract.blockchain_contract_id
                )
                
                # Transaktion wurde vorbereitet (noch nicht auf Blockchain gesendet)
                print(f"Lieferbestätigung vorbereitet: {tx_data}")
                
                if tx_data.get('success'):
                    print(f"Blockchain-Nachricht: {tx_data.get('message')}")
                
                # Create activity log
                ContractActivity.log(
                    contract=contract,
                    user=request.user,
                    user_role='creator',
                    action='delivery_confirmed',
                    details=delivery_notes if delivery_notes else "Keine Anmerkungen"                )                
                messages.success(request, "Lieferungsbestätigung wurde vorbereitet. (Hinweis: Transaktion noch nicht auf Blockchain gesendet)")
                return redirect('contract_detail', pk=pk)
                
            except Exception as e:
                messages.error(request, f"Fehler bei der Blockchain-Transaktion: {str(e)}")
                return redirect('contract_detail', pk=pk)
        elif not is_confirmed:
            # Wenn nicht bestätigt, handle Ablehnung der Lieferung
            ContractActivity.log(
                contract=contract,
                user=request.user,
                user_role='creator',
                action='delivery_rejected',
                details=delivery_notes if delivery_notes else "Keine Anmerkungen"
            )
            messages.success(request, "Lieferung wurde abgelehnt.")
        else:
            messages.error(request, message)
            
        return redirect('contract_detail', pk=pk)
    
    return render(request, 'contractsapp/confirm_delivery.html', {'contract': contract})


@login_required
def add_tracking_number(request, pk):
    """
    Add or update the tracking number for a contract
    """
    contract = get_object_or_404(Contract, pk=pk)
    
    user_eth_address = request.user.ethereum_address.lower() if request.user.ethereum_address else None
    is_partner = contract.partner_address == user_eth_address
    
    if not contract.blockchain_contract_id:
        messages.error(request, "Tracking-Nummern können erst eingegeben werden, wenn der Vertrag auf der Blockchain ist.")
        return redirect('contract_detail', pk=pk)
    
    if not is_partner:
        messages.error(request, "Nur der Vertragspartner kann Tracking-Nummern hinzufügen.")
        return redirect('contract_detail', pk=pk)
    
    # GET request - show the form
    if request.method == 'GET':
        return render(request, 'contractsapp/add_tracking.html', {'contract': contract})
    
    # POST request - process the tracking number
    if request.method == 'POST':
        tracking_number = request.POST.get('tracking_number', '')
        submit_to_blockchain = request.POST.get('submit_to_blockchain', 'false') == 'true'
        
        if not tracking_number:
            messages.error(request, "Bitte geben Sie eine gültige Tracking-Nummer ein.")
            return render(request, 'contractsapp/add_tracking.html', {'contract': contract})
        
        if submit_to_blockchain:
            # Erstelle einen Hash der Tracking-Nummer für die Blockchain
            tracking_service = DHLTrackingService()
            tracking_hash = tracking_service.generate_tracking_hash(tracking_number)
            
            # Initiiere die Blockchain-Transaktion (OHNE Datenbank-Update)
            # Die Tracking-Nummer wird erst nach erfolgreicher Transaktion gespeichert
            blockchain_service = BlockchainService()
            try:
                tx_data = blockchain_service.set_delivery_tracking(
                    user_eth_address, 
                    contract.blockchain_contract_id, 
                    tracking_hash
                )
                  # Render the template with transaction data for MetaMask signing
                # NOTE: Tracking number is NOT saved to database yet - only after successful blockchain transaction
                context = {
                    'contract': contract,
                    'tracking_number': tracking_number,  # Pass to template for later DB save
                    'is_submission': True,
                    'transaction': json.dumps(tx_data.get('transaction')),
                    'blockchain_service': blockchain_service,
                }
                return render(request, 'contractsapp/add_tracking.html', context)
                
            except Exception as e:
                messages.error(request, f"Fehler bei der Blockchain-Transaktion: {str(e)}")
                return render(request, 'contractsapp/add_tracking.html', {'contract': contract})
        else:
            # Just show the form with blockchain submission option
            context = {
                'contract': contract,
                'tracking_number': tracking_number,
                'show_blockchain_form': True,
            }
            return render(request, 'contractsapp/add_tracking.html', context)


@login_required
def prepare_set_oracle(request):
    """
    View to prepare the setOracle transaction for the smart contract.
    """
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Nur Administratoren können das Oracle setzen.'})
    
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Ungültige Anfrage'})
    
    deployer_address = request.POST.get('deployer_address')
    oracle_address = request.POST.get('oracle_address')
    contract_address = request.POST.get('contract_address')
    
    if not deployer_address or not oracle_address or not contract_address:
        return JsonResponse({'success': False, 'message': 'Alle Adressen sind erforderlich'})
    
    # Validate addresses
    if not (deployer_address.startswith('0x') and oracle_address.startswith('0x') and contract_address.startswith('0x')):
        return JsonResponse({'success': False, 'message': 'Ungültige Ethereum-Adressen'})
    
    try:
        blockchain_service = BlockchainService()
        
        # Aktualisiere die Contract-Adresse im Service
        blockchain_service.set_contract_address(contract_address)
        
        # Bereite die setOracle-Transaktion vor
        tx = blockchain_service.set_oracle(deployer_address, oracle_address)
        
        # Konvertiere Bytes zu Hex für JSON-Serialisierung
        processed_tx = {}
        for key, value in tx.items():
            if isinstance(value, bytes):
                processed_tx[key] = value.hex()
            else:
                processed_tx[key] = value
        
        transaction_json = json.dumps(processed_tx)
        
        return JsonResponse({
            'success': True,
            'transaction': transaction_json
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Fehler beim Vorbereiten der Oracle-Transaktion: {str(e)}'
        })