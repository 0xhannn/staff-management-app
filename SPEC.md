# Staff Management — SPEC

Public starter (fork of PKL Monitor concepts, separate product).

## Product
- **Name**: Staff Management
- **Roles**: Karyawan · Atasan (1-to-1 username) · Owner (master password, view all)
- **Admin Room**: master pass → list users, reset passwords to 123, cascade delete, change master
- **Private PKL Monitor is NOT this app** — no auto-sync

## Local install (Windows)
1. `install.bat`
2. `start.bat` → http://127.0.0.1:8080
3. Update: banner → copy `update.bat` → stop app → run update → `start.bat`

## Defaults
- Master password seed: `parhanganteng` (change in Admin Room)
- Demo users (seed): dual-role password `123` (andi, budi, citra, mentor, staff1)
- DB: `./data/staff.db`
- Owner login: master password only (no staff password)

## Env
See `.env.example`. R2 optional; without it uploads skip gracefully.
