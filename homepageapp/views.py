from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

def homepage_view(request):
    """Render the homepage or redirect to dashboard if user is authenticated"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'homepageapp/homepage.html')

@login_required
def dashboard_view(request):
    """Render the dashboard for authenticated users"""
    return render(request, 'homepageapp/dashboard.html')