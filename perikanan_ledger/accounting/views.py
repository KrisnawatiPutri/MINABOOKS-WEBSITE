from collections import defaultdict
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .forms import (AccountForm, JournalEntryForm, JournalLineFormSet,
                    MovementForm, PartyForm, ProductForm, ProfileForm)
from .models import (Account, BusinessProfile, InventoryLayer, InventoryMovement,
                     JournalEntry, JournalLine, Party, Product, ZERO)
from .services import (create_opening_stock, create_stock_movement, ledger,
                       period_totals, report_balances, stock_card, subsidiary, worksheet)


def cutoff(request, key='to'):
    try:
        return date.fromisoformat(request.GET[key])
    except (KeyError, ValueError):
        return timezone.localdate()


def optional_date(request, key='from'):
    try:
        return date.fromisoformat(request.GET[key])
    except (KeyError, ValueError):
        return None


def field_errors(form):
    return '; '.join(str(e) for e in form.non_field_errors())


@login_required
def dashboard(request):
    as_of = cutoff(request)
    totals = period_totals(as_of)
    products = Product.objects.count()
    stock = InventoryLayer.objects.filter(remaining_quantity__gt=0).aggregate(q=Sum('remaining_quantity'))['q'] or 0
    recent = JournalEntry.objects.filter(date__lte=as_of).prefetch_related('lines').order_by('-date', '-id')[:6]
    journals = JournalEntry.objects.filter(date__lte=as_of).count()
    # Last six months: amount of transactions during each month, not accumulated balances.
    months = []
    current = as_of.year * 12 + as_of.month - 1
    for offset in range(5, -1, -1):
        x = current - offset
        y, m = divmod(x, 12)
        months.append((date(y, m + 1, 1), y, m + 1))
    chart = {'labels': [], 'revenue': [], 'costs': []}
    for start, y, m in months:
        q = JournalLine.objects.filter(entry__date__year=y, entry__date__month=m,
             entry__date__lte=as_of).values('account__category').annotate(d=Sum('debit'), c=Sum('credit'))
        by_type = {r['account__category']: (r['d'] or ZERO, r['c'] or ZERO) for r in q}
        rev = sum((by_type.get(k, (ZERO, ZERO))[1] - by_type.get(k, (ZERO, ZERO))[0]
                   for k in ('REVENUE', 'OTHER_INCOME')), ZERO)
        cost = sum((by_type.get(k, (ZERO, ZERO))[0] - by_type.get(k, (ZERO, ZERO))[1]
                    for k in ('COGS', 'EXPENSE', 'OTHER_EXPENSE')), ZERO)
        chart['labels'].append(start.strftime('%b %Y'))
        chart['revenue'].append(float(rev))
        chart['costs'].append(float(cost))
    return render(request, 'accounting/dashboard.html', {
        'title': 'Dashboard', 'as_of': as_of, 'totals': totals,
        'product_count': products, 'stock_count': stock, 'journal_count': journals,
        'recent': recent, 'chart': chart,
    })


@login_required
def accounts(request):
    return render(request, 'accounting/accounts.html', {
        'title': 'Daftar Akun', 'rows': Account.objects.all(),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def account_form(request, pk=None):
    obj = get_object_or_404(Account, pk=pk) if pk else None
    form = AccountForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Daftar akun berhasil disimpan.')
        return redirect('accounts')
    return render(request, 'accounting/form_page.html', {
        'title': 'Ubah Akun' if obj else 'Tambah Akun', 'form': form, 'back_url': reverse('accounts'),
        'helper': 'Saldo awal bertanda positif mengikuti saldo normal. Gunakan negatif untuk akun kontra.'})


@login_required
def parties(request):
    return render(request, 'accounting/parties.html', {'title': 'Kode Pembantu', 'rows': Party.objects.all()})


@login_required
@require_http_methods(['GET', 'POST'])
def party_form(request, pk=None):
    obj = get_object_or_404(Party, pk=pk) if pk else None
    form = PartyForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Data relasi berhasil disimpan.')
        return redirect('parties')
    return render(request, 'accounting/form_page.html', {
        'title': 'Ubah Relasi' if obj else 'Tambah Relasi', 'form': form, 'back_url': reverse('parties'),
        'helper': 'Pelanggan untuk piutang (1140), pemasok untuk utang (2110).'})


@login_required
def journal_list(request):
    qs = JournalEntry.objects.prefetch_related('lines').exclude(kind=JournalEntry.Kind.ADJUSTMENT)
    start = optional_date(request)
    end = cutoff(request)
    if start:
        qs = qs.filter(date__gte=start)
    qs = qs.filter(date__lte=end)
    return render(request, 'accounting/journal_list.html', {
        'title': 'Jurnal Umum', 'rows': qs[:1000], 'start': start, 'end': end,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def journal_new(request):
    instance = JournalEntry(kind=JournalEntry.Kind.GENERAL)
    form = JournalEntryForm(request.POST or None, instance=instance)
    formset = JournalLineFormSet(request.POST or None, instance=instance, prefix='lines')
    form.fields.pop('kind', None)
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        try:
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.kind = JournalEntry.Kind.GENERAL
                obj.created_by = request.user
                obj.save()
                formset.instance = obj
                formset.save()
            messages.success(request, 'Jurnal berhasil dicatat. Buku besar dan laporan diperbarui otomatis.')
            return redirect('journal_detail', pk=obj.pk)
        except (IntegrityError, ValidationError) as exc:
            form.add_error(None, str(exc))
    return render(request, 'accounting/journal_form.html', {
        'title': 'Tambah Jurnal Umum', 'form': form, 'formset': formset,
        'back_url': reverse('journal_list'), 'journal_type': 'umum',
    })


@login_required
def adjustment_list(request):
    qs = JournalEntry.objects.prefetch_related('lines').filter(kind=JournalEntry.Kind.ADJUSTMENT)
    start, end = optional_date(request), cutoff(request)
    if start:
        qs = qs.filter(date__gte=start)
    qs = qs.filter(date__lte=end)
    return render(request, 'accounting/journal_list.html', {
        'title': 'Jurnal Penyesuaian', 'rows': qs[:1000], 'start': start,
        'end': end, 'is_adjustment': True,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def adjustment_new(request):
    instance = JournalEntry(kind=JournalEntry.Kind.ADJUSTMENT)
    form = JournalEntryForm(request.POST or None, instance=instance)
    form.fields.pop('kind', None)
    formset = JournalLineFormSet(request.POST or None, instance=instance, prefix='lines')
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        try:
            with transaction.atomic():
                obj = form.save(commit=False)
                # Forced server-side: a POST payload cannot switch journal types.
                obj.kind = JournalEntry.Kind.ADJUSTMENT
                obj.created_by = request.user
                obj.save()
                formset.instance = obj
                formset.save()
            messages.success(request, 'Penyesuaian berhasil diposting ke neraca lajur dan laporan.')
            return redirect('journal_detail', pk=obj.pk)
        except (IntegrityError, ValidationError) as exc:
            form.add_error(None, str(exc))
    return render(request, 'accounting/journal_form.html', {
        'title': 'Tambah Jurnal Penyesuaian', 'form': form, 'formset': formset,
        'back_url': reverse('adjustment_list'), 'journal_type': 'penyesuaian',
    })


@login_required
def journal_detail(request, pk):
    obj = get_object_or_404(JournalEntry.objects.prefetch_related('lines__account', 'lines__party'), pk=pk)
    return render(request, 'accounting/journal_detail.html', {'title': obj.reference, 'obj': obj,
        'back_url': reverse('adjustment_list' if obj.kind == JournalEntry.Kind.ADJUSTMENT else 'journal_list')})


@login_required
def ledger_view(request):
    account = Account.objects.filter(pk=request.GET.get('account'), is_header=False).first() if request.GET.get('account', '').isdigit() else None
    start, end = optional_date(request), cutoff(request)
    data = ledger(account, start, end) if account else None
    return render(request, 'accounting/ledger.html', {
        'title': 'Buku Besar', 'account': account, 'accounts': Account.objects.filter(is_header=False),
        'data': data, 'start': start, 'end': end,
    })


@login_required
def subsidiary_view(request):
    party = Party.objects.filter(pk=request.GET.get('party')).first() if request.GET.get('party', '').isdigit() else None
    start, end = optional_date(request), cutoff(request)
    data = subsidiary(party, start, end) if party else None
    return render(request, 'accounting/subsidiary.html', {
        'title': 'Buku Besar Pembantu', 'party': party, 'parties': Party.objects.all(),
        'data': data, 'start': start, 'end': end,
    })


@login_required
def trial_balance(request):
    as_of = cutoff(request)
    rows = report_balances(as_of)
    totals = {
        'debit': sum((x['debit'] for x in rows), ZERO),
        'credit': sum((x['credit'] for x in rows), ZERO),
    }
    totals['difference'] = totals['debit'] - totals['credit']
    return render(request, 'accounting/trial_balance.html', {
        'title': 'Neraca Saldo', 'as_of': as_of, 'rows': rows, 'totals': totals,
    })


@login_required
def worksheet_view(request):
    as_of = cutoff(request)
    return render(request, 'accounting/worksheet.html', {
        'title': 'Neraca Lajur', 'as_of': as_of, 'data': worksheet(as_of),
    })


@login_required
def income_statement(request):
    as_of = cutoff(request)
    data = period_totals(as_of)
    groups = []
    for code, title in [('REVENUE', 'Pendapatan Usaha'), ('COGS', 'Harga Pokok Penjualan'),
                        ('EXPENSE', 'Beban Operasional'), ('OTHER_INCOME', 'Pendapatan Lain-lain'),
                        ('OTHER_EXPENSE', 'Beban Lain-lain')]:
        rows = data['groups'].get(code, [])
        items = [{'account': r['account'], 'amount': -r['net'] if code in ('REVENUE', 'OTHER_INCOME') else r['net']} for r in rows]
        groups.append({'title': title, 'items': items, 'total': sum((r['amount'] for r in items), ZERO)})
    return render(request, 'accounting/income.html', {
        'title': 'Laba Rugi', 'as_of': as_of, 'data': data, 'groups': groups,
    })


@login_required
def balance_sheet(request):
    as_of = cutoff(request)
    data = period_totals(as_of)
    groups = []
    for code, title in [('ASSET', 'Aset'), ('LIABILITY', 'Kewajiban'), ('EQUITY', 'Ekuitas')]:
        rows = data['groups'].get(code, [])
        items = [{'account': r['account'], 'amount': r['net'] if code == 'ASSET' else -r['net']} for r in rows]
        groups.append({'title': title, 'items': items, 'total': sum((r['amount'] for r in items), ZERO)})
    return render(request, 'accounting/balance.html', {
        'title': 'Neraca', 'as_of': as_of, 'data': data, 'groups': groups,
    })


@login_required
def products(request):
    rows = []
    for product in Product.objects.all():
        card = stock_card(product)
        rows.append({'product': product, 'qty': card['qty'], 'value': card['value']})
    return render(request, 'accounting/products.html', {'title': 'Master Persediaan', 'rows': rows})


@login_required
@require_http_methods(['GET', 'POST'])
def product_form(request, pk=None):
    obj = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                product = form.save()
                if not obj and form.cleaned_data.get('opening_quantity', 0) > 0:
                    create_opening_stock(product, form.cleaned_data['opening_quantity'],
                        form.cleaned_data['opening_unit_cost'], form.cleaned_data['opening_date'])
            messages.success(request, 'Data produk berhasil disimpan.')
            return redirect('products')
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'accounting/form_page.html', {
        'title': 'Ubah Produk' if obj else 'Tambah Produk', 'form': form, 'back_url': reverse('products'),
        'helper': 'Stok awal hanya dicatat sekali ketika produk dibuat. Pastikan nilainya tercermin dalam saldo awal akun Persediaan.'})


@login_required
def inventory_card(request):
    product = Product.objects.filter(pk=request.GET.get('product')).first() if request.GET.get('product', '').isdigit() else None
    end = cutoff(request)
    data = stock_card(product, end=end) if product else None
    return render(request, 'accounting/inventory.html', {
        'title': 'Inventory Card · FIFO', 'product': product, 'products': Product.objects.all(),
        'data': data, 'end': end,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def movement_new(request):
    form = MovementForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            movement = create_stock_movement(product=d['product'], date_value=d['date'],
                reference=d['reference'], kind=d['kind'], quantity=d['quantity'],
                unit_price=d['unit_price'], settlement_account=d['settlement_account'],
                description=d['description'], party=d.get('party'), user=request.user)
            messages.success(request, f'Mutasi stok {movement.reference} dan jurnal otomatis berhasil disimpan.')
            return redirect(f"{reverse('inventory')}?product={movement.product_id}")
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, str(exc))
    return render(request, 'accounting/form_page.html', {
        'title': 'Transaksi Persediaan', 'form': form, 'back_url': reverse('inventory'),
        'helper': 'MASUK: debet Persediaan, kredit akun pembayaran/utang. KELUAR: debet kas/piutang, kredit penjualan, sekaligus debet HPP dan kredit persediaan dengan biaya FIFO. Transaksi stok tidak dapat dibackdate.'})


@login_required
@require_http_methods(['GET', 'POST'])
def settings_view(request):
    obj = BusinessProfile.current()
    form = ProfileForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Pengaturan nama usaha berhasil disimpan.')
        return redirect('settings')
    return render(request, 'accounting/form_page.html', {
        'title': 'Pengaturan Usaha', 'form': form, 'back_url': reverse('dashboard'),
        'helper': 'Nama usaha muncul pada header seluruh halaman dan file Excel. Kode akun Persediaan/HPP/Penjualan wajib ada sebelum mencatat stok.'})


@login_required
def export_view(request, kind):
    from .exports import export_download
    return export_download(request, kind)
