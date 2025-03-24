from django.urls import path
from .views import (
    contract_upload, 
    contract_detail, 
    add_signature, 
    contract_list, 
    contract_signing,
    contract_configuration,
    finish_contract_configuration
)

urlpatterns = [
    path('', contract_upload, name='contract_upload'),
    path('list/', contract_list, name='contract_list'),
    path('contract/<int:pk>/', contract_detail, name='contract_detail'),
    path('contract/<int:pk>/sign/', contract_signing, name='contract_signing'),
    path('contract/<int:pk>/add_signature/', add_signature, name='add_signature'),
    path('contract/<int:pk>/configure/', contract_configuration, name='contract_configuration'),
    path('contract/<int:pk>/finish_configuration/', finish_contract_configuration, name='finish_contract_configuration'),
]
