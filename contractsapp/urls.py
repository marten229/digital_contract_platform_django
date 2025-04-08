from django.urls import path
from . import views

urlpatterns = [
    path('', views.contract_upload, name='contract_upload'),
    path('list/', views.contract_list, name='contract_list'),
    path('contract/<int:pk>/', views.contract_detail, name='contract_detail'),
    path('contract/<int:pk>/sign/', views.contract_signing, name='contract_signing'),
    path('contract/<int:pk>/success/', views.contract_signing_success, name='contract_signing_success'),
    path('contract/<int:pk>/verify/', views.verify_partner, name='verify_partner'),
    path('contract/<int:pk>/add_signature/', views.add_signature, name='add_signature'),
    path('contract/<int:pk>/configure/', views.contract_configuration, name='contract_configuration'),
    path('contract/<int:pk>/finish_configuration/', views.finish_contract_configuration, name='finish_contract_configuration'),
    path('contract/<int:pk>/submit_to_blockchain/', views.submit_to_blockchain, name='submit_to_blockchain'),
    path('update-blockchain-status/<int:pk>/', views.update_blockchain_status, name='update_blockchain_status'),
    path('withdraw-funds/<int:pk>/', views.withdraw_funds, name='withdraw_funds'),
    
    # URLs für Smart Contract-Bereitstellung
    path('deploy-contract/', views.deploy_contract, name='deploy_contract'),
    path('update-contract-address/', views.update_contract_address, name='update_contract_address'),
]
