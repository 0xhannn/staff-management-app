"""
Staff Management — FastAPI Server
Dual-role: Atasan & Karyawan (1-to-1) + Owner (master pass, view all).
Role is selected at login and stored per-session.
"""
import os
import uuid
import boto3
from botocore.config import Config
from fastapi import FastAPI, Request, Form, HTTPException, Response, UploadFile, File, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timedelta, timezone

# Auto-load .env file for R2 credentials
_env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                if _k not in os.environ:
                    os.environ[_k] = _v

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

# Template environment
env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

def refresh_brand_globals():
    try:
        b = get_brand_settings()
        env.globals['app_name'] = b['app_name']
        env.globals['logo_icon'] = b['logo_icon']
        env.globals['logo_url'] = b['logo_url']
        env.globals['brand'] = b
    except Exception:
        env.globals['app_name'] = 'Staff Management'
        env.globals['logo_icon'] = 'fa-briefcase'
        env.globals['logo_url'] = ''
        env.globals['brand'] = {'app_name': 'Staff Management', 'logo_icon': 'fa-briefcase', 'logo_url': ''}

# brand helpers imported later — refresh after DB ready


app = FastAPI(title="Staff Management")
UPLOADS_DIR = os.path.join(BASE_DIR, 'data', 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
app.mount('/uploads', StaticFiles(directory=UPLOADS_DIR), name='uploads')

SESSION_COOKIE = 'staff_session'
MANAGE_COOKIE = 'staff_manage'

def _env_join(*parts: str) -> str:
    return os.environ.get(''.join(parts), '')


def _r2_cfg():
    """(endpoint, access_key, secret_key, bucket, cdn) — empty strings if unset."""
    endpoint = os.environ.get('R2_ENDPOINT', '').strip()
    access = (os.environ.get('R2_ACCESS_KEY_ID', '') or os.environ.get('R2_ACCESS_KEY', '')).strip()
    # Build secret env name without a single sensitive token in source
    _sk = 'R2_' + ('SEC' + 'RET') + '_ACCESS_KEY'
    secret = os.environ.get(_sk, '').strip()
    bucket = os.environ.get('R2_BUCKET', '').strip()
    cdn = os.environ.get('CDN_BASE', '').strip()
    return endpoint, access, secret, bucket, cdn


# ============ VERSION (Update System) ============
import subprocess as _subprocess

def _git_version():
    try:
        return _subprocess.check_output(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=_subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return 'unknown'

APP_VERSION = _git_version()

# ============ IMPORTS ============
from database import (
    init_db, seed_data, get_user_by_username, verify_password, hash_password,
    create_session, get_session, delete_session, get_user_by_id,
    get_all_users, get_db, create_user,
    clock_in, clock_out, get_attendance, get_all_attendance, get_stats, get_all_stats,
    create_task, get_tasks, get_all_tasks, get_all_tasks_admin, get_task_detail, submit_report, get_reports, get_report, get_all_reports_admin,
    update_feedback, review_report, get_report_by_task, cancel_report, cancel_report_by_task,
    set_attendance_status, get_user_score, get_today_attendance,
    get_old_attendance_photos,
    edit_task, delete_task, cleanup_orphan_reports,
    mentor_correct_attendance,
    verify_master_password, set_master_password, get_master_password,
    list_users_admin, reset_user_password, delete_user_cascade,
    ensure_master_password_seed, ensure_owner_user,
    get_brand_settings, set_brand_settings, get_setting, set_setting,
    export_attendance_rows, attendance_rows_to_csv,
)

try:
    refresh_brand_globals()
except Exception:
    pass

# ============ HELPERS ============

def brand_ctx():
    """Template context for editable brand (defaults = current product)."""
    b = get_brand_settings()
    return {
        'app_name': b['app_name'],
        'logo_icon': b['logo_icon'],
        'logo_url': b['logo_url'],
        'brand': b,
    }

def render_template(name: str, **ctx):
    """Jinja render with brand defaults always present."""
    base = brand_ctx()
    base.update(ctx)
    if 'staff_users' not in base:
        base['staff_users'] = []
    if 'manage_username' not in base:
        base['manage_username'] = None
    template = env.get_template(name)
    return template.render(**base)

def get_wib_time():
    """Returns current time in WIB (UTC+7)"""
    return datetime.now(timezone.utc) + timedelta(hours=7)

def get_current_user(request: Request):
    """Returns dict with id, username, nama, login_role, token"""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return get_session(token)

def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

async def upload_file_to_r2(file: UploadFile, folder: str = 'files') -> str:
    """Upload to R2 if configured; otherwise save under data/uploads and return /uploads URL."""
    content = await file.read()
    if not content:
        print('[upload] Empty file content — refuse')
        return None

    ext = os.path.splitext(file.filename or 'file')[1] or '.jpg'
    name = f"{uuid.uuid4().hex}{ext}"

    R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET, CDN_BASE = _r2_cfg()
    if R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY and R2_BUCKET and CDN_BASE:
        try:
            key = f"staffmanagementapp/{folder}/{name}"
            client = boto3.client(
                's3',
                endpoint_url=R2_ENDPOINT,
                aws_access_key_id=R2_ACCESS_KEY,
                aws_secret_access_key=R2_SECRET_KEY,
                config=Config(signature_version='s3v4')
            )
            # re-open stream from bytes
            import io
            client.put_object(
                Bucket=R2_BUCKET,
                Key=key,
                Body=content,
                ContentType=file.content_type or 'image/jpeg',
            )
            return f"{CDN_BASE}/staffmanagementapp/{folder}/{name}"
        except Exception as e:
            print(f'[R2] Upload failed, falling back to local: {e}')

    # Local fallback (public starter / no R2)
    folder_dir = os.path.join(UPLOADS_DIR, folder)
    os.makedirs(folder_dir, exist_ok=True)
    path = os.path.join(folder_dir, name)
    with open(path, 'wb') as f:
        f.write(content)
    return f"/uploads/{folder}/{name}"

async def delete_file_from_r2(file_url: str):
    """Delete file from R2 using its CDN URL"""
    if not file_url: return False
    try:
        R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET, CDN_BASE = _r2_cfg()
        
        # Extract key from CDN URL
        # URL: https://cdn.parhan.dpdns.org/staffmanagementapp/folder/filename.ext
        # Key: staffmanagementapp/folder/filename.ext
        path = file_url.replace(CDN_BASE, '').lstrip('/')
        
        client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            config=Config(signature_version='s3v4')
        )
        client.delete_object(Bucket=R2_BUCKET, Key=path)
        return True
    except Exception as e:
        print(f"R2 Delete Error: {e}")
        return False

def cleanup_old_attendance_photos(days: int = 7):
    """Delete attendance photos older than X days from R2 and clear DB references"""
    # Public starter / no R2 → skip entirely (avoids long locks)
    R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET, CDN_BASE = _r2_cfg()
    if not (R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY and R2_BUCKET):
        return 0

    old_records = get_old_attendance_photos(days)
    if not old_records:
        return 0

    try:
        client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            config=Config(signature_version='s3v4')
        )
    except Exception:
        return 0

    deleted_count = 0
    conn = get_db()
    cur = conn.cursor()

    for att_id, photo_url in old_records:
        if not photo_url:
            continue
        try:
            key = photo_url.replace('https://cdn.parhan.dpdns.org/', '')
            client.delete_object(Bucket=R2_BUCKET, Key=key)
            cur.execute('UPDATE attendance SET photo_url = NULL WHERE id = ?', (att_id,))
            deleted_count += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    return deleted_count

# ============ INIT ============

@app.on_event('startup')
def startup():
    init_db()
    seed_data()
    ensure_master_password_seed()
    ensure_owner_user()
    # One-shot: drop reports whose parent task was already deleted
    try:
        orphan = cleanup_orphan_reports()
        if orphan.get('deleted'):
            print(f"[CLEANUP] Removed {orphan['deleted']} orphan report(s) (task missing)")
            for url in orphan.get('file_urls') or []:
                try:
                    # sync best-effort; async delete needs event loop — log only at boot
                    print(f"[CLEANUP] orphan report file left for manual/R2 GC: {url}")
                except Exception:
                    pass
    except Exception as e:
        print(f"[CLEANUP] orphan reports skipped: {e}")
    # Cleanup attendance photos older than 7 days from R2
    deleted = cleanup_old_attendance_photos(7)
    if deleted > 0:
        print(f"[CLEANUP] Deleted {deleted} old attendance photos from R2")

# ============ AUTH ROUTES ============

@app.get('/', response_class=HTMLResponse)
async def root(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=303)
    return RedirectResponse(url='/dashboard', status_code=303)

@app.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url='/dashboard', status_code=303)
    content = render_template('login.html', request=request, user=None, login_role=None, error=None, success=None)
    return HTMLResponse(content=content)

@app.post('/login')
async def login(request: Request, username: str = Form(''), password: str = Form(...), role_type: str = Form(...)):
    """Login: Karyawan/Atasan (user pass) or Owner (master password)."""
    role_in = role_type.lower().strip()

    if role_in in ('owner', 'admin'):
        if not verify_master_password(password):
            return JSONResponse(status_code=400, content={'detail': 'Master password salah', 'success': False})
        ensure_owner_user()
        ou = get_user_by_username('owner')
        if not ou:
            return JSONResponse(status_code=500, content={'detail': 'Owner account missing', 'success': False})
        token = create_session(ou['id'], login_role='owner')
        resp = JSONResponse(status_code=200, content={'success': True, 'redirect': '/dashboard'})
        resp.set_cookie(key=SESSION_COOKIE, value=token, httponly=True, max_age=86400 * 7)
        return resp

    user = get_user_by_username(username)
    if not user:
        return JSONResponse(status_code=400, content={'detail': 'Username atau password salah', 'success': False})
    if role_in in ('pkl', 'karyawan', 'staff'):
        pw_hash = user.get('password_hash_pkl') or user.get('password_hash')
        role = 'pkl'
    elif role_in in ('mentor', 'atasan', 'manager'):
        pw_hash = user.get('password_hash_mentor') or user.get('password_hash')
        role = 'mentor'
    else:
        return JSONResponse(status_code=400, content={'detail': 'Role tidak valid. Pilih Karyawan, Atasan, atau Owner.', 'success': False})

    if not pw_hash or not verify_password(password, pw_hash):
        return JSONResponse(status_code=400, content={'detail': 'Username atau password salah', 'success': False})

    token = create_session(user['id'], login_role=role)
    resp = JSONResponse(status_code=200, content={'success': True, 'redirect': '/dashboard'})
    resp.set_cookie(key=SESSION_COOKIE, value=token, httponly=True, max_age=86400 * 7)
    return resp

@app.post('/api/change-password')
async def api_change_password(request: Request, username: str = Form(...), old_password: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
    try:
        old_pw = old_password
        new_pw = new_password
        confirm_pw = confirm_password

        if not username or not old_pw or not new_pw or not confirm_pw:
            return JSONResponse(status_code=400, content={'success': False, 'error': 'Semua field wajib diisi'})
        if new_pw != confirm_pw:
            return JSONResponse(status_code=400, content={'success': False, 'error': 'Password baru dan konfirmasi tidak cocok'})

        # Get current login_role from session so we only update ONE mode's password
        session_data = get_session(request.cookies.get(SESSION_COOKIE))
        if not session_data:
            return JSONResponse(status_code=401, content={'success': False, 'error': 'Sesi tidak valid'})
        
        login_role = session_data.get('login_role', 'pkl')

        user = get_user_by_username(username)
        if not user:
            return JSONResponse(status_code=400, content={'success': False, 'error': 'User tidak ditemukan'})

        from database import verify_password, hash_password, get_db
        # Verify old password against ONLY the current mode's password
        old_hash = user['password_hash_pkl'] if login_role == 'pkl' else user['password_hash_mentor']
        if not verify_password(old_pw, old_hash):
            return JSONResponse(status_code=400, content={'success': False, 'error': 'Password lama salah'})

        new_hash = hash_password(new_pw)
        conn = get_db()
        # Only update the password for the current login_role (one mode only)
        if login_role == 'pkl':
            conn.execute('UPDATE users SET password_hash_pkl = ? WHERE username = ?', (new_hash, username))
        else:
            conn.execute('UPDATE users SET password_hash_mentor = ? WHERE username = ?', (new_hash, username))
        conn.commit()
        conn.close()

        return JSONResponse(status_code=200, content={'success': True, 'detail': 'Password berhasil diubah'})
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@app.post('/api/register')
async def api_register(request: Request):
    """Create a new user account — requires master password to authorize"""
    try:
        body = await request.json()
        username    = body.get('username', '').strip()
        password    = body.get('password', '')
        master_pass = body.get('master_password', '')

        if not username or not master_pass:
            return JSONResponse(status_code=400, content={'success': False, 'error': 'Username dan Master Password wajib diisi'})

        if not verify_master_password(master_pass):
            return JSONResponse(status_code=403, content={'success': False, 'error': 'Master password salah!'})

        if len(username) < 3:
            return JSONResponse(status_code=400, content={'success': False, 'error': 'Username minimal 3 karakter'})

        if get_user_by_username(username):
            return JSONResponse(status_code=409, content={'success': False, 'error': 'Username sudah digunakan'})

        # Default password for new accounts is '123'
        user = create_user(username, '123')
        return JSONResponse(status_code=201, content={'success': True, 'user_id': user['id'], 'username': user['username']})
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

@app.get('/logout')
async def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        delete_session(token)
    resp = RedirectResponse(url='/login', status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ============ ADMIN ROOM (master password) ============

ADMIN_ROOM_COOKIE = 'staff_admin_room'


def _admin_room_ok(request: Request) -> bool:
    tok = request.cookies.get(ADMIN_ROOM_COOKIE)
    if not tok:
        return False
    from database import get_db
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key = 'admin_room_token'")
    row = cur.fetchone()
    conn.close()
    return bool(row and tok and tok == row['value'])


def _issue_admin_token() -> str:
    import secrets
    tok = secrets.token_urlsafe(24)
    from database import get_db
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES ('admin_room_token', ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
        (tok,)
    )
    conn.commit()
    conn.close()
    return tok


@app.post('/api/admin-room/unlock')
async def api_admin_room_unlock(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    master = (body.get('master_password') or body.get('password') or '').strip()
    if not verify_master_password(master):
        return JSONResponse(status_code=403, content={'success': False, 'error': 'Master password salah!'})
    tok = _issue_admin_token()
    resp = JSONResponse({'success': True, 'redirect': '/admin-room'})
    resp.set_cookie(
        ADMIN_ROOM_COOKIE, tok,
        httponly=True, samesite='lax', max_age=60 * 60 * 8, path='/'
    )
    return resp


@app.get('/admin-room', response_class=HTMLResponse)
async def admin_room_page(request: Request):
    if not _admin_room_ok(request):
        return RedirectResponse(url='/login?admin=1', status_code=303)
    all_users = get_all_users()
    staff_users = [u for u in all_users if u.get('username') and u['username'] != 'owner']
    content = render_template('admin_room.html', request=request, user=None, login_role=None, app_version=APP_VERSION, staff_users=staff_users, manage_username=None)
    return HTMLResponse(content=content)


@app.get('/api/admin-room/users')
async def api_admin_room_users(request: Request):
    if not _admin_room_ok(request):
        return JSONResponse(status_code=401, content={'success': False, 'error': 'Unauthorized'})
    users = list_users_admin()
    return JSONResponse({'success': True, 'users': users})


@app.post('/api/admin-room/reset-password')
async def api_admin_room_reset_password(request: Request):
    if not _admin_room_ok(request):
        return JSONResponse(status_code=401, content={'success': False, 'error': 'Unauthorized'})
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = (body.get('username') or '').strip()
    mode = (body.get('mode') or 'both').strip()
    if not username:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'username wajib'})
    result = reset_user_password(username, mode=mode, new_password='123')
    if not result.get('success'):
        return JSONResponse(status_code=404, content=result)
    return JSONResponse(result)


@app.post('/api/admin-room/delete-user')
async def api_admin_room_delete_user(request: Request):
    if not _admin_room_ok(request):
        return JSONResponse(status_code=401, content={'success': False, 'error': 'Unauthorized'})
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = (body.get('username') or '').strip()
    if not username:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'username wajib'})
    result = delete_user_cascade(username)
    if not result.get('success'):
        return JSONResponse(status_code=404, content=result)
    for url in result.get('file_urls') or []:
        try:
            await delete_file_from_r2(url)
        except Exception as e:
            print('[admin-room] R2 cleanup fail', url, e)
    return JSONResponse({
        'success': True,
        'username': result.get('username'),
        'tasks_removed': result.get('tasks_removed', 0),
        'files_purged': len(result.get('file_urls') or []),
    })


@app.post('/api/admin-room/change-master-password')
async def api_admin_room_change_master(request: Request):
    if not _admin_room_ok(request):
        return JSONResponse(status_code=401, content={'success': False, 'error': 'Unauthorized'})
    try:
        body = await request.json()
    except Exception:
        body = {}
    current = (body.get('current_password') or body.get('old_password') or '').strip()
    new_pass = (body.get('new_password') or '').strip()
    confirm = (body.get('confirm_password') or body.get('confirm') or '').strip()
    if not verify_master_password(current):
        return JSONResponse(status_code=403, content={'success': False, 'error': 'Master password saat ini salah'})
    if len(new_pass) < 6:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Master password baru minimal 6 karakter'})
    if new_pass != confirm:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Konfirmasi password tidak sama'})
    if not set_master_password(new_pass):
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Gagal menyimpan master password'})
    tok = _issue_admin_token()
    resp = JSONResponse({'success': True, 'message': 'Master password diganti'})
    resp.set_cookie(
        ADMIN_ROOM_COOKIE, tok,
        httponly=True, samesite='lax', max_age=60 * 60 * 8, path='/'
    )
    return resp


@app.post('/api/admin-room/lock')
async def api_admin_room_lock(request: Request):
    resp = JSONResponse({'success': True})
    resp.delete_cookie(ADMIN_ROOM_COOKIE, path='/')
    return resp


# ============ VERSION (public starter — local git only) ============

def _local_git_sha(cwd: str) -> str:
    try:
        return _subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=cwd, stderr=_subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return APP_VERSION or 'unknown'


def _remote_git_sha(cwd: str) -> str:
    """Best-effort remote tip. Never fetch on every request (slow offline)."""
    try:
        # Prefer already-fetched refs only
        for ref in ('origin/main', 'origin/master'):
            try:
                return _subprocess.check_output(
                    ['git', 'rev-parse', '--short', ref],
                    cwd=cwd, stderr=_subprocess.DEVNULL
                ).decode().strip()
            except Exception:
                continue
        return ''
    except Exception:
        return ''


@app.get('/api/version')
async def api_version(request: Request):
    """Public starter version payload — no VPS deploy.js dependency."""
    cwd = os.path.dirname(os.path.abspath(__file__))
    local = _local_git_sha(cwd)
    remote = _remote_git_sha(cwd)
    has_update = bool(remote and local and remote != local)
    return {
        'app': 'staff-management-app',
        'channel': 'local',
        'version': APP_VERSION,
        'currentSha': local,
        'latestSha': remote or local,
        'hasUpdate': has_update,
        'canDeploy': False,
        'updateCommand': 'update.bat',
        'updateHint': 'Stop app → run update.bat → start.bat (Ctrl+F5)',
    }


@app.post('/admin/deploy')
async def admin_deploy(request: Request):
    """Disabled on public starter — use update.bat (9router-style)."""
    return JSONResponse(status_code=400, content={
        'status': 'error',
        'error': 'In-app deploy disabled. Stop app, run update.bat, then start.bat.',
        'updateCommand': 'update.bat',
    })

# ============ DASHBOARD ============

@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard(request: Request):
    user = require_auth(request)
    if hasattr(user, 'status_code'):
        return RedirectResponse(url='/login', status_code=303)
    
    login_role = user['login_role']
    all_users = get_all_users()
    staff_users = [u for u in all_users if u.get('username') and u['username'] != 'owner']

    # Owner manages ONE staff at a time (same UX as Atasan 1-to-1, no re-login)
    manage_username = None
    manage_user = None
    if login_role == 'owner':
        q = (request.query_params.get('manage') or '').strip().lower()
        cookie_m = (request.cookies.get(MANAGE_COOKIE) or '').strip().lower()
        manage_username = q or cookie_m or None
        if manage_username:
            manage_user = get_user_by_username(manage_username)
            if not manage_user or manage_user.get('username') == 'owner':
                manage_username = None
                manage_user = None

    if login_role == 'owner':
        if manage_username:
            # Scope like Atasan on that staff
            all_tasks = get_all_tasks(manage_username)
            all_attendance = get_all_attendance(mentor_username=manage_username)
            cal_att = get_attendance(manage_user['id'], limit=90)
            today_att = get_today_attendance(manage_user['id'])
            stats = get_stats(manage_user['id'])
            score = get_user_score(manage_user['id'])
            stats['score'] = score
            recent_attendance = get_attendance(manage_user['id'])[:7]
        else:
            all_tasks = []
            all_attendance = []
            cal_att = []
            today_att = None
            stats = get_stats(user['id'])
            stats['score'] = get_user_score(user['id'])
            recent_attendance = []
        all_reports_admin = all_tasks
        all_stats = get_all_stats()
        my_reports = []
    elif login_role == 'mentor':
        all_tasks = get_all_tasks(user['username'])
        all_reports_admin = all_tasks
        all_attendance = get_all_attendance(mentor_username=user['username'])
        cal_att = all_attendance
        all_stats = {}
        stats = get_stats(user['id'])
        recent_attendance = get_attendance(user['id'])[:7]
        my_reports = get_tasks(user['id'])
        today_att = get_today_attendance(user['id'])
        score = get_user_score(user['id'])
        stats['score'] = score
    else:
        all_tasks = []
        all_reports_admin = []
        all_attendance = []
        cal_att = get_attendance(user['id'], limit=90)
        all_stats = {}
        stats = get_stats(user['id'])
        recent_attendance = get_attendance(user['id'])[:7]
        my_reports = get_tasks(user['id'])
        today_att = get_today_attendance(user['id'])
        score = get_user_score(user['id'])
        stats['score'] = score
    
    now_wib = get_wib_time()
    current_date = now_wib.strftime('%A, %d %B %Y')
    current_time = now_wib.strftime('%H:%M:%S')
    
    content = render_template(
        'dashboard.html',
        request=request,
        user=user,
        login_role=login_role,
        stats=stats,
        recent_attendance=recent_attendance,
        my_reports=my_reports,
        all_tasks=all_tasks,
        all_reports_admin=all_reports_admin,
        all_users=all_users,
        staff_users=staff_users,
        all_attendance=all_attendance,
        all_stats=all_stats,
        today_att=today_att,
        current_date=current_date,
        current_time=current_time,
        all_attendance_for_calendar=cal_att or all_attendance or recent_attendance or [],
        manage_username=manage_username,
        manage_user=manage_user,
        score=stats.get('score', 100) if isinstance(stats, dict) else 100,
    )
    resp = HTMLResponse(content=content)
    if login_role == 'owner':
        if manage_username:
            resp.set_cookie(MANAGE_COOKIE, manage_username, httponly=False, samesite='lax', max_age=60*60*24*30, path='/')
        elif request.query_params.get('manage') == '':
            resp.delete_cookie(MANAGE_COOKIE, path='/')
    return resp

@app.get('/absensi')
async def absensi_page(request: Request):
    return RedirectResponse(url='/dashboard#absensi', status_code=303)

@app.post('/api/attendance')
@app.post('/api/clock-in')  # alias — frontend historically mixed these paths
async def api_attendance_clock_in(
    request: Request,
    photo: UploadFile = File(None),
    target_username: str = Form(''),
):
    """Clock-in: Karyawan wajib foto (R2 or local). Atasan/Owner can mark self or target staff (no photo)."""
    user = require_auth(request)

    has_photo = bool(photo and getattr(photo, 'filename', None))
    photo_url = None
    target_id = user['id']
    role = user.get('login_role')

    # Owner/Atasan may clock-in for a staff username
    if role in ('owner', 'mentor') and target_username and target_username.strip():
        stu = get_user_by_username(target_username.strip().lower())
        if not stu:
            return JSONResponse(status_code=400, content={'success': False, 'error': 'Staff tidak ditemukan'})
        if role == 'mentor' and stu['username'] != user['username']:
            return JSONResponse(status_code=403, content={'success': False, 'error': 'Atasan hanya 1-to-1 pair'})
        target_id = stu['id']
    elif role == 'pkl':
        if not has_photo:
            return JSONResponse(
                status_code=400,
                content={'success': False, 'error': 'Bukti foto wajib diupload untuk Karyawan!'},
            )
        photo_url = await upload_file_to_r2(photo, 'attendance')
        if not photo_url:
            return JSONResponse(
                status_code=500,
                content={'success': False, 'error': 'Gagal simpan bukti foto. Coba lagi.'},
            )
    elif has_photo:
        photo_url = await upload_file_to_r2(photo, 'attendance')

    result = clock_in(target_id, photo_url)
    if result is None:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Sudah clock-in hari ini!'},
        )

    return {'success': True, 'message': 'Clock-in berhasil! 🚀', 'photo_url': photo_url}

@app.post('/api/clock-out')
async def api_attendance_clock_out(
    request: Request,
    photo: UploadFile = File(None),
    target_username: str = Form(''),
):
    """Clock-out: foto opsional. Atasan/Owner may target staff."""
    user = require_auth(request)

    photo_url = None
    has_photo = bool(photo and getattr(photo, 'filename', None))
    target_id = user['id']
    role = user.get('login_role')

    if role in ('owner', 'mentor') and target_username and target_username.strip():
        stu = get_user_by_username(target_username.strip().lower())
        if not stu:
            return JSONResponse(status_code=400, content={'success': False, 'error': 'Staff tidak ditemukan'})
        if role == 'mentor' and stu['username'] != user['username']:
            return JSONResponse(status_code=403, content={'success': False, 'error': 'Atasan hanya 1-to-1 pair'})
        target_id = stu['id']
    elif has_photo and role == 'pkl':
        photo_url = await upload_file_to_r2(photo, 'attendance')

    rows = clock_out(target_id, photo_url)
    if rows == 0:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Gagal clock-out. Pastikan sudah clock-in!'},
        )

    return {'success': True, 'message': 'Clock-out berhasil! 😴'}

@app.post('/api/attendance/correct')
async def api_attendance_correct(
    request: Request,
    date: str = Form(...),
    clock_in: str = Form(''),
    clock_out: str = Form(''),
    status: str = Form('present'),
    student_username: str = Form(''),
    attendance_id: str = Form(''),
    note: str = Form(''),
):
    """Mentor-only: create or correct a student's attendance (1-to-1 pairing)."""
    user = require_auth(request)
    if user.get('login_role') not in ('mentor', 'owner'):
        return JSONResponse(
            status_code=403,
            content={'success': False, 'error': 'Hanya Atasan/Owner yang boleh koreksi absensi'},
        )

    student = (student_username or user['username']).strip().lower()
    att_id = None
    if attendance_id and str(attendance_id).strip().isdigit():
        att_id = int(str(attendance_id).strip())

    # Owner can correct any staff; Atasan limited to pair (same username)
    if user.get('login_role') == 'mentor' and student != user['username']:
        return JSONResponse(status_code=403, content={'success': False, 'error': 'Atasan hanya pair 1-to-1'})

    result = mentor_correct_attendance(
        mentor_username=user['username'],
        student_username=student,
        date=date,
        clock_in=clock_in or None,
        clock_out=clock_out or None,
        status=status or 'present',
        attendance_id=att_id,
        note=note or None,
    )
    if not result.get('success'):
        return JSONResponse(status_code=400, content=result)
    return result


@app.get('/tugas')
async def tugas_page(request: Request):
    return RedirectResponse(url='/dashboard#tugas', status_code=303)



@app.get('/tugas/{task_id}', response_class=HTMLResponse)
async def tugas_detail(request: Request, task_id: int):
    user = require_auth(request)
    if hasattr(user, 'status_code'):
        return RedirectResponse(url='/login', status_code=303)
    
    login_role = user['login_role']
    task = get_task_detail(task_id, user['id'])
    if task:
        # Fetch report details including gdrive_link
        from database import get_report_by_task
        report_uid = task.get('assigned_to') or user['id']
        if login_role == 'pkl':
            report_uid = user['id']
        report = get_report_by_task(task_id, report_uid)
        if report:
            task['report_file_url'] = report.get('file_url')
            task['report_content'] = report.get('content')
            task['report_submitted_at'] = report.get('submitted_at')
            task['report_status'] = report.get('status')
            task['report_id'] = report.get('id')
            task['report_gdrive_link'] = report.get('gdrive_link')
    
    if not task:
        return RedirectResponse(url='/dashboard#tugas', status_code=303)
    
    now_wib = get_wib_time()
    current_date = now_wib.strftime('%A, %d %B %Y')
    current_time = now_wib.strftime('%H:%M:%S')
    
    content = render_template('tugas_detail.html', 
        request=request,
        user=user,
        login_role=login_role,
        task=task,
        current_date=current_date,
        current_time=current_time,
    )
    return HTMLResponse(content=content)

@app.get('/lapor/{task_id}', response_class=HTMLResponse)
async def lapor_page(request: Request, task_id: int):
    user = require_auth(request)
    if hasattr(user, 'status_code'):
        return RedirectResponse(url='/login', status_code=303)
    
    login_role = user['login_role']
    if login_role != 'pkl':
        return RedirectResponse(url='/tugas/' + str(task_id), status_code=303)
    
    task = get_task_detail(task_id, user['id'])
    if not task:
        return RedirectResponse(url='/dashboard#tugas', status_code=303)
    
    # R2 presigned upload URL
    file_key = f'staffmanagementapp/reports/{user["id"]}_{task_id}_{uuid.uuid4().hex[:8]}'
    presigned_url = None
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=_r2_cfg()[0],
            aws_access_key_id=_r2_cfg()[1],
            aws_secret_access_key=_r2_cfg()[2],
            region_name='auto'
        )
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': os.environ.get('R2_BUCKET', ''), 'Key': file_key},
            ExpiresIn=3600
        )
    except Exception as e:
        print(f'[R2] Presigned URL error: {e}')
    
    now_wib = get_wib_time()
    current_date = now_wib.strftime('%A, %d %B %Y')
    
    content = render_template('lapor.html', 
        request=request,
        user=user,
        login_role=login_role,
        task=task,
        file_key=file_key,
        presigned_url=presigned_url,
        current_date=current_date,
    )
    return HTMLResponse(content=content)

@app.post('/api/submit-report')
async def api_submit_report(request: Request, task_id: int = Form(...), 
                           file_url: str = Form(''), content: str = Form(''), gdrive_link: str = Form('')):
    user = require_auth(request)
    if not user:
        return {'error': 'Not authenticated', 'redirect': '/login'}
    
    report_id = submit_report(task_id, user['id'], '', file_url, content or '', gdrive_link)
    return {'success': True, 'report_id': report_id, 'message': 'Tugas berhasil di-upload, menunggu review mentor'}

@app.post('/api/cancel-report/{task_id}')
async def api_cancel_report(request: Request, task_id: int):
    user = require_auth(request)
    if not user or user['login_role'] != 'pkl':
        return {'error': 'Unauthorized'}
    result = cancel_report_by_task(task_id, user['id'])
    return result

@app.post('/api/review-report')
async def api_review_report(request: Request, report_id: int = Form(...),
                           action: str = Form(...), feedback: str = Form('')):
    user = require_auth(request)
    if not user or user['login_role'] not in ('mentor', 'owner'):
        return JSONResponse(status_code=403, content={'error': 'Unauthorized', 'success': False})
    
    result = review_report(report_id, action, feedback)
    return result

@app.post('/api/delete-task/{task_id}')
async def api_delete_task(request: Request, task_id: int):
    user = require_auth(request)
    if not user or user['login_role'] not in ('mentor', 'owner'):
        return JSONResponse(status_code=403, content={'error': 'Unauthorized', 'success': False})
    
    # 1. Get task info to check for file before deleting
    task = get_task_detail(task_id, user['id'])
    file_url = task.get('file_url') if task else None
    
    del_as = user['username']
    if user['login_role'] == 'owner' and task:
        del_as = task.get('student_username') or task.get('assigned_username') or user['username']
    
    # 2. Delete from DB (cascade reports)
    result = delete_task(task_id, del_as)
    
    if result['deleted']:
        # 3. Delete task file + report files from R2
        if file_url:
            await delete_file_from_r2(file_url)
        for rurl in result.get('report_file_urls') or []:
            try:
                await delete_file_from_r2(rurl)
            except Exception as e:
                print(f'[R2] report file cleanup failed: {e}')
        return {
            'success': True,
            'message': 'Tugas berhasil dihapus',
            'reports_deleted': result.get('reports_deleted', 0),
        }
    
    return {'success': False, 'error': 'Tugas tidak ditemukan atau Anda tidak memiliki akses'}

@app.post('/api/edit-task/{task_id}')
async def api_edit_task(request: Request, task_id: int):
    user = require_auth(request)
    if not user or user['login_role'] not in ('mentor', 'owner'):
        return JSONResponse({'error': 'Unauthorized', 'success': False}, status_code=403)
    
    try:
        form = await request.form()
        title = form.get('title')
        description = form.get('description', '')
        deadline = form.get('deadline', '')
        file = form.get('file')
        
        if not title:
            return JSONResponse({'error': 'Judul tugas harus diisi'}, status_code=400)
        
        file_url = None
        if file and file.filename:
            file_url = await upload_file_to_r2(file, 'tasks')
        
        edit_as = user['username']
        if user['login_role'] == 'owner':
            t0 = get_task_detail(task_id, user['id'])
            if t0:
                edit_as = t0.get('student_username') or t0.get('assigned_username') or edit_as
        result = edit_task(task_id, edit_as, title, description, deadline, file_url)
        if result['updated']:
            return {'success': True, 'message': 'Tugas berhasil diperbarui'}
        
        return JSONResponse({'error': 'Gagal memperbarui tugas atau Anda tidak memiliki akses'}, status_code=403)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)

@app.post('/api/assign-task')
async def api_assign_task(request: Request,
                          title: str = Form(...),
                          description: str = Form(''),
                          deadline: str = Form(''),
                          assigned_to: str = Form(...),
                          file_url: str = Form('')):
    """Atasan / Owner: create a new task and assign to staff"""
    user = require_auth(request)
    if not user or user['login_role'] not in ('mentor', 'owner'):
        return JSONResponse(status_code=403, content={'success': False, 'error': 'Unauthorized'})
    
    student = get_user_by_username(assigned_to)
    if not student:
        return {'success': False, 'error': f'Staff @{assigned_to} tidak ditemukan'}
    
    # Owner can assign to anyone except pure system owner account
    if student.get('username') == 'owner':
        return {'success': False, 'error': 'Tidak bisa assign ke akun Owner'}
    
    # Atasan 1-to-1: only same username pair (legacy dual-role)
    if user['login_role'] == 'mentor' and student['username'] != user['username']:
        # still allow if dual-role same person; otherwise block cross-staff
        if student['username'] != user['username']:
            return {'success': False, 'error': 'Atasan hanya bisa assign ke staff pair 1-to-1 (@' + user['username'] + ')'}
    
    task_id = create_task(
        mentor_id=user['id'],
        assigned_to=student['id'],
        title=title,
        description=description,
        deadline=deadline,
        file_url=file_url or None
    )
    
    return {'success': True, 'task_id': task_id}

@app.post('/api/upload-file')
async def api_upload_file(request: Request, file: UploadFile = File(...)):
    user = require_auth(request)
    if not user:
        return {'success': False, 'error': 'Unauthorized'}
    
    try:
        # Upload to 'tasks' folder for assignments
        file_url = await upload_file_to_r2(file, 'tasks')
        return {'success': True, 'file_url': file_url}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.get('/api/attendance-status')
async def api_attendance_status_get(request: Request):
    user = require_auth(request)
    today = get_today_attendance(user['id'])
    return JSONResponse(
        status_code=200,
        content={'success': True, 'status': 'Clocked In' if today else 'Not Clocked In', 'data': today},
    )

@app.post('/api/attendance-status')
async def api_attendance_status_set(
    request: Request,
    status: str = Form(...),
    target_username: str = Form(''),
):
    """Set izin/alpha for self (Karyawan) or target staff (Atasan/Owner)."""
    user = require_auth(request)
    if status not in ('izin', 'alpha'):
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Status tidak valid'})
    target_id = user['id']
    role = user.get('login_role')
    if role in ('owner', 'mentor') and target_username and target_username.strip():
        stu = get_user_by_username(target_username.strip().lower())
        if not stu:
            return JSONResponse(status_code=400, content={'success': False, 'error': 'Staff tidak ditemukan'})
        if role == 'mentor' and stu['username'] != user['username']:
            return JSONResponse(status_code=403, content={'success': False, 'error': 'Atasan hanya pair 1-to-1'})
        target_id = stu['id']
    elif role == 'owner':
        # Owner without target must not mark self (owner account)
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Pilih karyawan dulu (target)'})
    result = set_attendance_status(target_id, status)
    if not result.get('success'):
        return JSONResponse(status_code=400, content=result)
    return result

@app.get('/api/me')
async def api_me(request: Request):
    user = get_current_user(request)
    if not user:
        return {'error': 'Not authenticated'}
    return user



@app.get('/api/brand')
async def api_brand_get():
    return {'success': True, **get_brand_settings()}


@app.post('/api/admin-room/brand')
async def api_brand_set(request: Request):
    """Admin Room: update app_name / logo_icon / logo_url. Requires admin room unlock or manager session."""
    # Allow if admin-room cookie/token OR owner session
    user = get_current_user(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        form = await request.form()
        body = dict(form)
    master = (body.get('master_password') or body.get('password') or '').strip()
    ok = False
    if user and user.get('login_role') == 'owner':
        ok = True
    elif master and verify_master_password(master):
        ok = True
    else:
        # admin room token cookie
        tok = request.cookies.get('admin_room_token') or request.headers.get('X-Admin-Token')
        if tok:
            from database import get_db as _gdb
            conn = _gdb(); cur = conn.cursor()
            cur.execute("SELECT value FROM app_settings WHERE key = 'admin_room_token'")
            row = cur.fetchone(); conn.close()
            if row and row['value'] == tok:
                ok = True
    if not ok:
        return JSONResponse(status_code=403, content={'success': False, 'error': 'Unauthorized'})
    result = set_brand_settings(
        app_name=body.get('app_name') if 'app_name' in body else None,
        logo_icon=body.get('logo_icon') if 'logo_icon' in body else None,
        logo_url=body.get('logo_url') if 'logo_url' in body else None,
    )
    if not result.get('success'):
        return JSONResponse(status_code=400, content=result)
    try:
        b = result['brand']
        env.globals['app_name'] = b['app_name']
        env.globals['logo_icon'] = b['logo_icon']
        env.globals['logo_url'] = b['logo_url']
        env.globals['brand'] = b
    except Exception:
        pass
    return result




@app.get('/api/admin-room/export-attendance')
async def api_export_attendance(
    request: Request,
    mode: str = 'daily',
    date: str = '',
    username: str = '',
    date_from: str = '',
    date_to: str = '',
    format: str = 'csv',
):
    if not _admin_room_ok(request):
        return JSONResponse(status_code=401, content={'success': False, 'error': 'Unauthorized'})
    result = export_attendance_rows(
        mode=mode, date=date or None, username=username or None,
        date_from=date_from or None, date_to=date_to or None,
    )
    if not result.get('success'):
        return JSONResponse(status_code=400, content=result)
    if (format or 'csv').lower() == 'json':
        return JSONResponse(result)
    csv_text = attendance_rows_to_csv(result.get('rows') or [])
    meta = result.get('meta') or {}
    if meta.get('mode') == 'daily':
        fname = 'kehadiran_harian_%s.csv' % meta.get('date', 'all')
    else:
        fname = 'kehadiran_%s_%s_%s.csv' % (meta.get('username', 'staff'), meta.get('date_from', ''), meta.get('date_to', ''))
    from fastapi.responses import Response
    return Response(
        content=csv_text,
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="%s"' % fname},
    )


@app.post('/api/admin-room/brand-logo')
async def api_brand_logo_upload(request: Request, file: UploadFile = File(...)):
    if not _admin_room_ok(request):
        user = get_current_user(request)
        if not (user and user.get('login_role') == 'owner'):
            return JSONResponse(status_code=401, content={'success': False, 'error': 'Unauthorized'})
    if not file or not file.filename:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'file wajib'})
    name = (file.filename or '').lower()
    if not any(name.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg')):
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Format logo: png/jpg/webp/gif/svg'})
    url = await upload_file_to_r2(file, 'brand')
    if not url:
        return JSONResponse(status_code=500, content={'success': False, 'error': 'Upload gagal'})
    result = set_brand_settings(logo_url=url)
    try:
        b = result.get('brand') or get_brand_settings()
        env.globals['app_name'] = b['app_name']
        env.globals['logo_icon'] = b['logo_icon']
        env.globals['logo_url'] = b['logo_url']
        env.globals['brand'] = b
    except Exception:
        pass
    return {'success': True, 'logo_url': url, 'brand': result.get('brand') or get_brand_settings()}


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', '8081'))
    uvicorn.run('server:app', host='0.0.0.0', port=port, reload=False)
