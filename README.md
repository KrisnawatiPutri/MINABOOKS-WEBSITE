# MINABOOKS: Website Akuntansi Perikanan Django

Sistem informasi akuntansi **single-company** berbasis Django 5.2 LTS, SQLite,
HTML/CSS/JavaScript vanilla, dan openpyxl untuk ekspor Excel **dengan rumus aktif**. Antarmuka
responsif, tampilan modern, dashboard grafik, pencarian tabel, form jurnal
dinamis, dan laporan terhubung.

## 1. Komputer & aplikasi yang dibutuhkan

- Windows 10/11, macOS, atau Linux
- Python **3.10–3.14** (disarankan 3.12/3.13)
- VS Code (disarankan) dan koneksi internet **saat pertama menginstal paket**
- Browser Chrome/Edge/Firefox

## 2. Panduan instalasi dari NOL (Windows PowerShell)

1. Instal Python dari https://www.python.org/downloads/ . Saat instalasi,
   aktifkan **Add Python to PATH**. Pastikan dengan `py --version`.
2. Ekstrak file `tani_ledger.zip`.
3. Klik kanan folder `tani_ledger`, buka VS Code, lalu **Terminal > New Terminal**.
4. Jalankan perintah berikut satu per satu di PowerShell:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   python manage.py makemigrations accounting
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py seed_agriculture --demo
   python manage.py runserver
   ```

   Masukkan username, email (boleh kosong), dan password saat `createsuperuser`.
   **Password memang tidak muncul saat diketik**, ini normal.

   Jika PowerShell menolak menjalankan skrip aktivasi, dalam terminal yang sama:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
   ```

   Jika perintah `py` tidak ditemukan, gunakan `python`.

5. Buka **http://127.0.0.1:8000/** dan login menggunakan superuser tadi.
6. Buka **Pengaturan Usaha** untuk mengganti nama, alamat, telepon, dan profil usaha.
7. Setelah menjalankan server, tutup dengan `Ctrl+C`.

### Instalasi berikutnya (setelah komputer direstart)

```powershell
cd path\ke\tani_ledger
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py makemigrations accounting
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_agriculture --demo
python manage.py runserver
```

### Penting: dua opsi data awal, **pilih salah satu**

- `python manage.py seed_agriculture` membuat akun-akun khusus pertanian **dengan saldo nol**.
- `python manage.py seed_agriculture --demo` juga menambah contoh kas, modal, produk, pembelian, penjualan, dan stok FIFO, sehingga dashboard langsung terisi. **Ini hanya data simulasi.**
- `python manage.py seed_reference` mengisi **akun dan kode pembantu** seperti file Excel olahraga yang diunggah. Saldo awal tetap seimbang. Perintah ini tidak mengimpor jurnal/inventory asli dan harus dijalankan pada database kosong yang belum menjalankan perintah seed lainnya.

Jangan jalankan dua seed berbeda pada database yang sama. Untuk mulai benar-benar
baru, buat database baru lalu `migrate`, kemudian pilih `seed_agriculture` tanpa demo.

## 3. Fitur dan padanan Excel

| Excel | Halaman website | Keterangan |
|---|---|---|
| MENU | Dashboard | KPI keuangan, transaksi terakhir, grafik bulanan |
| AKUN | **Disembunyikan dari sidebar** | Master tetap di database dan selalu ada pada Excel ekspor; URL `/accounts/` tetap bisa diakses jika perlu pemeliharaan |
| KODE | **Disembunyikan dari sidebar** | Kode pelanggan/pemasok tetap digunakan pada formulir dan selalu disertakan dalam ekspor; URL `/parties/` tetap ada |
| JU JP | Jurnal Umum | Pencatatan berpasangan dan jurnal otomatis persediaan |
| BB | Buku Besar | Saldo berjalan menurut kode akun |
| JU JP (bagian JP) | **Jurnal Penyesuaian** | Halaman tersendiri **tepat setelah Buku Besar**, mem-posting penyesuaian akhir periode |
| BB PEMBANTU | Buku Besar Pembantu | Saldo per relasi |
| NERACA LAJUR | Neraca Lajur | NS, penyesuaian, NS disesuaikan, LR, Neraca |
| LABA RUGI | Laba Rugi | Pendapatan minus seluruh beban |
| NERACA | Neraca | Aset = kewajiban + ekuitas + laba berjalan |
| INVENTORY CARD | Inventory Card | FIFO per produk, stok dan biaya lapisan |
| (tambahan) | Neraca Saldo | Uji kesetimbangan debet/kredit |
| (tambahan) | Pengaturan Usaha | Nama usaha untuk seluruh halaman dan XLSX |

Halaman laporan memiliki tombol **Ekspor Excel**; semua tombol mengekspor workbook
**12 sheet saling terhubung** agar formula tidak kehilangan dependensi. Saat mengekspor dari
halaman tertentu, file terbuka langsung pada sheet yang diminta.

## 4. Alur penggunaan

1. Tentukan akun standar. Untuk akun baru bila perlu buka `/accounts/` secara langsung. Menu tersebut disembunyikan, tidak dihapus.
2. Bila perlu, buat pelanggan atau pemasok melalui URL `/parties/`. Kode relasi juga bisa dipilih pada jurnal.
3. Untuk transaksi yang tidak menggerakkan persediaan (misalnya pembayaran
   listrik, modal, beban) gunakan **Jurnal Umum > Tambah Jurnal**.
4. Untuk penyesuaian akhir periode, buka **Jurnal Penyesuaian** setelah **Buku Besar**.
5. Untuk pembelian/penjualan barang yang memengaruhi stok, gunakan **Inventory
   Card > Transaksi Stok**. Sistem membuat **jurnal otomatis**.
6. Buka **Buku Besar**, **Neraca Saldo**, **Neraca Lajur**, **Laba Rugi**, dan **Neraca**.
7. Pilih tanggal dan tekan **Ekspor Excel**.

### Contoh pencatatan manual

Penerimaan modal Rp5.000.000:

- Debet `1120 - Kas Tunai`: `5.000.000`
- Kredit `3100 - Modal Pemilik`: `5.000.000`

Pembayaran air Rp100.000:

- Debet `6130 - Beban Listrik dan Air`: `100.000`
- Kredit `1120 - Kas Tunai`: `100.000`

### Contoh FIFO yang ada pada `--demo`

- Saldo awal beras: 100 kg × Rp20.000 = Rp2.000.000
- Pembelian baru: 30 kg × Rp22.000 = Rp660.000
- Penjualan: 110 kg × Rp30.000 = Rp3.300.000
- **HPP FIFO**: 100 × Rp20.000 + 10 × Rp22.000 = Rp2.220.000
- Sisa stok: 20 kg × Rp22.000 = Rp440.000
- Jurnal penjualan: Dr Kas 3.300.000 / Cr Penjualan 3.300.000;
  Dr HPP 2.220.000 / Cr Persediaan 2.220.000

### Angka asli Excel yang penting

File referensi berisi **10 sheet** dengan transaksi bisnis olahraga pada Oktober
2025, bukan pertanian. Akun memiliki saldo awal **Rp2.138.700.000** pada sisi
debet maupun kredit. Inventory Card menggunakan **FIFO**. Di sheet KODE,
`C001-C003` tertulis Account Payable tetapi totalnya Rp48.100.000 cocok dengan
saldo piutang `1140`. `S001-S003` tertulis Account Receivable tetapi totalnya
Rp63.000.000 cocok dengan saldo utang `2110`.

Perintah `seed_reference` **menormalisasi klasifikasi** C→pelanggan dan
S→pemasok, bukan menyalin label yang keliru.

## 5. Ekspor Excel DINAMIS (revisi)

Semua tombol **Ekspor Excel** menghasilkan `.xlsx` dengan 12 sheet berisi rumus
antar-sheet, termasuk **AKUN** dan **KODE** walaupun kedua menu master tersembunyi
dari sidebar web. File yang diekspor merupakan salinan data **saat ekspor**,
bukan tautan online langsung ke database Django.

Sheet dan sumber hitung:

| Sheet | Fungsi dan hubungan formula |
|---|---|
| AKUN | Saldo awal debet/kredit, jenis akun, pos laporan, editable |
| KODE | Nama relasi, jenis piutang/utang, saldo awal, editable |
| JURNAL UMUM | Nominal input biru; jurnal stok otomatis merujuk INVENTORY CARD |
| BUKU BESAR | Nominal jurnal dan saldo berjalan merujuk dua sheet jurnal |
| JURNAL PENYESUAIAN | Input koreksi periodik tersendiri |
| BB PEMBANTU | Saldo awal KODE dan perubahan dari jurnal per relasi |
| NERACA SALDO | Saldo AKUN + `SUMIF` debet/kredit di kedua jurnal |
| NERACA LAJUR | NS sebelum penyesuaian, JP, NS disesuaikan, LR, Neraca |
| LABA RUGI | Angka merujuk NERACA LAJUR, rumus laba rugi |
| NERACA | Saldo merujuk NERACA LAJUR dan laba rugi berjalan |
| PRODUK | Daftar barang, stok dan nilai FIFO dari INVENTORY CARD |
| INVENTORY CARD | Kuantitas/harga input, HPP FIFO & nilai saldo dengan rumus `MAX`, `MIN`, dan `SUM` untuk alokasi per lot |

### Uji perubahan nilai di Excel

1. Jalankan web, isi satu transaksi, lalu **Ekspor Semua Excel**.
2. Buka berkas menggunakan **Microsoft Excel**, pilih **Enable Editing** bila muncul.
3. Edit **angka debet** atau **kredit** pada JURNAL UMUM atau JURNAL PENYESUAIAN.
4. Buku Besar, Neraca Saldo, Neraca Lajur, Laba Rugi, Neraca dan BB Pembantu
   akan **menghitung ulang ketika file dibuka/dihitung Excel**.
5. Untuk stok, coba ubah **jumlah masuk** atau **harga beli** pada INVENTORY CARD;
   HPP FIFO, nilai stok, jurnal otomatis dan laporan ikut terhitung kembali.
6. Pastikan kolom *Selisih (harus 0)* pada jurnal dan selisih di NERACA tetap 0.
   Jika mengedit hanya sisi debit, neraca akan tidak seimbang sampai sisi kredit
   pasangannya dikoreksi. Ini peringatan, bukan kesalahan perhitungan.

**Batas penting:** perubahan yang dibuat pada file Excel **tidak mengubah**
database website. Jika menambah/menghapus baris transaksi, mengganti kode akun,
memindahkan tanggal atau urutan FIFO, atau mengganti klasifikasi akun, ekspor
ulang dari web agar seluruh grouping Buku Besar, laporan, dan FIFO diregenerasi.
Rumus diperuntukkan terutama bagi perubahan **nominal, kuantitas, dan harga pada
baris yang telah diekspor**. Spreadsheet tidak mengecek semua aturan
validasi Django (misalnya kuantitas stok tidak boleh negatif).

Saat file pertama kali dibuka di viewer yang **tidak punya mesin kalkulasi Excel**,
sel formula mungkin tampil kosong sampai dibuka menggunakan Excel/LibreOffice
untuk menghitung ulang. Pengaturan `fullCalcOnLoad` dan `calcMode=auto` diaktifkan
pada workbook.

## 6. Apa yang sudah didukung vs batasan

**Sudah ada:** login/logout, daftar akun, kode pembantu, jurnal berpasangan,
halaman khusus jurnal penyesuaian setelah buku besar, buku besar pembantu, neraca saldo, neraca lajur,
laba rugi, neraca, master produk, FIFO berlapis, jurnal otomatis stok,
pencegahan stok minus, ekspor workbook 12 sheet saling terhubung dengan rumus, pengaturan
nama usaha, filter tanggal, pencarian tabel dan mobile sidebar.

**Batasan versi awal:**

- **Satu perusahaan** dalam satu database. Bukan multi-tenant atau ERP multi-cabang.
- Pembukuan menggunakan **saldo awal + transaksi kumulatif**, belum tersedia
  penutupan buku otomatis per tahun atau laporan laba rugi per rentang bulan.
- Akun saldo awal dan stok awal harus **dicocokkan manual**; tidak otomatis
  mengoreksi perbedaan antara nilai stok fisik dan akun Persediaan.
- Jurnal terposting tidak dapat diedit atau dihapus melalui UI. Koreksi
  dilakukan lewat jurnal pembalik; fitur pembalikan otomatis belum tersedia.
- Penjualan/pembelian barang melalui inventory otomatis membuat jurnal. Jangan
  mencatat transaksi yang sama di jurnal manual, karena akan **dobel**.
- Untuk biaya panen/produksi pertanian yang lebih rumit (aset biologis, WIP,
  penyusutan tanaman), perlu modul khusus. Aplikasi ini model dagang sederhana.
- FIFO tidak mengizinkan **backdate** mutasi stok. Pergerakan stok harus diinput
  kronologis.
- Kode akun `1140` dan `2110` dipakai khusus untuk buku pembantu piutang dan
  utang. Jika mengubah bagan akun, sesuaikan kode tersebut di kode program.
- Belum ada fitur ekspor PDF, unggah/impor Excel lewat UI, faktur pembelian,
  multi-gudang, tutup buku, audit log penuh, atau peran pengguna terperinci.
- Aplikasi ini ditujukan untuk pengembangan / demo awal, bukan software
  akuntansi tersertifikasi. Sebelum dipakai untuk data keuangan riil,
  verifikasi saldo pembuka, laporan dan pembatasan akses.

## 7. Menjalankan test otomatis

```powershell
python manage.py test accounting
python manage.py check
```

Untuk tes keamanan produksi:

```powershell
python manage.py check --deploy
```

Perintah `check --deploy` akan mengingatkan kebutuhan SSL/HTTPS, `DEBUG=0`,
`SECRET_KEY` acak, cookie secure, dan konfigurasi deployment lain.

## 8. Pengembangan & deployment lanjutan

- **Development:** SQLite cukup, tetapi untuk penggunaan bersamaan dan
  transaksi penting gunakan PostgreSQL.
- Amankan `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_DEBUG=0`, HTTPS,
  backup database, dan akses superuser.
- Setelah project stabil, buat migration versioned (`makemigrations`) dan commit
  ke Git. Di paket ini migrasi belum dibundel agar file dapat dibangkitkan sesuai
  versi Django yang terpasang.
- Instalasi awal memerlukan internet untuk mendapatkan paket dari PyPI.
- Untuk modifikasi desain: `accounting/static/accounting/css/app.css`.
- Untuk logika akuntansi: `accounting/services.py`.
- Untuk form: `accounting/forms.py`.
- Untuk halaman: `accounting/views.py` dan `accounting/templates/accounting/`.
- Untuk workbook ekspor: `accounting/exports.py`.

## 9. Struktur folder

```text
tani_ledger/
  manage.py
  requirements.txt
  README.md
  config/
    settings.py, urls.py, asgi.py, wsgi.py
  accounting/
    models.py, forms.py, services.py, views.py, exports.py, urls.py
    admin.py, context_processors.py
    management/commands/
      seed_agriculture.py, seed_reference.py
    tests/
      test_accounting.py
    templatetags/money.py
    templates/accounting/
      base.html, dashboard.html, ...
    static/accounting/
      css/app.css
      js/app.js
  data/
    reference_snapshot.json
```

