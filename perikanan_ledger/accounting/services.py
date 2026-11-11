"""Accounting logic shared by HTML reports and Excel exports.

No report stores a second copy of a journal amount. All calculations start from
Account.opening_balance and immutable JournalLine records.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from .models import (Account, BusinessProfile, InventoryAllocation, InventoryLayer,
                     InventoryMovement, JournalEntry, JournalLine, Party, ZERO)

CENT = Decimal('0.01')


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def report_balances(as_of=None, include_adjustments=True):
    """Rows with signed debit-minus-credit balances as of inclusive date."""
    entries = JournalLine.objects.all()
    if as_of:
        entries = entries.filter(entry__date__lte=as_of)
    if not include_adjustments:
        entries = entries.exclude(entry__kind=JournalEntry.Kind.ADJUSTMENT)
    sums = {
        r['account_id']: (r['d'] or ZERO, r['c'] or ZERO)
        for r in entries.order_by().values('account_id').annotate(d=Sum('debit'), c=Sum('credit'))
    }
    rows = []
    for account in Account.objects.filter(is_header=False).order_by('code'):
        opening_net = account.opening_balance if account.normal_balance == 'D' else -account.opening_balance
        d, c = sums.get(account.id, (ZERO, ZERO))
        net = opening_net + d - c
        rows.append({
            'account': account, 'opening': account.opening_balance, 'net': net,
            'debit': max(net, ZERO), 'credit': max(-net, ZERO),
        })
    return rows


def period_totals(as_of=None):
    rows = report_balances(as_of)
    cats = defaultdict(list)
    for row in rows:
        cats[row['account'].category].append(row)
    def signed(cat):
        return sum((row['net'] for row in cats[cat]), ZERO)
    revenue = -signed('REVENUE') - signed('OTHER_INCOME')
    costs = signed('COGS') + signed('EXPENSE') + signed('OTHER_EXPENSE')
    profit = revenue - costs
    assets = signed('ASSET')
    liabilities = -signed('LIABILITY')
    equity = -signed('EQUITY')
    return {
        'rows': rows, 'groups': dict(cats), 'revenue': revenue, 'costs': costs,
        'profit': profit, 'assets': assets, 'liabilities': liabilities,
        'equity': equity, 'equity_with_profit': equity + profit,
        'difference': assets - liabilities - equity - profit,
    }


def worksheet(as_of=None):
    base = {x['account'].id: x for x in report_balances(as_of, include_adjustments=False)}
    final = report_balances(as_of, include_adjustments=True)
    rows = []
    totals = {key: ZERO for key in ('trial_d', 'trial_c', 'adj_d', 'adj_c',
        'adjusted_d', 'adjusted_c', 'income_d', 'income_c', 'balance_d', 'balance_c')}
    for item in final:
        account = item['account']
        initial = base[account.id]['net']
        adjustment = item['net'] - initial
        income = account.report_type == 'LR'
        row = {
            'account': account, 'trial_d': max(initial, ZERO), 'trial_c': max(-initial, ZERO),
            'adj_d': max(adjustment, ZERO), 'adj_c': max(-adjustment, ZERO),
            'adjusted_d': item['debit'], 'adjusted_c': item['credit'],
            'income_d': item['debit'] if income else ZERO,
            'income_c': item['credit'] if income else ZERO,
            'balance_d': item['debit'] if not income else ZERO,
            'balance_c': item['credit'] if not income else ZERO,
        }
        rows.append(row)
        for key in totals:
            totals[key] += row[key]
    # To close a 10-column worksheet, show profit as separate balancing row.
    profit = totals['income_c'] - totals['income_d']
    return {'rows': rows, 'totals': totals, 'profit': profit,
            'check_trial': totals['trial_d'] - totals['trial_c'],
            'check_adjusted': totals['adjusted_d'] - totals['adjusted_c']}


def ledger(account, start=None, end=None):
    qs = JournalLine.objects.filter(account=account).select_related('entry', 'party').order_by('entry__date', 'entry_id', 'id')
    opening = account.opening_balance if account.normal_balance == 'D' else -account.opening_balance
    if start:
        for line in qs.filter(entry__date__lt=start):
            opening += line.debit - line.credit
        qs = qs.filter(entry__date__gte=start)
    if end:
        qs = qs.filter(entry__date__lte=end)
    running = opening
    records = []
    for line in qs:
        running += line.debit - line.credit
        records.append({'date': line.entry.date, 'reference': line.entry.reference,
            'description': line.description or line.entry.description,
            'party': line.party, 'debit': line.debit, 'credit': line.credit,
            'balance': running if account.normal_balance == 'D' else -running})
    return {'opening': opening if account.normal_balance == 'D' else -opening,
            'records': records,
            'closing': running if account.normal_balance == 'D' else -running}


def subsidiary(party, start=None, end=None):
    account_code = '1140' if party.kind == 'CUSTOMER' else '2110'
    qs = JournalLine.objects.filter(party=party, account__code=account_code).select_related('entry').order_by('entry__date', 'entry_id', 'id')
    running = party.opening_balance
    def natural_delta(line):
        return line.debit - line.credit if party.kind == 'CUSTOMER' else line.credit - line.debit
    if start:
        for line in qs.filter(entry__date__lt=start):
            running += natural_delta(line)
        qs = qs.filter(entry__date__gte=start)
    if end:
        qs = qs.filter(entry__date__lte=end)
    opening = running
    records = []
    for line in qs:
        running += natural_delta(line)
        records.append({'date': line.entry.date, 'reference': line.entry.reference,
            'description': line.description or line.entry.description,
            'debit': line.debit, 'credit': line.credit, 'balance': running})
    return {'opening': opening, 'records': records, 'closing': running}


def stock_card(product, end=None):
    qs = InventoryMovement.objects.filter(product=product).order_by('date', 'id')
    if end:
        qs = qs.filter(date__lte=end)
    running_qty = Decimal('0.000')
    running_value = ZERO
    records = []
    for m in qs:
        if m.kind in ('OPENING', 'IN'):
            running_qty += m.quantity
            running_value += m.cost_amount
        else:
            running_qty -= m.quantity
            running_value -= m.cost_amount
        records.append({'movement': m, 'in_qty': m.quantity if m.kind != 'OUT' else None,
            'out_qty': m.quantity if m.kind == 'OUT' else None,
            'in_value': m.cost_amount if m.kind != 'OUT' else None,
            'out_value': m.cost_amount if m.kind == 'OUT' else None,
            'qty': running_qty, 'value': running_value,
            'unit_cost': money(running_value / running_qty) if running_qty else ZERO})
    return {'records': records, 'qty': running_qty, 'value': running_value}


@transaction.atomic
def create_opening_stock(product, quantity, unit_cost, date_value):
    if quantity <= 0:
        return None
    if InventoryMovement.objects.filter(product=product).exists():
        raise ValidationError('Saldo awal hanya dapat dibuat sebelum transaksi stok lainnya.')
    total = money(quantity * unit_cost)
    movement = InventoryMovement.objects.create(product=product, date=date_value,
        reference=f'AWAL-{product.code}', kind='OPENING', description='Saldo awal persediaan',
        quantity=quantity, unit_price=unit_cost, cost_amount=total)
    InventoryLayer.objects.create(product=product, movement=movement,
        unit_cost=unit_cost, received_quantity=quantity, remaining_quantity=quantity)
    return movement


@transaction.atomic
def create_stock_movement(*, product, date_value, reference, kind, quantity,
                          unit_price, settlement_account, description, party=None, user=None):
    """FIFO outflow and matching double-entry journal, committed together.

    Dates cannot be backdated relative to other stock movements, because doing so
    would invalidate previously issued FIFO allocations.
    """
    product = type(product).objects.select_for_update().get(pk=product.pk)
    last = InventoryMovement.objects.filter(product=product).order_by('-date', '-id').first()
    if last and date_value < last.date:
        raise ValidationError('Tanggal lebih lama daripada mutasi terakhir barang. FIFO tidak mengizinkan backdate.')
    if InventoryMovement.objects.filter(product=product, reference=reference).exists():
        raise ValidationError('Nomor bukti sudah dipakai untuk barang ini.')
    if JournalEntry.objects.filter(date=date_value, reference=reference).exists():
        raise ValidationError('Nomor bukti jurnal sudah dipakai pada tanggal yang sama.')
    if not settlement_account.is_active or settlement_account.is_header:
        raise ValidationError('Akun pembayaran tidak aktif atau merupakan akun header.')
    if quantity <= 0 or unit_price < 0:
        raise ValidationError('Kuantitas harus positif dan harga tidak boleh negatif.')
    profile = BusinessProfile.current()
    codes = [profile.inventory_account_code, profile.cogs_account_code, profile.sales_account_code]
    accounts = {a.code: a for a in Account.objects.filter(code__in=codes, is_header=False, is_active=True)}
    if not all(c in accounts for c in codes):
        raise ValidationError('Akun Persediaan, HPP, atau Penjualan belum tersedia. Periksa Pengaturan.')
    inventory, cogs, revenue = [accounts[c] for c in codes]
    if len(set(codes)) != 3 or settlement_account.pk in {inventory.pk, cogs.pk, revenue.pk}:
        raise ValidationError('Akun pembayaran harus berbeda dari akun Persediaan, HPP, dan Penjualan.')
    if settlement_account.code in ('1140', '2110'):
        required = 'CUSTOMER' if settlement_account.code == '1140' else 'SUPPLIER'
        if not party or party.kind != required:
            raise ValidationError(f'Akun {settlement_account.code} memerlukan kode relasi yang sesuai.')
    elif party:
        raise ValidationError('Relasi hanya diisi saat pembayaran melalui Piutang (1140) atau Utang (2110).')
    total_price = money(quantity * unit_price)
    if kind == 'IN':
        if settlement_account.code == '1140':
            raise ValidationError('Pembelian kredit gunakan akun Utang 2110, bukan Piutang 1140.')
        cost = total_price
        allocations = []
    elif kind == 'OUT':
        if settlement_account.code == '2110':
            raise ValidationError('Penjualan kredit gunakan Piutang 1140, bukan Utang 2110.')
        remaining = quantity
        allocations = []
        for layer in InventoryLayer.objects.select_for_update().filter(
                product=product, remaining_quantity__gt=0).order_by('movement__date', 'movement__id', 'id'):
            taken = min(remaining, layer.remaining_quantity)
            allocations.append((layer, taken, money(taken * layer.unit_cost)))
            remaining -= taken
            if remaining == 0:
                break
        if remaining > 0:
            raise ValidationError('Stok tidak cukup. Tidak ada transaksi stok negatif.')
        cost = sum((x[2] for x in allocations), ZERO)
    else:
        raise ValidationError('Jenis mutasi tidak dikenal.')
    journal = JournalEntry.objects.create(date=date_value, reference=reference,
        description=description, kind='INVENTORY', created_by=user)
    movement = InventoryMovement.objects.create(
        product=product, date=date_value, reference=reference, description=description,
        kind=kind, quantity=quantity, unit_price=unit_price, cost_amount=cost,
        sales_amount=total_price if kind == 'OUT' else ZERO, entry=journal,
    )
    def line(account, debit=ZERO, credit=ZERO, relation=None):
        if debit == 0 and credit == 0:
            return
        obj = JournalLine(entry=journal, account=account, party=relation,
                          debit=debit, credit=credit, description=f'{product.code}: {description}')
        obj.full_clean()
        obj.save()
    if kind == 'IN':
        if total_price <= 0:
            raise ValidationError('Harga pembelian harus lebih dari nol.')
        InventoryLayer.objects.create(product=product, movement=movement,
            unit_cost=unit_price, received_quantity=quantity, remaining_quantity=quantity)
        line(inventory, debit=total_price)
        line(settlement_account, credit=total_price, relation=party)
    else:
        if total_price <= 0:
            raise ValidationError('Harga penjualan harus lebih dari nol.')
        line(settlement_account, debit=total_price, relation=party)
        line(revenue, credit=total_price)
        if cost:
            line(cogs, debit=cost)
            line(inventory, credit=cost)
        for layer, taken, amount in allocations:
            layer.remaining_quantity -= taken
            layer.save(update_fields=['remaining_quantity'])
            InventoryAllocation.objects.create(outgoing=movement, layer=layer,
                                               quantity=taken, amount=amount)
    return movement
