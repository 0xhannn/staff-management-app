# Staff Management — Project Handoff & Update Log

> **WAJIB DIBACA AGENT BARU SEBELUM MENGUBAH CODE.**
>
> File ini adalah handoff utama agar project dapat dilanjutkan oleh agent/developer lain tanpa bergantung pada riwayat chat.

## Aturan Wajib

1. Branch canonical repo ini adalah `master` (bukan `main`). Setiap perubahan code yang masuk ke `master` wajib tercatat di file ini.
2. Untuk perubahan bermakna, update **Current State / Architecture / Constraints** dan jelaskan apa yang berubah, kenapa, serta dampaknya.
3. Bagian otomatis di bawah akan mencatat commit/file/diff setiap push ke `master`; itu bukan pengganti catatan arsitektur manual.
4. Jangan menulis secret, password, token, cookie, private key, atau credential ke file ini.
5. Jika dokumentasi dan implementasi berbeda, code terbaru di `master` adalah sumber kebenaran teknis; kemudian perbaiki dokumen ini.

---

## Project Identity

- Repository: `0xhannn/staff-management-app`
- Canonical branch: `master`
- Produk: public starter untuk **staff attendance + tasks + reports**.
- Project **PKL Monitor** adalah produk terpisah dan tidak auto-sync dengan repo ini.
- Stack utama: Python 3.11+, server-side Python, SQLite, HTML/CSS/JS assets.
- Entry/runtime utama: `server.py`, `database.py`.
- Port lokal default menurut setup repo: `8081`.
- Optional object storage: Cloudflare R2 melalui env; aplikasi tetap dapat berjalan tanpa R2 untuk flow yang tidak membutuhkannya.

## Struktur Penting

- `server.py` — HTTP routes, auth/session, role flow, UI/API behavior.
- `database.py` — persistence dan operasi data staff/attendance/tasks/reports/settings.
- `export_formats.py` — format/export attendance/report.
- `static/` — frontend assets.
- `templates/` — HTML templates.
- `.env.example` — nama konfigurasi yang didukung; jangan commit nilai secret.
- `VERSION` — versi aplikasi.
- `install.bat`, `start.bat`, `start-hidden.vbs`, `run.sh` — install/run helpers.
- `SPEC.md` — referensi produk lama; verifikasi terhadap code aktual sebelum mengandalkannya.

## Current State

### Roles / Access

Flow saat ini memiliki beberapa role operasional:

- Staff/Karyawan: attendance dan task milik sendiri.
- Atasan: pasangan staff 1-to-1.
- Manager/Owner: dapat mengelola staff secara lebih luas.
- Admin Room: administrasi user, reset, delete/cascade, dan pengaturan master/admin.

Jangan melemahkan scoping role ketika menambah endpoint atau UI baru. Permission harus dijaga di server, bukan hanya disembunyikan di UI.

### Attendance

- Staff dapat mencatat attendance sesuai flow existing.
- Atasan mengikuti aturan pasangan 1-to-1.
- **Manager dapat mengoreksi attendance staff mana pun**; implementasi terbaru sengaja membypass constraint pasangan 1-to-1 untuk Manager.
- System owner tidak boleh diperlakukan sebagai staff target koreksi.
- Export attendance tersedia dalam beberapa bentuk, termasuk daily PDF/CSV dan tampilan kalender per staff.

### Tasks / Reports

- Manager dapat review/edit/delete task sesuai permission existing.
- Reject task membutuhkan feedback yang valid.
- Data/report yang terkait user/task harus tetap mengikuti ownership dan cascade behavior existing.

### Staff Lifecycle

- Staff mendukung soft-delete/archive + restore.
- Hard-delete adalah tindakan berbeda dan harus mempertahankan guard yang ada.
- Jangan menghapus guard minimum active staff / system owner protection tanpa requirement eksplisit.

### Branding / Upload

- Brand dapat diedit dari area admin yang berwenang.
- Logo upload tersedia.
- R2 bersifat optional; jangan hard-code credential atau bucket secret.

## UX / Product Constraints

- Naming terbaru di UI mengarah ke **Manager / Staff**; jangan hidupkan kembali label lama tanpa alasan produk.
- Manager harus bisa bekerja lintas staff sesuai capability existing, sementara Atasan tetap 1-to-1.
- Flow Windows (`install.bat` → `start.bat`) adalah jalur penggunaan penting dan jangan dirusak oleh perubahan dependency/runtime.
- Repo default adalah `master`; tooling/update script lama pernah bermasalah karena mengasumsikan `main`.

## Verification

Setelah perubahan, minimal:

- jalankan app di environment test;
- smoke test login per role yang terdampak;
- verifikasi permission server-side;
- verifikasi attendance/task/report flow yang disentuh;
- untuk export, buka hasil PDF/CSV/HTML aktual;
- jangan klaim PASS untuk test yang tidak dijalankan.

## Agent Handoff Checklist

Sebelum coding:

- baca `update.md` sampai selesai;
- pull `master` terbaru;
- inspect implementasi aktual di file yang akan disentuh;
- baca `README.md`/`SPEC.md` hanya sebagai pelengkap;
- hindari perubahan production/deploy/data destructive tanpa instruksi eksplisit.

Setelah coding:

- test flow terkait;
- update bagian manual file ini jika behavior/arsitektur/constraint berubah;
- pastikan tidak ada credential masuk commit.

---

## Known Context / Caveats

- Branch canonical adalah `master`, bukan `main`.
- Repo public starter ini bukan PKL Monitor private.
- Dokumentasi lama bisa memakai istilah role lama; code terbaru + handoff ini lebih diprioritaskan.
- Credential yang mungkin sudah ada di konfigurasi lokal/legacy tidak boleh disalin ke handoff baru.

---

<!-- AUTO-CHANGELOG:START -->
## Status `master` terbaru — otomatis

Baseline saat handoff dibuat:

- Commit: `0211eab`
- Message: `fix(v1.6.2): Manager can edit any staff attendance (bypass 1-to-1)`
- Tanggal handoff: 2026-09-14

> Bagian ini akan disegarkan otomatis oleh GitHub Actions pada push code berikutnya ke `master`.
<!-- AUTO-CHANGELOG:END -->

# Change Log Manual

## 2026-09-14

- Menambahkan handoff durable untuk agent berikutnya.
- Mencatat branch canonical `master`, role/permission model, attendance correction Manager, export, staff lifecycle, branding, dan verification rules.


## Audit supplement — 2026-09-14

- Branch utama terverifikasi di GitHub: `master`
- HEAD branch saat supplement dibuat: `9fa5e1ebddf63b94492f28f2e7fc1848aaa9f549`
- Perubahan ini hanya memperbarui dokumentasi handoff; source code, schema, API, environment, dan deployment tidak diubah.
- **Schema/API:** supplement ini tidak menambah atau mengubah schema/API. Detail kontrak existing mengikuti bagian sebelumnya dan source code branch ini.
- **Test/build:** tidak dijalankan ulang pada supplement dokumentasi ini; hasil aktual wajib dicatat setelah perubahan code berikutnya.
- **Deployment:** tidak ada deployment dari perubahan ini. Status live wajib diverifikasi terhadap SHA branch/deployment sebelum diklaim.
- **Rollback:** rollback dokumentasi dilakukan dengan revert commit GitHub yang dibuat oleh operasi ini; jangan reset atau revert commit source code.
- **Blocker:** tidak ada blocker baru yang diverifikasi oleh operasi dokumentasi ini; ikuti blocker existing di bagian sebelumnya.
- **Next step:** setiap perubahan code yang masuk branch utama wajib menambahkan log berisi tanggal, SHA, file/area, schema/API, test, deploy, blocker, dan rollback.
