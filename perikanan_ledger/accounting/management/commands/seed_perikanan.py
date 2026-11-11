"""Optional fresh-database starter data for fisheries businesses.

Leaves all accounting algorithms and the original seed_agriculture command unchanged.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounting.models import Account, BusinessProfile, Product, JournalEntry
from accounting.services import create_opening_stock, create_stock_movement

ACCOUNT_ROWS = [
    ('1110', 'Kas di Bank', 'ASSET', 'D'),
    ('1120', 'Kas Tunai', 'ASSET', 'D'),
    ('1130', 'Kas Kecil', 'ASSET', 'D'),
    ('1140', 'Piutang Usaha', 'ASSET', 'D'),
    ('1150', 'Persediaan Ikan dan Hasil Perikanan', 'ASSET', 'D'),
    ('1160', 'Perlengkapan Perikanan dan Budidaya', 'ASSET', 'D'),
    ('1210', 'Kolam / Area Budidaya', 'ASSET', 'D'),
    ('1220', 'Bangunan / Gudang', 'ASSET', 'D'),
    ('1230', 'Peralatan Penangkapan dan Budidaya', 'ASSET', 'D'),
    ('2110', 'Utang Usaha', 'LIABILITY', 'C'),
    ('2120', 'Utang Bank', 'LIABILITY', 'C'),
    ('3100', 'Modal Pemilik', 'EQUITY', 'C'),
    ('3110', 'Laba Ditahan', 'EQUITY', 'C'),
    ('4110', 'Penjualan Hasil Perikanan', 'REVENUE', 'C'),
    ('4120', 'Pendapatan Jasa Perikanan', 'REVENUE', 'C'),
    ('5110', 'Harga Pokok Penjualan', 'COGS', 'D'),
    ('6110', 'Beban Pakan dan Benih', 'EXPENSE', 'D'),
    ('6120', 'Beban Tenaga Kerja', 'EXPENSE', 'D'),
    ('6130', 'Beban Listrik, Air, dan Es', 'EXPENSE', 'D'),
    ('6140', 'Beban Transportasi dan Distribusi', 'EXPENSE', 'D'),
    ('6150', 'Beban Penyusutan Alat', 'EXPENSE', 'D'),
    ('7110', 'Pendapatan Lain-lain', 'OTHER_INCOME', 'C'),
    ('8120', 'Beban Bunga', 'OTHER_EXPENSE', 'D'),
]


class Command(BaseCommand):
    help = 'Siapkan akun perikanan di database baru, dengan demo FIFO opsional.'

    def add_arguments(self, parser):
        parser.add_argument('--demo', action='store_true', help='Tambahkan contoh pembelian dan penjualan ikan.')

    @transaction.atomic
    def handle(self, *args, **options):
        # Never silently rename or replace an existing user's business.
        has_existing_data = (Account.objects.exists() or Product.objects.exists() or
                             JournalEntry.objects.exists())
        profile = BusinessProfile.current()
        if not has_existing_data and profile.name == 'Tani Sejahtera' and \
                profile.subtitle == 'Pertanian dan Perdagangan Hasil Tani':
            profile.name = 'Mina Bahari'
            profile.subtitle = 'Perikanan Tangkap dan Budidaya'
            profile.save(update_fields=['name', 'subtitle'])
        for code, name, category, normal in ACCOUNT_ROWS:
            Account.objects.get_or_create(code=code, defaults={
                'name': name, 'category': category, 'normal_balance': normal})
        self.stdout.write(self.style.SUCCESS(f'{len(ACCOUNT_ROWS)} akun perikanan tersedia.'))
        if has_existing_data:
            self.stdout.write(self.style.WARNING(
                'Data/akun lama terdeteksi; akun yang sudah ada tidak diubah.'
                ' Untuk demo perikanan lengkap gunakan database baru.'))
        if not options['demo']:
            self.stdout.write('Tambahkan --demo untuk contoh stok dan transaksi FIFO.')
            return
        if has_existing_data or any(
                Account.objects.get(code=code).opening_balance != 0
                for code in ('1120', '1150', '3100')):
            raise CommandError('Demo hanya boleh pada database awal tanpa data produk, jurnal, dan akun lama.')
        cash = Account.objects.get(code='1120')
        inventory = Account.objects.get(code='1150')
        equity = Account.objects.get(code='3100')
        cash.opening_balance = Decimal('20000000.00')
        inventory.opening_balance = Decimal('4000000.00')
        equity.opening_balance = Decimal('24000000.00')
        for account in (cash, inventory, equity):
            account.save(update_fields=['opening_balance'])
        tilapia = Product.objects.create(code='IKN-01', name='Ikan Nila Segar',
            unit='kg', sale_price=Decimal('30000'))
        shrimp = Product.objects.create(code='UDG-01', name='Udang Vaname',
            unit='kg', sale_price=Decimal('55000'))
        today = timezone.localdate()
        create_opening_stock(tilapia, Decimal('100'), Decimal('20000'), today)
        create_opening_stock(shrimp, Decimal('50'), Decimal('40000'), today)
        create_stock_movement(product=tilapia, date_value=today, reference='BELI-IKAN-01',
            kind='IN', quantity=Decimal('30'), unit_price=Decimal('22000'),
            settlement_account=cash, description='Pembelian ikan nila segar', user=None)
        create_stock_movement(product=tilapia, date_value=today, reference='JUAL-IKAN-01',
            kind='OUT', quantity=Decimal('110'), unit_price=Decimal('30000'),
            settlement_account=cash, description='Penjualan ikan nila segar', user=None)
        self.stdout.write(self.style.SUCCESS(
            'Demo tersedia. Perhitungan FIFO: 100×20.000 + 10×22.000 = Rp 2.220.000.'))
