import json
from pathlib import Path
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounting.models import Account, Party

REFERENCE = Path(__file__).resolve().parents[3] / 'data' / 'reference_snapshot.json'

class Command(BaseCommand):
    help = 'Muat daftar akun dan kode pembantu dari struktur Excel asli (tanpa jurnal).' 

    @transaction.atomic
    def handle(self, *args, **options):
        if Account.objects.exists() or Party.objects.exists():
            raise CommandError('Akun atau relasi sudah ada. Gunakan database baru agar tidak mencampur dua set saldo awal.')
        payload = json.loads(REFERENCE.read_text(encoding='utf-8'))
        for obj in payload['accounts']:
            Account.objects.create(code=obj['code'], name=obj['name'],
                category=obj['category'], normal_balance=obj['normal_balance'],
                opening_balance=Decimal(obj['opening_balance']), is_header=obj['is_header'])
        for obj in payload['parties']:
            Party.objects.create(code=obj['code'], name=obj['name'], kind=obj['kind'],
                opening_balance=Decimal(obj['opening_balance']))
        self.stdout.write(self.style.SUCCESS(
            f"Impor selesai: {len(payload['accounts'])} akun dan {len(payload['parties'])} relasi."))
        self.stdout.write(self.style.WARNING(
            'CATATAN: Data olahraga Oktober 2025; label C/S di sheet KODE tertukar. '\
            'Jenis relasi dinormalisasi menurut saldo yang cocok (C=pelanggan, S=pemasok). '\
            'Jurnal dan Inventory Card asli tidak diimpor untuk mencegah pencatatan ganda.'))
