from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_page, name='login_page'),
    path('api/get_nonce/', views.get_nonce, name='get_nonce'),
    path('api/verify_signature/', views.verify_signature, name='verify_signature'),
    path('api/logout/', views.logout_view, name='logout'),
]