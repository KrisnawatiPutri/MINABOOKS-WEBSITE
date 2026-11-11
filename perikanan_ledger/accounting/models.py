from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

ZERO = Decimal('0.00')


class BusinessProfile(models.Model):
    name = models.CharField('Nama usaha', max_length=180, default='Tani Sejahtera')
    subtitle = models.CharField('Bidang usaha', max_length=160, default='Pertanian dan Perdagangan Hasil Tani')
    address = models.TextField('Alamat', blank=True)
    phone = models.CharField('Telepon', max_length=40, blank=True)
    email = models.EmailField('Email', blank=True)
    owner = models.CharField('Pemilik / penanggung jawab', max_length=120, blank=True)
    inventory_account_code = models.CharField('Kode akun persediaan', max_length=16, default='1150')
    cogs_account_code = models.CharField('Kode akun HPP', max_length=16, default='5110')
    sales_account_code = models.CharField('Kode akun pendapatan penjualan', max_length=16, default='4110')

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return self.name


class Account(models.Model):
    class Category(models.TextChoices):
        ASSET = 'ASSET', 'Aset'
        LIABILITY = 'LIABILITY', 'Kewajiban'
        EQUITY = 'EQUITY', 'Ekuitas'
        REVENUE = 'REVENUE', 'Pendapatan'
        COGS = 'COGS', 'Harga Pokok Penjualan'
        EXPENSE = 'EXPENSE', 'Beban Operasional'
        OTHER_INCOME = 'OTHER_INCOME', 'Pendapatan Lain-lain'
        OTHER_EXPENSE = 'OTHER_EXPENSE', 'Beban Lain-lain'

    code = models.CharField('Kode akun', max_length=16, unique=True)
    name = models.CharField('Nama akun', max_length=180)
    category = models.CharField('Kelompok akun', max_length=20, choices=Category.choices)
    normal_balance = models.CharField('Saldo normal', max_length=1, choices=[('D', 'Debet'), ('C', 'Kredit')], default='D')
    opening_balance = models.DecimalField('Saldo awal (sesuai saldo normal, boleh negatif)', max_digits=20, decimal_places=2, default=ZERO)
    is_active = models.BooleanField('Aktif', default=True)
    is_header = models.BooleanField('Akun header (tidak untuk transaksi)', default=False)

    class Meta:
        ordering = ['code']

    @property
    def report_type(self):
        return 'NRC' if self.category in ('ASSET', 'LIABILITY', 'EQUITY') else 'LR'

    def __str__(self):
        return f'{self.code} · {self.name}'


class Party(models.Model):
    class Kind(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Pelanggan / Piutang'
        SUPPLIER = 'SUPPLIER', 'Pemasok / Utang'

    code = models.CharField('Kode relasi', max_length=16, unique=True)
    name = models.CharField('Nama relasi', max_length=180)
    kind = models.CharField('Jenis relasi', max_length=12, choices=Kind.choices)
    opening_balance = models.DecimalField('Saldo awal piutang/utang', max_digits=20, decimal_places=2, default=ZERO)
    phone = models.CharField('Telepon', max_length=40, blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} · {self.name}'


class JournalEntry(models.Model):
    class Kind(models.TextChoices):
        GENERAL = 'GENERAL', 'Jurnal Umum'
        ADJUSTMENT = 'ADJUSTMENT', 'Jurnal Penyesuaian'
        INVENTORY = 'INVENTORY', 'Otomatis Persediaan'

    date = models.DateField('Tanggal')
    reference = models.CharField('Nomor bukti', max_length=50)
    description = models.TextField('Keterangan')
    kind = models.CharField('Jenis jurnal', max_length=12, choices=Kind.choices, default=Kind.GENERAL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        constraints = [models.UniqueConstraint(fields=['date', 'reference'], name='unique_voucher_per_date')]

    @property
    def total_debit(self):
        return sum((line.debit for line in self.lines.all()), ZERO)

    @property
    def total_credit(self):
        return sum((line.credit for line in self.lines.all()), ZERO)

    def __str__(self):
        return f'{self.reference} ({self.date})'


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, related_name='lines', on_delete=models.PROTECT)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField('Uraian baris', max_length=250, blank=True)
    debit = models.DecimalField('Debet', max_digits=20, decimal_places=2, default=ZERO)
    credit = models.DecimalField('Kredit', max_digits=20, decimal_places=2, default=ZERO)

    class Meta:
        ordering = ['id']

    def clean(self):
        errors = {}
        debit, credit = self.debit or ZERO, self.credit or ZERO
        if debit < 0 or credit < 0:
            errors['debit'] = 'Nominal harus positif atau nol.'
        if (debit > 0) == (credit > 0):
            errors['debit'] = 'Isi tepat satu kolom: debet ATAU kredit.'
        if self.account_id and (not self.account.is_active or self.account.is_header):
            errors['account'] = 'Pilih akun transaksi yang aktif.'
        if self.account_id:
            if self.account.code == '1140':
                if not self.party_id or self.party.kind != Party.Kind.CUSTOMER:
                    errors['party'] = 'Akun 1140 wajib memakai relasi pelanggan.'
            elif self.account.code == '2110':
                if not self.party_id or self.party.kind != Party.Kind.SUPPLIER:
                    errors['party'] = 'Akun 2110 wajib memakai relasi pemasok.'
            elif self.party_id:
                errors['party'] = 'Kode relasi hanya dipakai untuk akun 1140/2110.'
        if errors:
            raise ValidationError(errors)


class Product(models.Model):
    code = models.CharField('Kode barang', max_length=24, unique=True)
    name = models.CharField('Nama produk/hasil tani', max_length=180)
    unit = models.CharField('Satuan', max_length=20, default='kg')
    sale_price = models.DecimalField('Harga jual standar', max_digits=20, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)])
    is_active = models.BooleanField('Aktif', default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} · {self.name}'


class InventoryMovement(models.Model):
    class Kind(models.TextChoices):
        OPENING = 'OPENING', 'Saldo Awal'
        IN = 'IN', 'Masuk / Pembelian'
        OUT = 'OUT', 'Keluar / Penjualan'

    product = models.ForeignKey(Product, related_name='movements', on_delete=models.PROTECT)
    date = models.DateField('Tanggal')
    reference = models.CharField('Nomor bukti', max_length=50)
    description = models.CharField('Keterangan', max_length=250)
    kind = models.CharField('Jenis pergerakan', max_length=8, choices=Kind.choices)
    quantity = models.DecimalField('Kuantitas', max_digits=18, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    unit_price = models.DecimalField('Harga beli atau jual per unit', max_digits=20, decimal_places=2, default=ZERO)
    cost_amount = models.DecimalField('Nilai harga pokok FIFO', max_digits=20, decimal_places=2, default=ZERO)
    sales_amount = models.DecimalField('Nilai penjualan', max_digits=20, decimal_places=2, default=ZERO)
    entry = models.OneToOneField(JournalEntry, null=True, blank=True, related_name='stock_movement', on_delete=models.PROTECT)

    class Meta:
        ordering = ['date', 'id']
        constraints = [models.UniqueConstraint(fields=['product', 'reference'], name='unique_inventory_reference_per_product')]

    def __str__(self):
        return f'{self.reference} · {self.product.code} · {self.kind}'


class InventoryLayer(models.Model):
    product = models.ForeignKey(Product, related_name='layers', on_delete=models.PROTECT)
    movement = models.OneToOneField(InventoryMovement, related_name='layer', on_delete=models.PROTECT)
    unit_cost = models.DecimalField(max_digits=20, decimal_places=2)
    received_quantity = models.DecimalField(max_digits=18, decimal_places=3)
    remaining_quantity = models.DecimalField(max_digits=18, decimal_places=3)

    class Meta:
        ordering = ['movement__date', 'movement__id', 'id']


class InventoryAllocation(models.Model):
    outgoing = models.ForeignKey(InventoryMovement, related_name='allocations', on_delete=models.PROTECT)
    layer = models.ForeignKey(InventoryLayer, related_name='allocations', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    amount = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        ordering = ['id']
