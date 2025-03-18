from django.shortcuts import render

def homepage_view(request):
    """Render the homepage"""
    return render(request, 'homepageapp/homepage.html')