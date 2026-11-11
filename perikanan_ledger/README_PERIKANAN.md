# MinaBooks: versi antarmuka perikanan

MinaBooks adalah versi **antarmuka perikanan** dari proyek AgriBooks Django. Tema meliputi logo ikan, ilustrasi kapal & ombak, palet warna laut, navigasi, halaman login, dashboard, halaman master produk, dan label form produk.

## Apa yang tidak diubah

- URL dan menu semua modul, termasuk **Jurnal Penyesuaian setelah Buku Besar**.
- CRUD produk, transaksi persediaan masuk/keluar, FIFO, serta jurnal otomatis.
- Jurnal umum, buku besar, buku besar pembantu, neraca saldo, neraca lajur, laba rugi, dan neraca.
- Ekspor Excel keseluruhan dan per laporan, termasuk formula, struktur sheet, akun/kode yang tetap tersedia pada hasil ekspor.
- Autentikasi, validasi debit-kredit, model database, service, export, dan pengujian yang sudah ada.
- **Daftar Akun dan Kode Pembantu tetap tidak muncul di sidebar**, sesuai revisi sebelumnya. URL/fiturnya tetap tersedia bila diperlukan.

## Instalasi database BARU (Windows)

Masuk ke folder `tani_ledger` lalu jalankan:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py makemigrations accounting
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_perikanan --demo
python manage.py runserver
```

Buka `http://127.0.0.1:8000` dan login. Untuk memulai tanpa contoh transaksi, gunakan `python manage.py seed_perikanan` **tanpa** opsi `--demo`.

### Isi demo (hanya database kosong)

Nama usaha **Mina Bahari**, bidang usaha **Perikanan Tangkap dan Budidaya**, bagan akun perikanan, produk **Ikan Nila Segar** dan **Udang Vaname**, contoh pembelian dan penjualan nila menggunakan FIFO. Total saldo awal akun telah dibuat berimbang, contoh FIFO HPP = Rp2.220.000.

Perlu dicatat bahwa **kode akun akuntansi tetap**. Ini sengaja dilakukan karena sistem memakai kode tertentu, seperti 1150 (persediaan), 5110 (HPP), dan 4110 (penjualan), untuk jurnal otomatis. Mengubah kode tersebut tanpa menyesuaikan seluruh relasi dapat merusak pembukuan.

## Menggunakan database yang sudah ada

Jangan hapus database lama. Karena permintaan ini mengutamakan antarmuka, **transaksi, nama akun, dan produk yang sudah tersimpan tidak otomatis diganti menjadi perikanan**. Buka **Pengaturan Usaha** untuk mengganti nama/subtitle bisnis, lalu tambahkan atau sunting produk sesuai kebutuhan. Nama akun dapat diubah bila masih sesuai aturan sistem. Jangan menjalankan mode `--demo` pada database aktif.

## Penting tentang ruang lingkup

Aplikasi tetap merupakan sistem pembukuan dan manajemen persediaan FIFO, bukan aplikasi pelacakan kapal, perhitungan tonase tangkapan otomatis, pakan ikan, suhu kolam, atau pencatatan hasil budidaya terpisah. Fitur semacam itu memerlukan pengembangan fungsi baru dan sengaja **tidak ditambahkan**.

Dokumentasi akuntansi asli dan penjelasan fitur ada pada `README.md` dan `CHANGELOG_REVISI.md`.
