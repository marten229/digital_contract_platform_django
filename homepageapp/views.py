from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from contractsapp.models import Contract, ContractActivity

def homepage_view(request):
    return render(request, 'homepageapp/homepage.html')

@login_required
def dashboard_view(request):
    """Render the dashboard for authenticated users"""
    
    # Alle Verträge, bei denen der Benutzer der Ersteller oder Partner ist
    user_contracts = Contract.objects.filter(
        Q(creator_address=request.user.ethereum_address) | 
        Q(partner_address=request.user.ethereum_address)
    )
    
    # Die neuesten Aktivitäten für diese Verträge laden
    recent_activities = ContractActivity.objects.filter(
        contract__in=user_contracts
    ).order_by('-timestamp')[:10]  # Nur die 10 neuesten Aktivitäten
    
    context = {
        'recent_activities': recent_activities,
        'has_activities': recent_activities.exists()
    }
    
    return render(request, 'homepageapp/dashboard.html', context)