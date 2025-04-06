from django import forms
from .models import Contract

class ContractForm(forms.ModelForm):
    contract_amount_eth = forms.DecimalField(
        label="Vertragsbetrag (ETH)",
        required=True,
        decimal_places=18,
        max_digits=36,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.0',
            'step': '0.01'
        }),
    )

    class Meta:
        model = Contract
        fields = ['title', 'pdf_file', 'creator_address', 'partner_name', 'partner_email', 'partner_address', 'contract_amount_eth']
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
            'partner_address': forms.TextInput(attrs={
                'placeholder': '0x...',
                'class': 'form-control eth-address-input',
                'required': True
            }),
        }
        
    def clean(self):
        cleaned_data = super().clean()
        amount_eth = cleaned_data.get('contract_amount_eth')
        
        # Convert ETH to Wei for blockchain storage
        if amount_eth:
            # 1 ETH = 10^18 Wei
            amount_wei = int(amount_eth * 10**18)
            cleaned_data['contract_amount'] = amount_wei
        
        return cleaned_data
        
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Save the contract amount in Wei
        if 'contract_amount' in self.cleaned_data:
            instance.contract_amount = self.cleaned_data['contract_amount']
            
        if commit:
            instance.save()
            
        return instance