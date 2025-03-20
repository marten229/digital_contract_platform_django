from django.urls import path
from .views import contract_upload, contract_detail, add_signature, contract_list, contract_signing

urlpatterns = [
    path('', contract_upload, name='contract_upload'),
    path('list/', contract_list, name='contract_list'),
    path('contract/<int:pk>/', contract_detail, name='contract_detail'),
    path('contract/<int:pk>/sign/', contract_signing, name='contract_signing'),
    path('contract/<int:pk>/add_signature/', add_signature, name='add_signature'),
]
