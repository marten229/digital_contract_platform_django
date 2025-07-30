import json
import random
import string
from eth_account.messages import encode_defunct
from web3 import Web3
from web3.auto import w3
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import login, logout
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Web3User

def generate_nonce():
    """Generate a random nonce string"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))

@require_http_methods(["GET"])
def get_nonce(request):
    """Generate or retrieve a nonce for the given ethereum address"""
    eth_address = request.GET.get('address', '').lower()
    
    if not eth_address or not Web3.is_address(eth_address):
        return JsonResponse({'error': 'Invalid Ethereum address'}, status=400)
    
    # Get or create user with this ethereum address
    try:
        user = Web3User.objects.get(ethereum_address=eth_address)
    except Web3User.DoesNotExist:
        # Create a new user with this address
        username = f"user_{eth_address[:8]}"
        user = Web3User(
            username=username,
            ethereum_address=eth_address,
        )
    
    # Generate new nonce
    nonce = generate_nonce()
    user.nonce = nonce
    user.save()
    
    return JsonResponse({'nonce': nonce})

@csrf_exempt
@require_http_methods(["POST"])
def verify_signature(request):
    """Verify the signature and login the user"""
    data = json.loads(request.body)
    address = data.get('address', '').lower()
    signature = data.get('signature', '')
    
    try:
        # Get the user and their nonce
        user = Web3User.objects.get(ethereum_address=address)
        nonce = user.nonce
        
        # Create the message that was signed
        message = f"Sign this message to authenticate with our app: {nonce}"
        message_encoded = encode_defunct(text=message)
        
        # Verify the signature
        recovered_address = w3.eth.account.recover_message(message_encoded, signature=signature)
        
        if recovered_address.lower() == address.lower():
            # Valid signature, log in the user
            login(request, user)
            # Generate new nonce for next login
            user.nonce = generate_nonce()
            user.save()
            
            messages.success(request, "Sie wurden erfolgreich angemeldet!")
            
            return JsonResponse({
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'address': user.ethereum_address
                }
            })
        else:
            return JsonResponse({'error': 'Invalid signature'}, status=401)
            
    except Web3User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["POST"])
def logout_view(request):
    """Logout the user and redirect to homepage"""
    logout(request)
    messages.success(request, "Sie wurden erfolgreich abgemeldet!")
    return redirect('homepage')

def login_page(request):
    """Render the login page"""
    return render(request, 'authenticationapp/login.html', {'show_menu': False})