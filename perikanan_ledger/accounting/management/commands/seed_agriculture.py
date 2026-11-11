from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounting.models import Account, BusinessProfile, Product, JournalEntry
from accounting.services import create_opening_stock, create_stock_movement

ACCOUNT_ROWS = [
    ('1110','Kas di Bank','ASSET','D'),
    ('1120','Kas Tunai','ASSET','D'),
    ('1130','Kas Kecil','ASSET','D'),
    ('1140','Piutang Usaha','ASSET','D'),
    ('1150','Persediaan Barang dan Hasil Tani','ASSET','D'),
    ('1160','Perlengkapan Pertanian','ASSET','D'),
    ('1210','Tanah Pertanian','ASSET','D'),
    ('1220','Bangunan / Gudang','ASSET','D'),
    ('1230','Peralatan Pertanian','ASSET','D'),
    ('2110','Utang Usaha','LIABILITY','C'),
    ('2120','Utang Bank','LIABILITY','C'),
    ('3100','Modal Pemilik','EQUITY','C'),
    ('3110','Laba Ditahan','EQUITY','C'),
    ('4110','Penjualan Hasil Tani','REVENUE','C'),
    ('4120','Pendapatan Jasa','REVENUE','C'),
    ('5110','Harga Pokok Penjualan','COGS','D'),
    ('6110','Beban Pupuk dan Pestisida','EXPENSE','D'),
    ('6120','Beban Tenaga Kerja','EXPENSE','D'),
    ('6130','Beban Listrik dan Air','EXPENSE','D'),
    ('6140','Beban Transportasi','EXPENSE','D'),
    ('6150','Beban Penyusutan Alat','EXPENSE','D'),
    ('7110','Pendapatan Lain-lain','OTHER_INCOME','C'),
    ('8120','Beban Bunga','OTHER_EXPENSE','D'),
]


class Command(BaseCommand):
    help = 'Isi bagan akun usaha pertanian, dengan demo transaksi FIFO opsional.'

    def add_arguments(self, parser):
        parser.add_argument('--demo', action='store_true', help='Tambah data uji contoh yang saldonya seimbang')

    @transaction.atomic
    def handle(self, *args, **options):
        BusinessProfile.current()
        for code, name, cat, normal in ACCOUNT_ROWS:
            Account.objects.get_or_create(code=code, defaults={
                'name':name, 'category':cat, 'normal_balance':normal})
        self.stdout.write(self.style.SUCCESS(f'Bagan akun pertanian siap ({len(ACCOUNT_ROWS)} akun standar).'))
        if not options['demo']:
            self.stdout.write('Tambahkan --demo untuk contoh stok, pembelian, dan penjualan.')
            return
        if JournalEntry.objects.exists() or Product.objects.exists() or any(
                Account.objects.get(code=code).opening_balance != 0 for code in ('1120','1150','3100')):
            raise CommandError('Mode demo hanya aman dijalankan pada database awal tanpa produk, jurnal dan saldo awal.')
        cash = Account.objects.get(code='1120')
        inventory = Account.objects.get(code='1150')
        equity = Account.objects.get(code='3100')
        cash.opening_balance = Decimal('20000000.00')
        inventory.opening_balance = Decimal('4000000.00')
        equity.opening_balance = Decimal('24000000.00')
        for a in (cash, inventory, equity): a.save(update_fields=['opening_balance'])
        rice = Product.objects.create(code='PADI-01', name='Beras Organik', unit='kg', sale_price=Decimal('30000'))
        corn = Product.objects.create(code='JAG-01', name='Jagung Pipil', unit='kg', sale_price=Decimal('50000'))
        today = timezone.localdate()
        create_opening_stock(rice, Decimal('100'), Decimal('20000'), today)
        create_opening_stock(corn, Decimal('50'), Decimal('40000'), today)
        create_stock_movement(product=rice, date_value=today, reference='BELI-DEMO-01',
            kind='IN', quantity=Decimal('30'), unit_price=Decimal('22000'),
            settlement_account=cash, description='Pembelian beras organik', user=None)
        create_stock_movement(product=rice, date_value=today, reference='JUAL-DEMO-01',
            kind='OUT', quantity=Decimal('110'), unit_price=Decimal('30000'),
            settlement_account=cash, description='Penjualan beras organik', user=None)
        self.stdout.write(self.style.SUCCESS('Demo terisi. FIFO penjualan: 100×20.000 + 10×22.000 = 2.220.000.'))
