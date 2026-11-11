from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, BusinessProfile, JournalEntry, JournalLine, Party, Product
from accounting.services import (create_opening_stock, create_stock_movement,
                                  ledger, period_totals, report_balances, stock_card)

D = Decimal


class AccountingFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester', password='strong-test-pass-123')
        self.client.force_login(self.user)
        self.profile = BusinessProfile.current()
        self.cash = Account.objects.create(code='1120', name='Kas', category='ASSET',
            normal_balance='D', opening_balance=D('20000000'))
        self.stock = Account.objects.create(code='1150', name='Persediaan', category='ASSET',
            normal_balance='D', opening_balance=D('4000000'))
        self.equity = Account.objects.create(code='3100', name='Modal', category='EQUITY',
            normal_balance='C', opening_balance=D('24000000'))
        self.sales = Account.objects.create(code='4110', name='Penjualan', category='REVENUE', normal_balance='C')
        self.cogs = Account.objects.create(code='5110', name='HPP', category='COGS', normal_balance='D')
        self.receivable = Account.objects.create(code='1140', name='Piutang', category='ASSET', normal_balance='D')
        self.payable = Account.objects.create(code='2110', name='Utang', category='LIABILITY', normal_balance='C')
        self.product = Product.objects.create(code='PADI', name='Beras', unit='kg', sale_price=D('30000'))
        create_opening_stock(self.product, D('100'), D('20000'), date(2026, 10, 1))

    def test_trial_balance_opening(self):
        rows = report_balances(date(2026, 10, 1))
        self.assertEqual(sum(x['debit'] for x in rows), D('24000000'))
        self.assertEqual(sum(x['credit'] for x in rows), D('24000000'))
        self.assertEqual(period_totals()['difference'], 0)

    def test_fifo_cost_and_automatic_balanced_journals(self):
        create_stock_movement(product=self.product, date_value=date(2026, 10, 2),
            reference='BELI-01', kind='IN', quantity=D('30'), unit_price=D('22000'),
            settlement_account=self.cash, description='Pembelian')
        movement = create_stock_movement(product=self.product, date_value=date(2026, 10, 3),
            reference='JUAL-01', kind='OUT', quantity=D('110'), unit_price=D('30000'),
            settlement_account=self.cash, description='Penjualan')
        self.assertEqual(movement.cost_amount, D('2220000'))
        self.assertEqual(movement.sales_amount, D('3300000'))
        self.assertEqual(movement.allocations.count(), 2)
        card = stock_card(self.product)
        self.assertEqual(card['qty'], D('20'))
        self.assertEqual(card['value'], D('440000'))
        self.assertEqual(period_totals()['profit'], D('1080000'))
        self.assertEqual(period_totals()['difference'], 0)
        for j in JournalEntry.objects.all():
            self.assertEqual(j.total_debit, j.total_credit)

    def test_negative_stock_and_backdate_rejected_without_partial_journal(self):
        before = JournalEntry.objects.count()
        with self.assertRaises(ValidationError):
            create_stock_movement(product=self.product, date_value=date(2026, 10, 2),
                reference='JUAL-BESAR', kind='OUT', quantity=D('101'), unit_price=D('30000'),
                settlement_account=self.cash, description='Melebihi stok')
        self.assertEqual(JournalEntry.objects.count(), before)
        create_stock_movement(product=self.product, date_value=date(2026, 10, 3),
            reference='BELI-02', kind='IN', quantity=D('2'), unit_price=D('21000'),
            settlement_account=self.cash, description='Pembelian kedua')
        with self.assertRaises(ValidationError):
            create_stock_movement(product=self.product, date_value=date(2026, 10, 2),
                reference='BELI-BACKDATE', kind='IN', quantity=D('1'), unit_price=D('21000'),
                settlement_account=self.cash, description='Terlarang')

    def test_party_validation(self):
        supplier = Party.objects.create(code='S001', name='Pemasok', kind='SUPPLIER')
        entry = JournalEntry.objects.create(date=date(2026, 10, 1), reference='MAN-001', description='Cek')
        line = JournalLine(entry=entry, account=self.receivable, party=supplier,
                           debit=D('100'), credit=D('0'))
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_income_and_stock_excel_export(self):
        for kind in ('all','accounts','parties','journal','ledger','subsidiary','trial',
                     'worksheet','income','balance','products','inventory'):
            response = self.client.get(reverse('export', args=[kind]))
            self.assertEqual(response.status_code, 200, kind)
            self.assertEqual(response.content[:2], b'PK')
            self.assertIn('.xlsx', response['Content-Disposition'])

    def test_login_required_and_settings(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
        self.client.force_login(self.user)
        res = self.client.post(reverse('settings'), data={
            'name': 'Kebun Ceria', 'subtitle': 'Pertanian', 'address': '', 'phone': '',
            'email': '', 'owner': '', 'inventory_account_code': '1150',
            'cogs_account_code': '5110', 'sales_account_code': '4110',
        })
        self.assertEqual(res.status_code, 302)
        self.assertEqual(BusinessProfile.current().name, 'Kebun Ceria')

    def test_new_journal_rejects_unbalanced(self):
        response = self.client.post(reverse('journal_new'),data={
            'date': '2026-10-10', 'reference': 'JV-01', 'description': 'Contoh', 'kind': 'GENERAL',
            'lines-TOTAL_FORMS': '2', 'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '2', 'lines-MAX_NUM_FORMS': '30',
            'lines-0-account':str(self.cash.id), 'lines-0-debit':'100000', 'lines-0-credit':'0',
            'lines-1-account':str(self.equity.id),'lines-1-debit':'0','lines-1-credit':'90000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_new_journal_posts_valid_lines(self):
        response = self.client.post(reverse('journal_new'), data={
            'date':'2026-10-10','reference':'JV-OK','description':'Setoran','kind':'GENERAL',
            'lines-TOTAL_FORMS':'2','lines-INITIAL_FORMS':'0',
            'lines-MIN_NUM_FORMS':'2','lines-MAX_NUM_FORMS':'30',
            'lines-0-account':str(self.cash.id),'lines-0-debit':'100000','lines-0-credit':'0',
            'lines-1-account':str(self.equity.id),'lines-1-debit':'0','lines-1-credit':'100000',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.first().lines.count(), 2)
        self.assertEqual(ledger(self.cash)['closing'],D('20100000'))

    def test_adjustment_is_separate_and_cannot_be_forged_as_general(self):
        response = self.client.post(reverse('adjustment_new'), data={
            'date': '2026-10-10', 'reference': 'AJP-01',
            'description': 'Jurnal penyesuaian akhir periode', 'kind': 'GENERAL',
            'lines-TOTAL_FORMS': '2', 'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '2', 'lines-MAX_NUM_FORMS': '30',
            'lines-0-account': str(self.cash.pk), 'lines-0-debit': '12000', 'lines-0-credit': '0',
            'lines-1-account': str(self.equity.pk), 'lines-1-debit': '0', 'lines-1-credit': '12000',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(JournalEntry.objects.get(reference='AJP-01').kind, JournalEntry.Kind.ADJUSTMENT)
        self.assertContains(self.client.get(reverse('adjustment_list')), 'AJP-01')
        self.assertNotContains(self.client.get(reverse('journal_list')), 'AJP-01')
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Daftar Akun')
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Kode Pembantu')

    def test_excel_has_live_cross_sheet_formulas(self):
        from io import BytesIO
        from openpyxl import load_workbook
        self.client.post(reverse('journal_new'),data={
            'date': '2026-10-10', 'reference': 'JV-42', 'description': 'Penjualan jasa',
            'lines-TOTAL_FORMS': '2', 'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '2', 'lines-MAX_NUM_FORMS': '30',
            'lines-0-account': str(self.cash.pk), 'lines-0-debit': '250000', 'lines-0-credit': '0',
            'lines-1-account': str(self.sales.pk), 'lines-1-debit': '0', 'lines-1-credit': '250000',
        })
        self.client.post(reverse('adjustment_new'), data={
            'date': '2026-10-11', 'reference': 'AJP-42', 'description': 'Penyesuaian',
            'lines-TOTAL_FORMS': '2', 'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '2', 'lines-MAX_NUM_FORMS': '30',
            'lines-0-account': str(self.cash.pk), 'lines-0-debit': '1000', 'lines-0-credit': '0',
            'lines-1-account': str(self.equity.pk), 'lines-1-debit': '0', 'lines-1-credit': '1000',
        })
        create_stock_movement(product=self.product, date_value=date(2026, 10, 12),
            reference='BELI-XLSX', kind='IN', quantity=D('30'), unit_price=D('22000'),
            settlement_account=self.cash, description='Pembelian FIFO untuk Excel')
        create_stock_movement(product=self.product, date_value=date(2026, 10, 13),
            reference='JUAL-XLSX', kind='OUT', quantity=D('110'), unit_price=D('30000'),
            settlement_account=self.cash, description='Penjualan FIFO untuk Excel')
        response = self.client.get(reverse('export', args=['all']) + '?to=2026-11-01')
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.content), data_only=False)
        self.assertEqual(len(wb.worksheets), 12)
        for tab in ('AKUN', 'KODE', 'JURNAL UMUM', 'BUKU BESAR',
                    'JURNAL PENYESUAIAN', 'BB PEMBANTU', 'NERACA SALDO',
                    'NERACA LAJUR', 'LABA RUGI', 'NERACA', 'PRODUK', 'INVENTORY CARD'):
            self.assertIn(tab, wb.sheetnames)
        self.assertEqual(wb.sheetnames[3:5], ['BUKU BESAR','JURNAL PENYESUAIAN'])
        self.assertIn('SUMIF', wb['NERACA SALDO']['D5'].value)
        self.assertIn('JURNAL PENYESUAIAN', wb['NERACA SALDO']['D5'].value)
        self.assertIn('NERACA LAJUR', wb['LABA RUGI']['D5'].value)
        self.assertIn('LABA RUGI', next(
            c.value for row in wb['NERACA'].iter_rows() for c in row
            if c.data_type == 'f' and 'LABA RUGI' in c.value))
        self.assertIn('MIN', wb['INVENTORY CARD']['U7'].value)
        self.assertIn('SUM', wb['INVENTORY CARD']['N7'].value)
        self.assertEqual(wb.calculation.calcMode, 'auto')
