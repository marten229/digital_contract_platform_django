from django.contrib import admin
from .models import Contract, ContractActivity, CreatedPDF

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['title', 'creator_address', 'partner_address', 'status', 'uploaded_at']
    list_filter = ['status', 'uploaded_at', 'has_dhl_tracking']
    search_fields = ['title', 'creator_address', 'partner_address']
    readonly_fields = ['uploaded_at', 'pdf_hash']

@admin.register(ContractActivity)
class ContractActivityAdmin(admin.ModelAdmin):
    list_display = ['contract', 'action', 'timestamp', 'user_role']
    list_filter = ['action', 'timestamp', 'user_role']
    search_fields = ['contract__title', 'details']
    readonly_fields = ['timestamp']

@admin.register(CreatedPDF)
class CreatedPDFAdmin(admin.ModelAdmin):
    list_display = ['title', 'creator', 'contract_type', 'amount_eth', 'created_at']
    list_filter = ['contract_type', 'created_at']
    search_fields = ['title', 'creator__username']
    readonly_fields = ['created_at', 'updated_at']
