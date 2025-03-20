from django import forms
from .models import Contract

class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ['title', 'pdf_file', 'creator_address', 'partner_address']
        widgets = {
            'creator_address': forms.TextInput(attrs={
                'placeholder': '0x...',
                'class': 'form-control eth-address-input'
            }),
            'partner_address': forms.TextInput(attrs={
                'placeholder': '0x...',
                'class': 'form-control eth-address-input'
            }),
        }