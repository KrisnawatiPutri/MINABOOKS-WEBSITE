"""Linked Excel export.

Editable inputs (blue): AKUN, KODE, JURNAL UMUM, JURNAL PENYESUAIAN,
PRODUK and the quantities/prices in INVENTORY CARD. Derived cells contain
Excel formulas, including a formula-based FIFO cost calculation.

The workbook is a *snapshot* of the database's accounts, document rows and
product movements. Changing existing amounts/prices/quantities recalculates
linked reports in Excel. Adding, deleting, reassigning, or reordering documents
requires a fresh export because the ledger's detail rows are pre-grouped.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.http import Http404, HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from .models import (Account, BusinessProfile, InventoryMovement, JournalEntry,
                     JournalLine, Party, Product)

FIRST = 5
MONEY = '#,##0.00;[Red](#,##0.00);"-"'
QTY = '#,##0.000;[Red](#,##0.000);"-"'
INP = '1D4ED8'
LINK = '15803D'
FORMULA = '1E293B'
HEAD = '0F766E'

# All export buttons produce a self-contained linked workbook. Selecting a
# report only changes which tab is shown first; formula dependencies stay valid.
EXPORTS = ('accounts', 'parties', 'journal', 'ledger', 'adjustment', 'subsidiary',
           'trial', 'worksheet', 'income', 'balance', 'products', 'inventory')
NAME = {
    'accounts': 'AKUN', 'parties': 'KODE', 'journal': 'JURNAL UMUM',
    'ledger': 'BUKU BESAR', 'adjustment': 'JURNAL PENYESUAIAN',
    'subsidiary': 'BB PEMBANTU', 'trial': 'NERACA SALDO',
    'worksheet': 'NERACA LAJUR', 'income': 'LABA RUGI',
    'balance': 'NERACA', 'products': 'PRODUK', 'inventory': 'INVENTORY CARD',
}


def get_asof(request):
    try:
        return date.fromisoformat(request.GET['to'])
    except (KeyError, ValueError):
        return timezone.localdate()


def get_from(request):
    try:
        return date.fromisoformat(request.GET['from'])
    except (KeyError, ValueError):
        return None


def plain(value):
    """Excel injection defense for all user-entered text."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + value
    return value


def put(ws, row, col, value, *, formula=False, number=False, date_cell=False):
    cell = ws.cell(row, col)
    cell.value = value if formula else plain(value)
    cell.font = Font(name='Aptos', size=10, color=LINK if formula and "'!" in str(value) else FORMULA if formula else INP)
    if number or formula:
        cell.number_format = MONEY
    if date_cell:
        cell.number_format = 'dd mmm yyyy'
    if row % 2 == 0:
        cell.fill = PatternFill('solid', fgColor='F0FDF7')
    return cell


def make_sheet(wb, title, headers, company, *, hint='Angka biru dapat diedit, angka hitam/hijau adalah rumus.'):
    ws = wb.create_sheet(title)
    last = len(headers)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last)
    ws['A1'] = plain(company)
    ws['A1'].font = Font(name='Aptos Display', size=16, bold=True, color='FFFFFF')
    ws['A1'].fill = PatternFill('solid', fgColor='134E4A')
    ws.row_dimensions[1].height = 36
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last)
    ws['A2'] = plain(f'{title}  |  {hint}')
    ws['A2'].font = Font(name='Aptos', size=10, color='166534', italic=True)
    ws.row_dimensions[2].height = 25
    for c, title_col in enumerate(headers, 1):
        cell = ws.cell(4, c, title_col)
        cell.fill = PatternFill('solid', fgColor=HEAD)
        cell.font = Font(name='Aptos', size=10, bold=True, color='FFFFFF')
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        ws.column_dimensions[get_column_letter(c)].width = (
            33 if any(t in title_col.lower() for t in ('keterangan', 'nama', 'uraian'))
            else 19 if any(t in title_col.lower() for t in ('saldo', 'debet', 'kredit', 'jumlah', 'nilai', 'harga'))
            else 15
        )
    ws.row_dimensions[4].height = 32
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'C5' if last >= 5 else 'A5'
    return ws


def ref(sheet, col, row):
    return f"'{sheet}'!{col}{row}"


def rr(sheet, col, last):
    return f"'{sheet}'!${col}${FIRST}:${col}${max(FIRST, last)}"


def ss(sheet, value_col, criteria_col, criteria, last):
    return f'SUMIF({rr(sheet, criteria_col, last)},{criteria},{rr(sheet, value_col, last)})'


def prior(sheet, amount_col, code_col, key, last, start_date):
    # Only used to compute a ledger opening when the user chooses a date range.
    if not start_date:
        return '0'
    cutoff = f'DATE({start_date.year},{start_date.month},{start_date.day})'
    return (f'SUMIFS({rr(sheet,amount_col,last)},{rr(sheet,code_col,last)},{key},'
            f'{rr(sheet,"A",last)},"<"&{cutoff})')


def span(ws, title, formulas, start_row):
    for i, value in enumerate([title] + formulas):
        put(ws, start_row, i+1, value, formula=isinstance(value, str) and value.startswith('='))
    for cell in ws[start_row][:len(formulas)+1]:
        cell.fill = PatternFill('solid', fgColor='D1FAE5')
        cell.font = Font(name='Aptos', size=10, bold=True, color='134E4A')


def build_linked_workbook(end, start=None):
    wb = Workbook()
    wb.remove(wb.active)
    wb.calculation = CalcProperties(calcMode='auto', fullCalcOnLoad=True, forceFullCalc=True)
    profile = BusinessProfile.current()
    accounts = list(Account.objects.filter(is_header=False).order_by('code'))
    parties = list(Party.objects.order_by('code'))
    products = list(Product.objects.order_by('code'))
    movements = list(InventoryMovement.objects.filter(date__lte=end)
                     .select_related('product').order_by('product__code', 'date', 'id'))
    entries = list(JournalEntry.objects.filter(date__lte=end).order_by('date', 'id').prefetch_related(
        'lines__account', 'lines__party'))
    lines = [line for e in entries for line in e.lines.all()]

    sheets = {}
    headers = {
        'accounts': ['Kode Akun', 'Nama Akun', 'Normal D/C', 'Kategori', 'Pos Laporan', 'Saldo Awal Debet', 'Saldo Awal Kredit'],
        'parties': ['Kode Bantu', 'Nama Relasi', 'Jenis', 'Saldo Awal', 'Telepon'],
        'journal': ['Tanggal', 'Bukti', 'Keterangan', 'Kode Akun', 'Nama Akun', 'Kode Bantu', 'Nama Relasi', 'DEBET', 'KREDIT'],
        'ledger': ['Kode Akun', 'Nama Akun', 'Tanggal', 'Bukti', 'Keterangan', 'DEBET', 'KREDIT', 'Saldo Normal'],
        'adjustment': ['Tanggal', 'Bukti', 'Keterangan', 'Kode Akun', 'Nama Akun', 'Kode Bantu', 'Nama Relasi', 'DEBET', 'KREDIT'],
        'subsidiary': ['Kode Bantu', 'Nama Relasi', 'Jenis', 'Tanggal', 'Bukti', 'DEBET', 'KREDIT', 'Saldo Normal'],
        'trial': ['Kode Akun', 'Nama Akun', 'Kategori', 'DEBET', 'KREDIT'],
        'worksheet': ['Kode Akun', 'Nama Akun', 'NS D', 'NS K', 'JP D', 'JP K', 'NS Disesuaikan D', 'NS Disesuaikan K', 'Laba Rugi D', 'Laba Rugi K', 'Neraca D', 'Neraca K'],
        'income': ['Bagian', 'Kode Akun', 'Nama Akun', 'Nilai (Rp)'],
        'balance': ['Bagian', 'Kode Akun', 'Nama Akun', 'Nilai (Rp)'],
        'products': ['Kode Produk', 'Nama Barang', 'Satuan', 'Harga Jual', 'Jumlah Stok', 'Nilai Stok FIFO'],
        'inventory': ['Kode Produk', 'Nama Barang', 'Satuan', 'Tanggal', 'Bukti', 'Jenis', 'Keterangan', 'Masuk Unit', 'Harga Beli/Unit', 'Nilai Masuk', 'Keluar Unit', 'Harga Jual/Unit', 'Nilai Penjualan', 'HPP FIFO', 'Saldo Unit', 'Saldo Nilai', 'Kumulatif Masuk', 'Kumulatif Keluar', 'Batas Awal Lot', 'HPP/Unit'],
    }
    for key in EXPORTS:
        sheets[key] = make_sheet(wb, NAME[key], headers[key], profile.name)
    count = {k: len(x) for k, x in [('accounts', accounts), ('parties', parties), ('products', products), ('inventory', movements)]}
    last_account = FIRST + len(accounts) - 1
    last_party = FIRST + len(parties) - 1
    last_product = FIRST + len(products) - 1
    last_stock = FIRST + len(movements) - 1

    # 1. User-editable account master and helper codes. Always included in the XLSX,
    # even though the website no longer shows their sidebar links.
    arows = {}
    ws = sheets['accounts']
    for r, a in enumerate(accounts, FIRST):
        arows[a.code] = r
        values = [a.code, a.name, a.normal_balance, a.category, a.report_type,
                  a.opening_balance if a.normal_balance == 'D' else 0,
                  a.opening_balance if a.normal_balance == 'C' else 0]
        for c, val in enumerate(values, 1):
            put(ws, r, c, val, number=c in (6, 7))
    ws = sheets['parties']
    for r, p in enumerate(parties, FIRST):
        for c, val in enumerate((p.code, p.name, p.kind, p.opening_balance, p.phone), 1):
            put(ws, r, c, val, number=c == 4)

    # 2. Inventory input + formula FIFO using overlapping cumulative quantity
    # intervals per receipt layer with scalar MAX/MIN helpers. No static cost_amount field is copied.
    ws = sheets['inventory']
    stock_row = {}
    receipts_by_product = defaultdict(list)
    max_receipt_count = 0
    for r, movement in enumerate(movements, FIRST):
        stock_row[movement.pk] = r
        incoming = movement.kind in ('OPENING', 'IN')
        raw = {
            1: movement.product.code,
            4: movement.date, 5: movement.reference, 6: movement.kind,
            7: movement.description, 8: movement.quantity if incoming else 0,
            9: movement.unit_price if incoming else 0,
            11: movement.quantity if not incoming else 0,
            12: movement.unit_price if not incoming else 0,
        }
        for c, val in raw.items():
            put(ws, r, c, val, date_cell=(c == 4), number=c in (8,9,11,12))
        put(ws,r,2,f'=IFERROR(VLOOKUP(A{r},\'PRODUK\'!$A${FIRST}:$D${max(FIRST,last_product)},2,FALSE),"")',formula=True)
        put(ws,r,3,f'=IFERROR(VLOOKUP(A{r},\'PRODUK\'!$A${FIRST}:$D${max(FIRST,last_product)},3,FALSE),"")',formula=True)
        formulas = {
            10: f'=IF(OR(F{r}="IN",F{r}="OPENING"),ROUND(H{r}*I{r},2),0)',
            13: f'=IF(F{r}="OUT",ROUND(K{r}*L{r},2),0)',
            17: f'=SUMIFS($H${FIRST}:H{r},$A${FIRST}:A{r},A{r})',
            18: f'=SUMIFS($K${FIRST}:K{r},$A${FIRST}:A{r},A{r})',
            19: f'=Q{r}-H{r}',
        }
        for c, f in formulas.items():
            put(ws,r,c,f,formula=True)
        # Calculate each FIFO layer separately using scalar Excel MAX/MIN.
        # This is more compatible than array-SUMPRODUCT/IF and recalculates
        # correctly when the user edits purchase quantities or unit costs.
        if incoming:
            receipts_by_product[movement.product_id].append(r)
            max_receipt_count = max(max_receipt_count,
                                    len(receipts_by_product[movement.product_id]))
        else:
            layer_rows = receipts_by_product[movement.product_id]
            if len(layer_rows) > 16360:
                raise ValueError('Terlalu banyak lot FIFO untuk satu produk di Excel.')
            for slot, receipt_r in enumerate(layer_rows):
                helper_col = get_column_letter(21 + slot)  # U, V, W, ...
                allocation = (f'=MAX(0,MIN($R{r},$Q{receipt_r})-'
                              f'MAX($R{r}-$K{r},$S{receipt_r}))*$I{receipt_r}')
                put(ws,r,21+slot,allocation,formula=True)
            if layer_rows:
                last_helper = get_column_letter(20+len(layer_rows))
                fifo = f'=IF(K{r}=0,0,ROUND(SUM(U{r}:{last_helper}{r}),2))'
            else:
                fifo = '=0'
            put(ws,r,14,fifo,formula=True)
        if incoming:
            put(ws,r,14,'=0',formula=True)
        put(ws,r,15,f'=Q{r}-R{r}',formula=True)
        put(ws,r,16,f'=SUMIFS($J${FIRST}:J{r},$A${FIRST}:A{r},A{r})-SUMIFS($N${FIRST}:N{r},$A${FIRST}:A{r},A{r})',formula=True)
        put(ws,r,20,f'=IFERROR(N{r}/K{r},0)',formula=True)
        ws.cell(r,8).number_format = ws.cell(r,11).number_format = ws.cell(r,15).number_format = QTY
    for hidden in 'QRST':
        ws.column_dimensions[hidden].hidden = True
    for col in range(21, 21 + max_receipt_count):
        ws.column_dimensions[get_column_letter(col)].hidden = True
    ws.sheet_view.showGridLines = False
    ws['A3'] = 'FIFO dihitung dari harga dan jumlah barang MASUK. Jika menambah/menghapus/mengurutkan transaksi, ekspor ulang.'
    ws['A3'].font = Font(color='B45309', italic=True, size=10)
    ws = sheets['products']
    for r, product in enumerate(products, FIRST):
        for c,val in enumerate((product.code,product.name,product.unit,product.sale_price),1):
            put(ws,r,c,val,number=(c==4))
        for c,pos,neg in [(5,'H','K'),(6,'J','N')]:
            f = f'={ss("INVENTORY CARD",pos,"A",f"A{r}",last_stock)}-{ss("INVENTORY CARD",neg,"A",f"A{r}",last_stock)}'
            put(ws,r,c,f,formula=True)
        ws.cell(r,5).number_format = QTY

    # 3. Journal source sheets: adjustments independent, inventory journal lines
    # link to inventory quantities, sale amount and FIFO expense. User-entered
    # general and adjustment lines remain blue editable cells.
    jrows = {}
    lines_by_account = defaultdict(list)
    lines_by_party = defaultdict(list)
    stock_by_entry = {m.entry_id: m for m in movements if m.entry_id}
    groups = {
        'journal': [l for l in lines if l.entry.kind != 'ADJUSTMENT'],
        'adjustment': [l for l in lines if l.entry.kind == 'ADJUSTMENT'],
    }
    last_j = FIRST + len(groups['journal']) - 1
    last_adj = FIRST + len(groups['adjustment']) - 1
    for key in ('journal','adjustment'):
        ws = sheets[key]
        for r, line in enumerate(groups[key], FIRST):
            name = NAME[key]
            jrows[line.pk] = (name,r)
            lines_by_account[line.account_id].append(line)
            if line.party_id: lines_by_party[line.party_id].append(line)
            for c,val in {1:line.entry.date,2:line.entry.reference,
                          3:line.description or line.entry.description,
                          4:line.account.code,6:line.party.code if line.party else ''}.items():
                put(ws,r,c,val,date_cell=(c==1))
            put(ws,r,5,f'=IFERROR(VLOOKUP(D{r},\'AKUN\'!$A${FIRST}:$B${max(FIRST,last_account)},2,FALSE),"Kode tidak ditemukan")',formula=True)
            put(ws,r,7,f'=IF(F{r}="","",IFERROR(VLOOKUP(F{r},\'KODE\'!$A${FIRST}:$B${max(FIRST,last_party)},2,FALSE),"Kode tidak ditemukan"))',formula=True)
            movement = stock_by_entry.get(line.entry_id)
            amount_formula = None
            if movement and movement.pk in stock_row:
                stock_col = ('J' if movement.kind == 'IN' else
                             'N' if line.account.code in (profile.inventory_account_code, profile.cogs_account_code)
                             else 'M')
                amount_formula = f'={ref("INVENTORY CARD",stock_col,stock_row[movement.pk])}'
            for c, val in ((8,line.debit),(9,line.credit)):
                f = amount_formula if amount_formula and val != 0 else None
                put(ws,r,c,f if f else val,formula=bool(f),number=True)
        ws['A3'] = 'Edit jumlah debet/kredit pada sel biru; jurnal otomatis dari stok terhubung ke INVENTORY CARD.'
        ws['A3'].font = Font(color='B45309', italic=True, size=10)

    # Account balance expression used by independent report formulas.
    def net_formula(account_cell, include_adjustments=True, before=None):
        x = account_cell
        base = (f'{ss("AKUN","F","A",x,last_account)}-'
                f'{ss("AKUN","G","A",x,last_account)}')
        if before:
            j_d = prior('JURNAL UMUM','H','D',x,last_j,before)
            j_c = prior('JURNAL UMUM','I','D',x,last_j,before)
            a_d = prior('JURNAL PENYESUAIAN','H','D',x,last_adj,before)
            a_c = prior('JURNAL PENYESUAIAN','I','D',x,last_adj,before)
        else:
            j_d = ss('JURNAL UMUM','H','D',x,last_j)
            j_c = ss('JURNAL UMUM','I','D',x,last_j)
            a_d = ss('JURNAL PENYESUAIAN','H','D',x,last_adj)
            a_c = ss('JURNAL PENYESUAIAN','I','D',x,last_adj)
        return f'({base}+{j_d}-{j_c}' + (f'+{a_d}-{a_c}' if include_adjustments else '') + ')'

    # 4. Transaction-level ledgers with running formulas, amount cells
    # always reference corresponding journal source cells.
    ws = sheets['ledger']
    r = FIRST
    for a in accounts:
        first_row = r
        put(ws,r,1,a.code)
        put(ws,r,2,f'=IFERROR(VLOOKUP(A{r},\'AKUN\'!$A${FIRST}:$B${max(FIRST,last_account)},2,FALSE),"")',formula=True)
        put(ws,r,5,'SALDO AWAL PERIODE')
        n = net_formula(f'A{r}',before=start) if start else (f'({ss("AKUN","F","A",f"A{r}",last_account)}-{ss("AKUN","G","A",f"A{r}",last_account)})')
        normal = f'IFERROR(VLOOKUP(A{r},\'AKUN\'!$A${FIRST}:$C${max(FIRST,last_account)},3,FALSE),"D")'
        put(ws,r,8,f'=IF({normal}="D",{n},-({n}))',formula=True)
        r += 1
        for line in lines_by_account.get(a.id, []):
            if start and line.entry.date < start:
                continue
            source_name, src_r = jrows[line.pk]
            put(ws,r,1,a.code)
            for c, src_c in ((2,'E'),(3,'A'),(4,'B'),(5,'C'),(6,'H'),(7,'I')):
                put(ws,r,c,f'={ref(source_name,src_c,src_r)}',formula=True,date_cell=(c==3))
            normal = f'IFERROR(VLOOKUP(A{r},\'AKUN\'!$A${FIRST}:$C${max(FIRST,last_account)},3,FALSE),"D")'
            put(ws,r,8,f'=IF({normal}="D",H{r-1}+F{r}-G{r},H{r-1}+G{r}-F{r})',formula=True)
            r += 1
    ws['A3'] = 'Saldo berjalan mengacu ke jurnal. Penambahan/pengubahan kode akun pada jurnal memerlukan ekspor ulang.'
    ws['A3'].font = Font(color='B45309', italic=True, size=10)

    # 5. Subsidiary ledger by party, natural debit (customer) / credit (supplier).
    ws = sheets['subsidiary']
    r = FIRST
    for p in parties:
        put(ws,r,1,p.code)
        put(ws,r,2,f'=IFERROR(VLOOKUP(A{r},\'KODE\'!$A${FIRST}:$B${max(FIRST,last_party)},2,FALSE),"")',formula=True)
        put(ws,r,3,f'=IFERROR(VLOOKUP(A{r},\'KODE\'!$A${FIRST}:$C${max(FIRST,last_party)},3,FALSE),"")',formula=True)
        put(ws,r,5,'SALDO AWAL PERIODE')
        opening = ss('KODE','D','A',f'A{r}',last_party)
        if start:
            for sheet_name, last in [('JURNAL UMUM',last_j),('JURNAL PENYESUAIAN',last_adj)]:
                debit = prior(sheet_name,'H','F',f'A{r}',last,start)
                credit = prior(sheet_name,'I','F',f'A{r}',last,start)
                opening = f'({opening}+IF(C{r}="CUSTOMER",{debit}-{credit},{credit}-{debit}))'
        put(ws,r,8,f'={opening}',formula=True)
        r += 1
        for line in lines_by_party.get(p.id, []):
            if start and line.entry.date < start:
                continue
            source_name, src_r = jrows[line.pk]
            put(ws,r,1,p.code)
            for c,src_c in ((2,'G'),(4,'A'),(5,'B'),(6,'H'),(7,'I')):
                put(ws,r,c,f'={ref(source_name,src_c,src_r)}',formula=True,date_cell=c==4)
            put(ws,r,3,f'=IFERROR(VLOOKUP(A{r},\'KODE\'!$A${FIRST}:$C${max(FIRST,last_party)},3,FALSE),"")',formula=True)
            put(ws,r,8,f'=IF(C{r}="CUSTOMER",H{r-1}+F{r}-G{r},H{r-1}+G{r}-F{r})',formula=True)
            r += 1

    # 6. Trial balance + 10-column worksheet. Adjustment is not duplicated
    # in unadjusted NS columns; it only appears in JP and adjusted columns.
    ws_t = sheets['trial']
    ws_w = sheets['worksheet']
    adjusted_ref = {}
    for r, a in enumerate(accounts, FIRST):
        ar = arows[a.code]
        for ws in (ws_t,ws_w):
            put(ws,r,1,f'={ref("AKUN","A",ar)}',formula=True)
            put(ws,r,2,f'={ref("AKUN","B",ar)}',formula=True)
        put(ws_t,r,3,f'={ref("AKUN","D",ar)}',formula=True)
        net = net_formula(f'A{r}')
        put(ws_t,r,4,f'=MAX(0,{net})',formula=True)
        put(ws_t,r,5,f'=MAX(0,-({net}))',formula=True)
        unadjusted = net_formula(f'A{r}',include_adjustments=False)
        adjustment = (f'({ss("JURNAL PENYESUAIAN","H","D",f"A{r}",last_adj)}-'
                      f'{ss("JURNAL PENYESUAIAN","I","D",f"A{r}",last_adj)})')
        formulas = {
            3: f'=MAX(0,{unadjusted})', 4: f'=MAX(0,-({unadjusted}))',
            5: f'=MAX(0,{adjustment})', 6: f'=MAX(0,-({adjustment}))',
            7: f'=MAX(0,C{r}-D{r}+E{r}-F{r})',
            8: f'=MAX(0,-(C{r}-D{r}+E{r}-F{r}))',
            9: f'=IF({ref("AKUN","E",ar)}="LR",G{r},0)',
            10: f'=IF({ref("AKUN","E",ar)}="LR",H{r},0)',
            11: f'=IF({ref("AKUN","E",ar)}="NRC",G{r},0)',
            12: f'=IF({ref("AKUN","E",ar)}="NRC",H{r},0)',
        }
        for c,f in formulas.items():
            put(ws_w,r,c,f,formula=True)
        adjusted_ref[a.code] = r
    tail = FIRST + len(accounts) - 1
    row_total = tail + 1
    put(ws_t,row_total,1,'TOTAL')
    for c in (4,5):
        letter = get_column_letter(c)
        f = f'=SUM({letter}{FIRST}:{letter}{tail})' if accounts else '=0'
        put(ws_t,row_total,c,f,formula=True)
    for c in range(3,13):
        letter = get_column_letter(c)
        f = f'=SUM({letter}{FIRST}:{letter}{tail})' if accounts else '=0'
        put(ws_w,row_total,c,f,formula=True)
    ws_w.cell(row_total,2).value = 'TOTAL'
    put(ws_w,row_total+1,2,'LABA / RUGI BERJALAN')
    put(ws_w,row_total+1,10,f'=J{row_total}-I{row_total}',formula=True)

    # 7. P&L points to worksheet outputs. Its profit is referenced by the
    # balance sheet, ensuring no separately typed profit amount exists.
    ws = sheets['income']
    r = FIRST
    for cat,title in [('REVENUE','Pendapatan'),('COGS','Harga Pokok Penjualan'),
                      ('EXPENSE','Beban Operasional'),('OTHER_INCOME','Pendapatan Lain'),
                      ('OTHER_EXPENSE','Beban Lain')]:
        for a in accounts:
            if a.category != cat: continue
            wr = adjusted_ref[a.code]
            put(ws,r,1,title)
            put(ws,r,2,f'={ref("NERACA LAJUR","A",wr)}',formula=True)
            put(ws,r,3,f'={ref("NERACA LAJUR","B",wr)}',formula=True)
            amount = f'J{wr}-I{wr}' if cat in ('REVENUE','OTHER_INCOME') else f'I{wr}-J{wr}'
            put(ws,r,4,f'=\'NERACA LAJUR\'!{amount.replace("-", "-\'NERACA LAJUR\'!")}',formula=True)
            r += 1
    profit_row = r
    put(ws,profit_row,1,'HASIL')
    put(ws,profit_row,3,'LABA / RUGI BERSIH')
    def income_total(label):
        return f'SUMIF(A{FIRST}:A{r-1},"{label}",D{FIRST}:D{r-1})' if r > FIRST else '0'
    rev = income_total('Pendapatan')
    oth = income_total('Pendapatan Lain')
    cost = income_total('Harga Pokok Penjualan')
    expense = income_total('Beban Operasional')
    oth_ex = income_total('Beban Lain')
    put(ws,profit_row,4,f'={rev}+{oth}-{cost}-{expense}-{oth_ex}',formula=True)
    for c in ws[profit_row][:4]:
        c.fill = PatternFill('solid',fgColor='D1FAE5')

    # 8. Balance sheet links every account to worksheet adjusted debit/credit
    # and includes the same live profit formula from LABA RUGI.
    ws = sheets['balance']
    r = FIRST
    for cat,title in [('ASSET','Aset'),('LIABILITY','Kewajiban'),('EQUITY','Ekuitas')]:
        for a in accounts:
            if a.category != cat: continue
            wr = adjusted_ref[a.code]
            put(ws,r,1,title)
            put(ws,r,2,f'={ref("NERACA LAJUR","A",wr)}',formula=True)
            put(ws,r,3,f'={ref("NERACA LAJUR","B",wr)}',formula=True)
            if cat == 'ASSET':
                f=f'={ref("NERACA LAJUR","G",wr)}-{ref("NERACA LAJUR","H",wr)}'
            else:
                f=f'={ref("NERACA LAJUR","H",wr)}-{ref("NERACA LAJUR","G",wr)}'
            put(ws,r,4,f,formula=True)
            r += 1
    def total_by_group(name):
        return f'SUMIF($A${FIRST}:$A${r-1},"{name}",$D${FIRST}:$D${r-1})' if r > FIRST else '0'
    totals = {}
    for label, formula in [
        ('Total Aset', f'={total_by_group("Aset")}'),
        ('Total Kewajiban', f'={total_by_group("Kewajiban")}'),
        ('Total Ekuitas', f'={total_by_group("Ekuitas")}'),
        ('Laba / Rugi Berjalan', f'={ref("LABA RUGI","D",profit_row)}'),
    ]:
        put(ws,r,1,'RINGKASAN')
        put(ws,r,3,label)
        put(ws,r,4,formula,formula=True)
        totals[label] = r
        r += 1
    put(ws,r,1,'KONTROL')
    put(ws,r,3,'SELISIH NERACA (HARUS 0)')
    put(ws,r,4,f'=D{totals["Total Aset"]}-D{totals["Total Kewajiban"]}-D{totals["Total Ekuitas"]}-D{totals["Laba / Rugi Berjalan"]}',formula=True)
    for c in ws[r][:4]:
        c.fill = PatternFill('solid', fgColor='D1FAE5')

    # Explicit total-check row in each journal to help identify an unbalanced edit.
    for key in ('journal','adjustment'):
        ws = sheets[key]
        last = last_j if key == 'journal' else last_adj
        tail = max(FIRST,last)+1
        put(ws,tail,7,'TOTAL / SELISIH')
        put(ws,tail,8,f'=SUM(H{FIRST}:H{tail-1})',formula=True)
        put(ws,tail,9,f'=SUM(I{FIRST}:I{tail-1})',formula=True)
        put(ws,tail+1,7,'Selisih (harus 0)')
        put(ws,tail+1,8,f'=H{tail}-I{tail}',formula=True)

    # Add freeze/filter for each sheet; protect none, so users can edit inputs.
    for ws in wb.worksheets:
        cols=len(headers[next(k for k,v in NAME.items() if v==ws.title)])
        ws.auto_filter.ref=f'A4:{get_column_letter(cols)}{max(FIRST,ws.max_row)}'
        ws.sheet_properties.pageSetUpPr.fitToPage=True
    return wb


def export_download(request, kind):
    if kind != 'all' and kind not in EXPORTS:
        raise Http404('Jenis laporan ekspor tidak dikenal.')
    end = get_asof(request)
    start = get_from(request)
    wb = build_linked_workbook(end, start)
    if kind != 'all':
        wb.active = wb.sheetnames.index(NAME[kind])
    result = BytesIO()
    wb.save(result)
    slug = 'lengkap' if kind == 'all' else kind
    response = HttpResponse(result.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="agribooks_{slug}_{end:%Y%m%d}.xlsx"'
    return response
