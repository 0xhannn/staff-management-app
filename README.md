# Staff Management

Public starter: **staff attendance + tasks + reports**.

Private **PKL Monitor** is a separate product — no auto-sync with this repo.

## Roles

| Role | Login | Scope |
|------|--------|--------|
| **Karyawan** | username + pass Karyawan | own attendance / tasks |
| **Atasan** | same username + pass Atasan | 1-to-1 staff pair |
| **Owner** | master password only | **all** staff |
| **Admin Room** | master password | user list, reset → `123`, cascade delete, change master |

## Windows

1. Install [Python 3.11+](https://www.python.org/downloads/) (tick **Add to PATH**)
2. Install [Git](https://git-scm.com/)
3. `git clone https://github.com/0xhannn/staff-management-app.git`
4. Double-click **`install.bat`**
5. Double-click **`start.bat`** → http://127.0.0.1:8080
6. Update: stop app → **`update.bat`** → **`start.bat`** (Ctrl+F5)

## Defaults (local seed)

- Demo dual-role users, password **`123`**: `andi`, `budi`, `citra`, `mentor`, `staff1`
- Owner / Admin Room master seed: **`parhanganteng`** (change in Admin Room)
- DB file: `./data/staff.db`

## Env

See `.env.example`. R2 optional — without it, file uploads skip gracefully.
