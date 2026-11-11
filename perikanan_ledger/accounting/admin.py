"""Audit-oriented admin: financial records are read-only here.

Create transactions through the validated application UI to preserve posting/FIFO.
"""
from django.contrib import admin
from .models import (Account, Party, Product, BusinessProfile, JournalEntry, JournalLine,
                     InventoryMovement, InventoryLayer, InventoryAllocation)


class ReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Account)
class AccountAdmin(ReadOnlyAdmin):
    list_display = ('code', 'name', 'category', 'normal_balance', 'opening_balance', 'is_header')
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'name')


@admin.register(Party)
class PartyAdmin(ReadOnlyAdmin):
    list_display = ('code', 'name', 'kind', 'opening_balance')
    search_fields = ('code', 'name')


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    readonly_fields = ('account', 'party', 'description', 'debit', 'credit')
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(JournalEntry)
class JournalAdmin(ReadOnlyAdmin):
    list_display = ('date', 'reference', 'description', 'kind')
    inlines = [JournalLineInline]


@admin.register(Product)
class ProductAdmin(ReadOnlyAdmin):
    list_display = ('code', 'name', 'unit', 'sale_price', 'is_active')


@admin.register(InventoryMovement)
class InventoryMovementAdmin(ReadOnlyAdmin):
    list_display = ('date', 'reference', 'product', 'kind', 'quantity', 'cost_amount')


@admin.register(InventoryLayer)
class InventoryLayerAdmin(ReadOnlyAdmin):
    list_display = ('product', 'movement', 'received_quantity', 'remaining_quantity', 'unit_cost')


@admin.register(InventoryAllocation)
class InventoryAllocationAdmin(ReadOnlyAdmin):
    list_display = ('outgoing', 'layer', 'quantity', 'amount')


@admin.register(BusinessProfile)
class BusinessAdmin(ReadOnlyAdmin):
    list_display = ('name', 'subtitle', 'owner', 'email')
