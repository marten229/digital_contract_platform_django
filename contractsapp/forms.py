from django import forms
from .models import Contract

class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ['title', 'pdf_file', 'creator_address', 'partner_name', 'partner_email']
        widgets = {
            'creator_address': forms.TextInput(attrs={
                'placeholder': '0x...',
                'class': 'form-control eth-address-input'
            }),
            'partner_name': forms.TextInput(attrs={
                'placeholder': 'Max Mustermann',
                'class': 'form-control'
            }),
            'partner_email': forms.EmailInput(attrs={
                'placeholder': 'partner@example.com',
                'class': 'form-control'
            }),
        }