from django import forms
from django.contrib.auth import get_user_model
from .models import Contract

User = get_user_model()

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
    partner_address = forms.CharField(
        label="Ethereum-Adresse des Partners",
        required=True,
        max_length=42,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '0x...'
        })
    )

    class Meta:
        model = Contract
        fields = ['title', 'pdf_file', 'contract_amount_eth']
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
        # Prevent saving the creator field to avoid the "creator_id" database error
        exclude = getattr(self._meta, 'exclude', None)
        if exclude is None:
            self._meta.exclude = ['creator']
        else:
            self._meta.exclude = list(exclude) + ['creator']
        
        instance = super().save(commit=False)
        
        # Save the contract amount in Wei
        if 'contract_amount' in self.cleaned_data:
            instance.contract_amount = self.cleaned_data['contract_amount']
        
        # Setze die Ethereum-Adresse des Partners direkt aus dem Formularfeld
        partner_addr = self.cleaned_data.get('partner_address', '').lower()
        instance.partner_address = partner_addr
        
        # Versuche, einen Benutzer mit dieser Ethereum-Adresse zu finden
        partner_user = User.objects.filter(ethereum_address__iexact=partner_addr).first()
        
        # Wenn ein Benutzer gefunden wurde, setze ihn als Partner
        if partner_user:
            instance.partner = partner_user
        
        if commit:
            instance.save()
            
        return instance