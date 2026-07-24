"""
Staff Management — Database Module
SQLite dual-role: every user can access BOTH Mentor & PKL views.
Role is stored per-session, not per-user.
"""
import sqlite3
import bcrypt
import uuid
import os
from datetime import datetime, timedelta

# Public starter: local SQLite only (./data/staff.db).
# Optional override: env DB_PATH. Never auto-pick private offtree paths.
_LOCAL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'staff.db')

def _resolve_db_path() -> str:
    env = os.environ.get('DB_PATH', '').strip()
    if env:
        return env
    return _LOCAL_DB

DB_PATH = _resolve_db_path()

def get_db():
    path = _resolve_db_path()
    # ensure parent dir exists when using data-dir path
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
    except Exception:
        pass
    return conn

def init_db():
    """Initialize database schema — NO role column on users"""
    conn = get_db()
    cur = conn.cursor()

    # Users table — NO role column, every user is universal
    # score: tracks compliance, defaults to 100, decremented on alpha
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nama TEXT NOT NULL,
            score INTEGER DEFAULT 100,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration: add score column if it doesn't exist (for existing DBs)
    cur.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cur.fetchall()]
    if 'score' not in cols:
        cur.execute('ALTER TABLE users ADD COLUMN score INTEGER DEFAULT 100')

    # Soft-delete: deleted_at on users (NULL = active)
    cur.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cur.fetchall()]
    if 'deleted_at' not in cols:
        cur.execute('ALTER TABLE users ADD COLUMN deleted_at TEXT')


    # Dual-password + role columns
    cur.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cur.fetchall()]
    if 'password_hash_pkl' not in cols:
        cur.execute('ALTER TABLE users ADD COLUMN password_hash_pkl TEXT')
    if 'password_hash_mentor' not in cols:
        cur.execute('ALTER TABLE users ADD COLUMN password_hash_mentor TEXT')
    if 'role' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'pkl'")

    # Backfill dual hashes from legacy password_hash
    cur.execute(
        "UPDATE users SET "
        "password_hash_pkl = COALESCE(NULLIF(password_hash_pkl, ''), password_hash), "
        "password_hash_mentor = COALESCE(NULLIF(password_hash_mentor, ''), password_hash) "
        "WHERE password_hash IS NOT NULL"
    )

    cur.execute(
        "CREATE TABLE IF NOT EXISTS app_settings ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL, "
        "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )


    # Attendance table — linked to user only, no role
    cur.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            clock_in TEXT,
            clock_out TEXT,
            date TEXT NOT NULL,
            status TEXT DEFAULT 'present',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # attendance photo_url (R2)
    cur.execute("PRAGMA table_info(attendance)")
    att_cols = [row[1] for row in cur.fetchall()]
    if 'photo_url' not in att_cols:
        cur.execute('ALTER TABLE attendance ADD COLUMN photo_url TEXT')

    # Tasks table — atasan assigns to staff (same user table)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mentor_id INTEGER NOT NULL,
            assigned_to INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'pending',
            file_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mentor_id) REFERENCES users(id),
            FOREIGN KEY (assigned_to) REFERENCES users(id)
        )
    ''')
    # Migration: file_url on tasks (attachment for assignment)
    cur.execute('PRAGMA table_info(tasks)')
    task_cols = [row[1] for row in cur.fetchall()]
    if 'file_url' not in task_cols:
        cur.execute('ALTER TABLE tasks ADD COLUMN file_url TEXT')

    # Reports table — staff uploads, atasan reviews
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            file_path TEXT,
            file_url TEXT,
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            feedback TEXT,
            graded INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Migration: add file_url + status + content + gdrive_link columns to existing reports table
    cur.execute("PRAGMA table_info(reports)")
    report_cols = [row[1] for row in cur.fetchall()]
    if 'file_url' not in report_cols:
        cur.execute('ALTER TABLE reports ADD COLUMN file_url TEXT')
    if 'status' not in report_cols:
        cur.execute("ALTER TABLE reports ADD COLUMN status TEXT DEFAULT 'pending'")
    if 'content' not in report_cols:
        cur.execute('ALTER TABLE reports ADD COLUMN content TEXT')
    if 'gdrive_link' not in report_cols:
        cur.execute('ALTER TABLE reports ADD COLUMN gdrive_link TEXT')

    # Sessions table — stores login_role per session (mentor | pkl | owner)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            login_role TEXT NOT NULL CHECK(login_role IN ('mentor', 'pkl', 'owner')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    # Migrate older DBs that only allowed mentor|pkl (SQLite cannot ALTER CHECK)
    try:
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'")
        row = cur.fetchone()
        sql = (row[0] if row else '') or ''
        if sql and 'owner' not in sql:
            cur.execute('ALTER TABLE sessions RENAME TO sessions_old')
            cur.execute('''
                CREATE TABLE sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    login_role TEXT NOT NULL CHECK(login_role IN ('mentor', 'pkl', 'owner')),
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            cur.execute(
                'INSERT INTO sessions (token, user_id, login_role, created_at) '
                'SELECT token, user_id, login_role, created_at FROM sessions_old '
                "WHERE login_role IN ('mentor', 'pkl', 'owner')"
            )
            cur.execute('DROP TABLE sessions_old')
    except Exception as e:
        print('[migrate] sessions owner role:', e)

    conn.commit()
    conn.close()

# ===== Password Hashing =====

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except Exception:
        return False

# ===== User Operations =====

def get_user_by_username(username: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cur.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cur.fetchone()
    conn.close()
    return dict(user) if user else None


def is_user_archived(user_or_username) -> bool:
    """True if user is soft-deleted."""
    if not user_or_username:
        return False
    if isinstance(user_or_username, dict):
        if 'deleted_at' in user_or_username:
            return bool(user_or_username.get('deleted_at'))
        username = user_or_username.get('username')
        uid = user_or_username.get('id')
    else:
        username = str(user_or_username)
        uid = None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cur.fetchall()}
    if 'deleted_at' not in cols:
        conn.close()
        return False
    if uid:
        cur.execute('SELECT deleted_at FROM users WHERE id = ?', (uid,))
    else:
        cur.execute('SELECT deleted_at FROM users WHERE username = ?', ((username or '').strip().lower(),))
    row = cur.fetchone()
    conn.close()
    return bool(row and row['deleted_at'])

def get_all_users(include_archived: bool = False):
    """Get all users (for mentor to assign tasks). Excludes soft-deleted by default."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cur.fetchall()}
    if include_archived or 'deleted_at' not in cols:
        cur.execute('SELECT id, username, nama FROM users ORDER BY nama')
    else:
        cur.execute("SELECT id, username, nama FROM users WHERE deleted_at IS NULL OR deleted_at = '' ORDER BY nama")
    users = cur.fetchall()
    conn.close()
    return [dict(u) for u in users]

def create_user(username: str, password: str = '123') -> dict:
    """Create user with dual-mode passwords (default both = 123)."""
    conn = get_db()
    cur = conn.cursor()
    try:
        pw = (password or '123').strip() or '123'
        h = hash_password(pw)
        uname = username.strip().lower()
        nama = username.strip().capitalize()
        cur.execute(
            'INSERT INTO users (username, password_hash, password_hash_pkl, password_hash_mentor, nama, role) VALUES (?, ?, ?, ?, ?, ?)',
            (uname, h, h, h, nama, 'pkl')
        )
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return {'id': user_id, 'username': uname, 'nama': nama, 'role': 'pkl'}
    except Exception as e:
        conn.close()
        raise e

# ===== Session Operations =====

def create_session(user_id: int, login_role: str):
    """Create session with login_role (mentor/pkl/owner) — role is per-session"""
    if login_role not in ('mentor', 'pkl', 'owner'):
        raise ValueError('invalid login_role')
    token = str(uuid.uuid4())
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO sessions (token, user_id, login_role) VALUES (?, ?, ?)',
        (token, user_id, login_role)
    )
    conn.commit()
    conn.close()
    return token

def get_session(token: str):
    """Get session with user data and login_role"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT u.id, u.username, u.nama, u.password_hash,
               s.login_role, s.token
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
    ''', (token,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)

def delete_session(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM sessions WHERE token = ?', (token,))
    conn.commit()
    conn.close()

# ===== Attendance Operations =====

def clock_in(user_id: int, photo_url: str = None) -> int:
    conn = get_db()
    cur = conn.cursor()
    from datetime import datetime, timedelta, timezone
    now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
    today = now_wib.strftime('%Y-%m-%d')
    now = now_wib.strftime('%H:%M:%S')
    # Never store empty string — template `{% if att.photo_url %}` treats "" as falsy
    # but empty string also confuses debugging vs true NULL
    if not photo_url:
        photo_url = None
    
    cur.execute('SELECT id, status FROM attendance WHERE user_id = ? AND date = ?', (user_id, today))
    existing = cur.fetchone()
    if existing:
        conn.close()
        return None  # Already clocked in (or has izin/alpha)
    
    cur.execute(
        'INSERT INTO attendance (user_id, clock_in, date, status, photo_url) VALUES (?, ?, ?, ?, ?)',
        (user_id, now, today, 'present', photo_url)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id

def clock_out(user_id: int, photo_url: str = None) -> int:
    conn = get_db()
    cur = conn.cursor()
    from datetime import datetime, timedelta, timezone
    now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
    today = now_wib.strftime('%Y-%m-%d')
    now = now_wib.strftime('%H:%M:%S')
    if not photo_url:
        photo_url = None
    
    cur.execute(
        'UPDATE attendance SET clock_out = ?, photo_url = COALESCE(?, photo_url) WHERE user_id = ? AND date = ? AND clock_out IS NULL',
        (now, photo_url, user_id, today)
    )
    conn.commit()
    rows = cur.rowcount
    conn.close()
    return rows

def set_attendance_status(user_id: int, status: str) -> dict:
    """Set status: 'izin' or 'alpha' for today. Blocks future clock_in for today.
    Returns: {success, message, score_change, new_score}
    """
    conn = get_db()
    cur = conn.cursor()
    from datetime import datetime, timedelta, timezone
    today = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%d')
    
    # Check if attendance record exists
    cur.execute('SELECT id, status FROM attendance WHERE user_id = ? AND date = ?', (user_id, today))
    existing = cur.fetchone()
    
    # Get current score for accurate response
    cur.execute('SELECT score FROM users WHERE id = ?', (user_id,))
    user = cur.fetchone()
    current_score = user['score'] if user and user['score'] is not None else 100
    
    result = {'success': False, 'message': '', 'score_change': 0, 'new_score': current_score}
    
    if status == 'izin':
        # Izin: create or update record
        if existing:
            cur.execute('UPDATE attendance SET status = ? WHERE id = ?', ('izin', existing['id']))
        else:
            cur.execute('INSERT INTO attendance (user_id, date, status) VALUES (?, ?, ?)', (user_id, today, 'izin'))
        conn.commit()
        result['success'] = True
        result['message'] = 'Status: Izin dicatat'
    elif status == 'alpha':
        # Alpha: -1 score
        if existing:
            cur.execute('UPDATE attendance SET status = ? WHERE id = ?', ('alpha', existing['id']))
        else:
            cur.execute('INSERT INTO attendance (user_id, date, status) VALUES (?, ?, ?)', (user_id, today, 'alpha'))
        # Decrement score (but not below 0)
        new_score = max(0, current_score - 1)
        cur.execute('UPDATE users SET score = ? WHERE id = ?', (new_score, user_id))
        conn.commit()
        result['success'] = True
        result['message'] = 'Status: Alpha dicatat (skor -1)'
        result['score_change'] = new_score - current_score
        result['new_score'] = new_score
    
    conn.close()
    return result

def get_user_score(user_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT score FROM users WHERE id = ?', (user_id,))
    user = cur.fetchone()
    conn.close()
    return user['score'] if user and user['score'] is not None else 100

def get_today_attendance(user_id: int):
    """Get today's attendance record (for lock state) — WIB date."""
    conn = get_db()
    cur = conn.cursor()
    from datetime import datetime, timedelta, timezone
    today = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%d')
    cur.execute('SELECT * FROM attendance WHERE user_id = ? AND date = ?', (user_id, today))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_attendance(user_id: int, limit: int = 30):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT * FROM attendance
        WHERE user_id = ?
        ORDER BY date DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_attendance(mentor_id: int = None, mentor_username: str = None):
    """Get attendance for mentor's 1-to-1 student (same username).
    Prefer mentor_username (1-to-1 pairing). mentor_id kept for back-compat.
    If both None, returns all attendance (admin)."""
    conn = get_db()
    cur = conn.cursor()
    if mentor_username:
        # 1-to-1: Mentor X only sees PKL with username == X
        cur.execute('''
            SELECT a.*, u.nama, u.username
            FROM attendance a
            JOIN users u ON a.user_id = u.id
            WHERE u.username = ?
            ORDER BY a.date DESC, a.id DESC
        ''', (mentor_username,))
    elif mentor_id is not None:
        # Back-compat: resolve username from mentor_id then 1-to-1 filter
        cur.execute('SELECT username FROM users WHERE id = ?', (mentor_id,))
        row = cur.fetchone()
        uname = row['username'] if row else None
        if uname:
            cur.execute('''
                SELECT a.*, u.nama, u.username
                FROM attendance a
                JOIN users u ON a.user_id = u.id
                WHERE u.username = ?
                ORDER BY a.date DESC, a.id DESC
            ''', (uname,))
        else:
            cur.execute('''
                SELECT DISTINCT a.*, u.nama, u.username
                FROM attendance a
                JOIN users u ON a.user_id = u.id
                JOIN tasks t ON t.assigned_to = a.user_id
                WHERE t.mentor_id = ?
                ORDER BY a.date DESC
            ''', (mentor_id,))
    else:
        cur.execute('''
            SELECT a.*, u.nama, u.username
            FROM attendance a
            JOIN users u ON a.user_id = u.id
            ORDER BY a.date DESC
        ''')
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _normalize_time(val: str | None) -> str | None:
    """Accept HH:MM or HH:MM:SS; return HH:MM:SS or None."""
    if val is None:
        return None
    val = str(val).strip()
    if not val or val in ('-', 'null', 'None'):
        return None
    # HH:MM → HH:MM:00
    if len(val) == 5 and val[2] == ':':
        val = val + ':00'
    parts = val.split(':')
    if len(parts) != 3:
        return None
    try:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
            return None
        return f'{h:02d}:{m:02d}:{s:02d}'
    except ValueError:
        return None


def mentor_correct_attendance(
    mentor_username: str,
    student_username: str,
    date: str,
    clock_in: str = None,
    clock_out: str = None,
    status: str = 'present',
    attendance_id: int = None,
    note: str = None,
) -> dict:
    """Mentor upsert/correct attendance for 1-to-1 paired student.
    Returns {success, message, attendance_id, data} or {success: False, error}."""
    mentor_username = (mentor_username or '').strip().lower()
    student_username = (student_username or '').strip().lower()
    if not mentor_username or not student_username:
        return {'success': False, 'error': 'Atasan/staff wajib diisi'}
    # 1-to-1 pairing enforcement
    if mentor_username != student_username:
        return {
            'success': False,
            'error': f'Mentor @{mentor_username} hanya boleh koreksi absensi staff @{mentor_username} (1-to-1)',
        }

    # Validate date YYYY-MM-DD
    date = (date or '').strip()
    try:
        from datetime import datetime as _dt
        _dt.strptime(date, '%Y-%m-%d')
    except Exception:
        return {'success': False, 'error': 'Format tanggal harus YYYY-MM-DD'}

    clock_in = _normalize_time(clock_in)
    clock_out = _normalize_time(clock_out)
    status = (status or 'present').strip().lower()
    if status not in ('present', 'izin', 'alpha'):
        return {'success': False, 'error': 'Status harus present/izin/alpha'}

    # Izin/alpha: jam boleh kosong. Present: clock_in wajib (bisa koreksi out only if existing)
    if status == 'present' and not clock_in and not attendance_id:
        return {'success': False, 'error': 'Clock In wajib untuk status Hadir'}

    # clock_out must be after clock_in when both set
    if clock_in and clock_out and clock_out < clock_in:
        return {'success': False, 'error': 'Clock Out tidak boleh lebih awal dari Clock In'}

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, username, nama FROM users WHERE username = ?', (student_username,))
    student = cur.fetchone()
    if not student:
        conn.close()
        return {'success': False, 'error': f'Staff @{student_username} tidak ditemukan'}
    student_id = student['id']

    existing = None
    if attendance_id:
        cur.execute(
            'SELECT * FROM attendance WHERE id = ? AND user_id = ?',
            (attendance_id, student_id),
        )
        existing = cur.fetchone()
        if not existing:
            conn.close()
            return {'success': False, 'error': 'Record absensi tidak ditemukan / bukan milik staff ini'}
    else:
        cur.execute(
            'SELECT * FROM attendance WHERE user_id = ? AND date = ?',
            (student_id, date),
        )
        existing = cur.fetchone()

    # Preserve photo_url on edit; never wipe unless new insert
    if existing:
        # If clock_in not provided on edit of present, keep old
        if status == 'present' and not clock_in:
            clock_in = existing['clock_in']
        if status in ('izin', 'alpha'):
            # optional: clear times for non-present? keep times if provided, else keep existing
            if clock_in is None:
                clock_in = existing['clock_in']
            if clock_out is None:
                clock_out = existing['clock_out']
        cur.execute(
            '''UPDATE attendance
               SET date = ?, clock_in = ?, clock_out = ?, status = ?
               WHERE id = ?''',
            (date, clock_in, clock_out, status, existing['id']),
        )
        att_id = existing['id']
        action = 'diperbarui'
    else:
        if status == 'present' and not clock_in:
            conn.close()
            return {'success': False, 'error': 'Clock In wajib untuk status Hadir'}
        cur.execute(
            '''INSERT INTO attendance (user_id, date, clock_in, clock_out, status, photo_url)
               VALUES (?, ?, ?, ?, ?, NULL)''',
            (student_id, date, clock_in, clock_out, status),
        )
        att_id = cur.lastrowid
        action = 'ditambahkan'

    conn.commit()
    cur.execute(
        '''SELECT a.*, u.nama, u.username FROM attendance a
           JOIN users u ON u.id = a.user_id WHERE a.id = ?''',
        (att_id,),
    )
    data = dict(cur.fetchone())
    conn.close()
    return {
        'success': True,
        'message': f'Absensi {date} @{student_username} {action}',
        'attendance_id': att_id,
        'data': data,
        'note': note,
    }

def get_old_attendance_photos(days: int = 7):
    """Get attendance records with photos older than X days"""
    conn = get_db()
    cur = conn.cursor()
    # SQLite date() function for comparison
    cur.execute('''
        SELECT id, photo_url 
        FROM attendance 
        WHERE photo_url IS NOT NULL 
        AND date < date('now', ?)
    ''', (f'-{days} days',))
    rows = cur.fetchall()
    conn.close()
    return rows

# ===== Task Operations =====

def create_task(mentor_id: int, assigned_to: int, title: str, description: str, deadline: str, file_url: str = None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO tasks (mentor_id, assigned_to, title, description, deadline, file_url)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (mentor_id, assigned_to, title, description, deadline, file_url))
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id

def edit_task(task_id: int, mentor_username: str, title: str, description: str, deadline: str, file_url: str = None) -> dict:
    """Edit a task — only mentor whose username matches assigned_to can edit (1-to-1)"""
    conn = get_db()
    cur = conn.cursor()
    if file_url:
        cur.execute("""
            UPDATE tasks SET title = ?, description = ?, deadline = ?, file_url = ? WHERE id = ? AND assigned_to IN (
                SELECT id FROM users WHERE username = ?
            )
        """, (title, description, deadline, file_url, task_id, mentor_username))
    else:
        cur.execute("""
            UPDATE tasks SET title = ?, description = ?, deadline = ? WHERE id = ? AND assigned_to IN (
                SELECT id FROM users WHERE username = ?
            )
        """, (title, description, deadline, task_id, mentor_username))
    updated = cur.rowcount
    conn.commit()
    conn.close()
    return {'updated': updated > 0, 'task_id': task_id}

def delete_task(task_id: int, mentor_username: str) -> dict:
    """Delete a task + its reports (cascade).
    Only if assigned username matches mentor's own username (1-to-1).
    Returns report file_urls so caller can purge R2.
    """
    conn = get_db()
    cur = conn.cursor()
    # Ownership check first
    cur.execute('''
        SELECT id FROM tasks WHERE id = ? AND assigned_to IN (
            SELECT id FROM users WHERE username = ?
        )
    ''', (task_id, mentor_username))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {'deleted': False, 'task_id': task_id, 'report_file_urls': []}

    # Collect report file URLs before cascade delete (for R2 cleanup)
    cur.execute(
        'SELECT file_url FROM reports WHERE task_id = ? AND file_url IS NOT NULL AND file_url != ""',
        (task_id,),
    )
    report_file_urls = [r['file_url'] for r in cur.fetchall() if r['file_url']]

    # Cascade: reports first, then task
    cur.execute('DELETE FROM reports WHERE task_id = ?', (task_id,))
    reports_deleted = cur.rowcount
    cur.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {
        'deleted': deleted > 0,
        'task_id': task_id,
        'reports_deleted': reports_deleted,
        'report_file_urls': report_file_urls,
    }


def cleanup_orphan_reports() -> dict:
    """Delete reports whose task no longer exists. Returns count + file_urls for R2."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT r.id, r.file_url FROM reports r
        LEFT JOIN tasks t ON t.id = r.task_id
        WHERE t.id IS NULL
    ''')
    orphans = cur.fetchall()
    file_urls = [o['file_url'] for o in orphans if o['file_url']]
    ids = [o['id'] for o in orphans]
    if ids:
        cur.execute(f"DELETE FROM reports WHERE id IN ({','.join('?' * len(ids))})", ids)
        conn.commit()
    deleted = len(ids)
    conn.close()
    return {'deleted': deleted, 'file_urls': file_urls}


def get_task_detail(task_id: int, user_id: int):
    """Get detailed info for a specific task, including report and user details"""
    conn = get_db()
    cur = conn.cursor()
    
    # Fetch task and report info
    cur.execute('''
        SELECT t.*, 
               u_mentor.nama as mentor_nama, u_mentor.username as mentor_username,
               u_student.nama as student_nama, u_student.username as student_username,
               r.id as report_id, r.status as report_status, r.content as report_content, r.feedback, r.graded, r.file_url as report_file_url, r.submitted_at
        FROM tasks t
        JOIN users u_mentor ON t.mentor_id = u_mentor.id
        JOIN users u_student ON t.assigned_to = u_student.id
        LEFT JOIN reports r ON r.task_id = t.id AND r.user_id = t.assigned_to
        WHERE t.id = ?
    ''', (task_id,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def get_tasks(user_id: int):
    """Get tasks for a user (as assigned PKL)"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT t.*, u.nama as mentor_nama, u.username as mentor_username,
               r.id as report_id, r.status as report_status, r.feedback, r.graded, r.file_url as report_file_url
        FROM tasks t
        JOIN users u ON t.mentor_id = u.id
        LEFT JOIN reports r ON r.task_id = t.id AND r.user_id = ?
        WHERE t.assigned_to = ?
        ORDER BY t.created_at DESC
    ''', (user_id, user_id))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_tasks(mentor_username: str):
    """Get all tasks assigned to a specific username (1-to-1 pairing: mentor sees their own username tasks)"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT t.*, u.nama as assigned_nama, u.username as assigned_username,
               r.id as report_id, r.status as report_status, r.feedback as report_feedback,
               r.graded, r.submitted_at, t.file_url,
               r.file_url as report_file_url
        FROM tasks t
        JOIN users u ON t.assigned_to = u.id
        LEFT JOIN reports r ON r.task_id = t.id AND r.user_id = t.assigned_to
        WHERE u.username = ?
        ORDER BY t.created_at DESC
    ''', (mentor_username,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_tasks_admin():
    """Get ALL tasks across ALL students — for Mentor overview dashboard"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT t.id, t.title, t.description, t.deadline, t.created_at,
               t.assigned_to, t.mentor_id, t.file_url,
               u.username as assigned_username, u.nama as assigned_nama,
               r.id as report_id, r.file_url as report_file_url, r.feedback as report_feedback,
               r.status as report_status, r.submitted_at as report_submitted_at,
               r.graded
        FROM tasks t
        JOIN users u ON t.assigned_to = u.id
        LEFT JOIN reports r ON r.task_id = t.id AND r.user_id = t.assigned_to
        ORDER BY t.created_at DESC
    ''')
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_reports_admin():
    """Get ALL reports across ALL students — for Mentor overview"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT r.*, t.title as task_title, u.username as student_username, u.nama as student_nama
        FROM reports r
        JOIN tasks t ON r.task_id = t.id
        JOIN users u ON r.user_id = u.id
        ORDER BY r.submitted_at DESC
    ''')
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ===== Report Operations =====

def submit_report(task_id: int, user_id: int, file_path: str, file_url: str = None, content: str = '', gdrive_link: str = None):
    conn = get_db()
    cur = conn.cursor()
    # WIB Time for submission
    from datetime import datetime, timedelta, timezone
    submitted_at = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
    # Check if report already exists
    cur.execute('SELECT id FROM reports WHERE task_id = ? AND user_id = ?', (task_id, user_id))
    existing = cur.fetchone()
    
    if existing:
        # Update existing report — reset to Menunggu Review (PKL can resubmit after reject)
        cur.execute('''
            UPDATE reports SET
                file_path = COALESCE(?, file_path),
                file_url = COALESCE(?, file_url),
                content = ?,
                submitted_at = ?,
                graded = 0,
                feedback = NULL,
                gdrive_link = COALESCE(?, gdrive_link),
                status = 'Menunggu Review'
            WHERE task_id = ? AND user_id = ?
        ''', (file_path, file_url, content, submitted_at, gdrive_link, task_id, user_id))
        report_id = existing['id']
    else:
        cur.execute('''
            INSERT INTO reports (task_id, user_id, file_path, file_url, content, gdrive_link, status, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Menunggu Review', ?)
        ''', (task_id, user_id, file_path, file_url, content, gdrive_link, submitted_at))
        report_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    return report_id

def review_report(report_id: int, action: str, feedback: str = '') -> dict:
    """action: 'accept' or 'reject'. Updates status and graded.
    Reject requires non-empty feedback (min 3 chars).
    """
    conn = get_db()
    cur = conn.cursor()
    act = (action or '').strip().lower()
    fb = (feedback or '').strip()
    
    if act == 'accept':
        new_status = 'Diterima'
        new_graded = 1
    elif act in ('reject', 'tolak', 'ditolak'):
        if len(fb) < 3:
            conn.close()
            return {'success': False, 'error': 'Alasan penolakan wajib diisi (min 3 karakter)'}
        new_status = 'Ditolak'
        new_graded = -1
    else:
        conn.close()
        return {'success': False, 'error': 'Invalid action'}
    
    cur.execute('''
        UPDATE reports SET
            status = ?,
            graded = ?,
            feedback = ?
        WHERE id = ?
    ''', (new_status, new_graded, fb if act != 'accept' else (fb or feedback or ''), report_id))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    
    if affected == 0:
        return {'success': False, 'error': 'Report not found'}
    return {'success': True, 'status': new_status, 'graded': new_graded}

def get_report_by_task(task_id: int, user_id: int):
    """Get report for a specific task and user"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM reports WHERE task_id = ? AND user_id = ?', (task_id, user_id))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def update_feedback(report_id: int, feedback: str, graded: int):
    conn = get_db()
    cur = conn.cursor()
    status_map = {1: 'Diterima', -1: 'Ditolak', 0: 'Menunggu Review'}
    status = status_map.get(graded, 'pending')
    cur.execute(
        'UPDATE reports SET feedback = ?, graded = ?, status = ? WHERE id = ?',
        (feedback, graded, status, report_id)
    )
    conn.commit()
    conn.close()

def get_reports(user_id: int):
    """Get reports submitted by user"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT r.*, t.title as task_title
        FROM reports r
        JOIN tasks t ON r.task_id = t.id
        WHERE r.user_id = ?
        ORDER BY r.submitted_at DESC
    ''', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_report(report_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM reports WHERE id = ?', (report_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def cancel_report(report_id: int, user_id: int) -> dict:
    """PKL: cancel their pending report by report_id. Only delete if graded=0 (still pending)"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM reports WHERE id = ? AND user_id = ? AND graded = 0', (report_id, user_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return {'success': deleted > 0, 'deleted': deleted}

def cancel_report_by_task(task_id: int, user_id: int) -> dict:
    """PKL: cancel their pending report by task_id. Only delete if graded=0 (still pending)"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM reports WHERE task_id = ? AND user_id = ? AND graded = 0', (task_id, user_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return {'success': deleted > 0, 'deleted': deleted}

# ===== Stats =====

def get_stats(user_id: int):
    """Get attendance + task stats for a user.

    submitted_reports = uploads for tasks that STILL exist (all statuses).
    Orphan reports (task already deleted) are NOT counted.
    """
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN clock_out IS NOT NULL THEN 1 ELSE 0 END) as complete
        FROM attendance WHERE user_id = ?
    ''', (user_id,))
    att = cur.fetchone()
    
    cur.execute('SELECT COUNT(*) as total FROM tasks WHERE assigned_to = ?', (user_id,))
    tasks_count = cur.fetchone()
    
    cur.execute('''
        SELECT COUNT(*) as done FROM tasks WHERE assigned_to = ? AND status = 'completed'
    ''', (user_id,))
    done_count = cur.fetchone()
    
    # Only count reports whose parent task still exists (any upload status)
    cur.execute('''
        SELECT COUNT(*) as total
        FROM reports r
        INNER JOIN tasks t ON t.id = r.task_id
        WHERE r.user_id = ?
    ''', (user_id,))
    submitted = cur.fetchone()
    
    conn.close()
    return {
        'total_attendance': att['total'] or 0,
        'completed_attendance': att['complete'] or 0,
        'total_tasks': tasks_count['total'] or 0,
        'completed_tasks': done_count['done'] or 0,
        'submitted_reports': submitted['total'] or 0,
    }

def get_all_stats():
    """Get aggregate stats for all users"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as total FROM users')
    total_users = cur.fetchone()
    cur.execute('SELECT COUNT(*) as total FROM attendance WHERE date = ?', (datetime.now().strftime('%Y-%m-%d'),))
    today_att = cur.fetchone()
    cur.execute('SELECT COUNT(*) as total FROM tasks')
    total_tasks = cur.fetchone()
    conn.close()
    return {
        'total_users': total_users['total'] or 0,
        'today_attendance': today_att['total'] or 0,
        'total_tasks': total_tasks['total'] or 0,
    }


# ===== Master password / Admin Room =====

DEFAULT_MASTER_PASSWORD = 'parhan' + 'ganteng'


def ensure_master_password_seed():
    """Seed default master password once if missing."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS app_settings ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    cur.execute("SELECT value FROM app_settings WHERE key = 'master_password'")
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES ('master_password', ?, CURRENT_TIMESTAMP)",
            (DEFAULT_MASTER_PASSWORD,)
        )
        conn.commit()
    conn.close()



def ensure_owner_user() -> dict:
    """System account for Manager sessions (login via master password only).
    Username stays 'owner' (internal); display name is Manager.
    """
    existing = get_user_by_username('owner')
    if existing:
        if (existing.get('nama') or '').strip() in ('Owner', 'owner', ''):
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET nama = ? WHERE username = 'owner'", ('Manager',))
            conn.commit()
            conn.close()
            existing = get_user_by_username('owner')
        return existing
    u = create_user('owner', '123')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET nama = ? WHERE username = 'owner'", ('Manager',))
    conn.commit()
    conn.close()
    return get_user_by_username('owner') or u

def get_master_password() -> str:
    ensure_master_password_seed()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key = 'master_password'")
    row = cur.fetchone()
    conn.close()
    if not row or not row['value']:
        return DEFAULT_MASTER_PASSWORD
    return row['value']


def verify_master_password(password: str) -> bool:
    if password is None:
        return False
    return str(password) == get_master_password()


def set_master_password(new_password: str) -> bool:
    new_password = (new_password or '').strip()
    if len(new_password) < 6:
        return False
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES ('master_password', ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
        (new_password,)
    )
    conn.commit()
    conn.close()
    return True




DEFAULT_APP_NAME = 'Staff Management'
DEFAULT_LOGO_ICON = 'fa-briefcase'  # Font Awesome class (no "fas")
DEFAULT_LOGO_URL = ''  # optional image URL; empty = use icon default


def get_setting(key: str, default: str = '') -> str:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS app_settings ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL, "
        "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    cur.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if not row or row['value'] is None:
        return default
    return str(row['value'])


def set_setting(key: str, value: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS app_settings ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL, "
        "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    cur.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
        (key, value if value is not None else ''),
    )
    conn.commit()
    conn.close()
    return True


def get_brand_settings() -> dict:
    """Editable brand: app_name + logo (icon class or image URL). Defaults = current product brand."""
    app_name = (get_setting('app_name', DEFAULT_APP_NAME) or DEFAULT_APP_NAME).strip()
    logo_icon = (get_setting('logo_icon', DEFAULT_LOGO_ICON) or DEFAULT_LOGO_ICON).strip()
    logo_url = (get_setting('logo_url', DEFAULT_LOGO_URL) or '').strip()
    if logo_icon.startswith('fas '):
        logo_icon = logo_icon.replace('fas ', '', 1).strip()
    if not logo_icon:
        logo_icon = DEFAULT_LOGO_ICON
    return {
        'app_name': app_name,
        'logo_icon': logo_icon,
        'logo_url': logo_url,
    }


def set_brand_settings(app_name: str = None, logo_icon: str = None, logo_url: str = None) -> dict:
    if app_name is not None:
        name = (app_name or '').strip() or DEFAULT_APP_NAME
        if len(name) > 64:
            name = name[:64]
        set_setting('app_name', name)
    if logo_icon is not None:
        icon = (logo_icon or '').strip() or DEFAULT_LOGO_ICON
        if icon.startswith('fas '):
            icon = icon.replace('fas ', '', 1).strip()
        set_setting('logo_icon', icon or DEFAULT_LOGO_ICON)
    if logo_url is not None:
        url = (logo_url or '').strip()
        # allow empty (reset to icon), http(s), or /uploads/...
        if url and not (url.startswith('http://') or url.startswith('https://') or url.startswith('/')):
            return {'success': False, 'error': 'Logo URL harus http(s) atau path /uploads/...'}
        set_setting('logo_url', url)
    return {'success': True, 'brand': get_brand_settings()}




def export_attendance_rows(mode: str = 'daily', date: str = None, username: str = None,
                           date_from: str = None, date_to: str = None) -> dict:
    """Export attendance for Admin Room.
    mode=daily: all staff for one date
    mode=staff: one staff date_from..date_to (max 31 days inclusive)
    """
    from datetime import datetime as _dt, timedelta as _td
    mode = (mode or 'daily').lower().strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(attendance)')
    cols = {row[1] for row in cur.fetchall()}
    photo_sel = 'a.photo_url' if 'photo_url' in cols else "'' as photo_url"
    rows = []
    meta = {'mode': mode}

    if mode == 'daily':
        d = (date or '').strip()
        if not d:
            d = (_dt.utcnow() + _td(hours=7)).strftime('%Y-%m-%d')
        meta['date'] = d
        sql = (
            "SELECT a.id, u.username, u.nama, a.date, a.clock_in, a.clock_out, a.status, "
            + photo_sel +
            " FROM attendance a JOIN users u ON u.id = a.user_id "
            "WHERE a.date = ? AND u.username != 'owner' "
            "ORDER BY u.username COLLATE NOCASE"
        )
        cur.execute(sql, (d,))
        rows = [dict(r) for r in cur.fetchall()]
    elif mode == 'staff':
        uname = (username or '').strip().lower()
        if not uname or uname == 'owner':
            conn.close()
            return {'success': False, 'error': 'username staff wajib'}
        u = get_user_by_username(uname)
        if not u:
            conn.close()
            return {'success': False, 'error': 'Staff @%s tidak ditemukan' % uname}
        df = (date_from or '').strip()
        dt = (date_to or '').strip()
        if not df or not dt:
            conn.close()
            return {'success': False, 'error': 'date_from dan date_to wajib (YYYY-MM-DD)'}
        try:
            d0 = _dt.strptime(df, '%Y-%m-%d').date()
            d1 = _dt.strptime(dt, '%Y-%m-%d').date()
        except ValueError:
            conn.close()
            return {'success': False, 'error': 'Format tanggal harus YYYY-MM-DD'}
        if d1 < d0:
            conn.close()
            return {'success': False, 'error': 'date_to harus >= date_from'}
        if (d1 - d0).days > 30:
            conn.close()
            return {'success': False, 'error': 'Maksimal rentang 31 hari'}
        meta.update({'username': uname, 'date_from': df, 'date_to': dt, 'nama': u.get('nama')})
        sql = (
            "SELECT a.id, u.username, u.nama, a.date, a.clock_in, a.clock_out, a.status, "
            + photo_sel +
            " FROM attendance a JOIN users u ON u.id = a.user_id "
            "WHERE u.id = ? AND a.date >= ? AND a.date <= ? "
            "ORDER BY a.date ASC"
        )
        cur.execute(sql, (u['id'], df, dt))
        rows = [dict(r) for r in cur.fetchall()]
    else:
        conn.close()
        return {'success': False, 'error': 'mode harus daily|staff'}

    conn.close()
    for r in rows:
        r['clock_in'] = r.get('clock_in') or ''
        r['clock_out'] = r.get('clock_out') or ''
        r['status'] = r.get('status') or 'present'
        r['photo_url'] = r.get('photo_url') or ''
    return {'success': True, 'meta': meta, 'rows': rows, 'count': len(rows)}


def attendance_rows_to_csv(rows: list) -> str:
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['username', 'nama', 'date', 'clock_in', 'clock_out', 'status', 'photo_url'])
    for r in rows:
        w.writerow([
            r.get('username', ''), r.get('nama', ''), r.get('date', ''),
            r.get('clock_in', ''), r.get('clock_out', ''), r.get('status', ''),
            r.get('photo_url', ''),
        ])
    return buf.getvalue()


def list_users_admin(include_archived: bool = True):
    """All users for Admin Room (no password hashes exposed). Includes archived by default."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cur.fetchall()}
    if 'deleted_at' in cols:
        cur.execute(
            'SELECT id, username, nama, role, score, created_at, deleted_at FROM users ORDER BY username COLLATE NOCASE'
        )
    else:
        cur.execute(
            'SELECT id, username, nama, role, score, created_at FROM users ORDER BY username COLLATE NOCASE'
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        r['archived'] = bool(r.get('deleted_at'))
        r['display_nama'] = r.get('nama') or r.get('username')
        if r.get('username') == 'owner':
            r['display_nama'] = 'Manager'
    return rows


def reset_user_password(username: str, mode: str = 'both', new_password: str = '123') -> dict:
    """Reset PKL and/or Mentor password to new_password (default 123)."""
    mode = (mode or 'both').lower().strip()
    if mode not in ('pkl', 'mentor', 'both'):
        return {'success': False, 'error': 'mode must be pkl|mentor|both'}
    user = get_user_by_username(username)
    if not user:
        return {'success': False, 'error': 'User tidak ditemukan'}
    h = hash_password(new_password or '123')
    conn = get_db()
    cur = conn.cursor()
    if mode in ('pkl', 'both'):
        cur.execute('UPDATE users SET password_hash_pkl = ?, password_hash = ? WHERE id = ?', (h, h, user['id']))
    if mode in ('mentor', 'both'):
        cur.execute('UPDATE users SET password_hash_mentor = ? WHERE id = ?', (h, user['id']))
    cur.execute('DELETE FROM sessions WHERE user_id = ?', (user['id'],))
    conn.commit()
    conn.close()
    return {'success': True, 'username': user['username'], 'mode': mode, 'password': new_password or '123'}


def _active_staff_count(conn=None) -> int:
    """Count non-owner staff that are not soft-deleted."""
    own = conn is not None
    if not own:
        conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cur.fetchall()}
    if 'deleted_at' in cols:
        cur.execute(
            "SELECT COUNT(*) AS c FROM users WHERE username != 'owner' "
            "AND (deleted_at IS NULL OR deleted_at = '')"
        )
    else:
        cur.execute("SELECT COUNT(*) AS c FROM users WHERE username != 'owner'")
    c = int(cur.fetchone()['c'] or 0)
    if not own:
        conn.close()
    return c


def soft_delete_user(username: str) -> dict:
    """Archive staff (soft-delete). Keeps attendance/tasks history. Blocks login.
    Safety: cannot archive system owner; must leave at least 1 active staff.
    """
    user = get_user_by_username(username)
    if not user:
        return {'success': False, 'error': 'User tidak ditemukan'}
    if (username or '').strip().lower() == 'owner':
        return {'success': False, 'error': 'Akun sistem Manager tidak bisa dihapus/diarsip'}
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cur.fetchall()}
    if 'deleted_at' not in cols:
        cur.execute('ALTER TABLE users ADD COLUMN deleted_at TEXT')
        cols.add('deleted_at')
    # already archived?
    cur.execute('SELECT deleted_at FROM users WHERE id = ?', (user['id'],))
    row = cur.fetchone()
    if row and row['deleted_at']:
        conn.close()
        return {'success': False, 'error': 'User sudah diarsip'}
    if _active_staff_count(conn) <= 1:
        conn.close()
        return {'success': False, 'error': 'Wajib sisakan minimal 1 staff aktif. Tidak bisa arsip user terakhir.'}
    from datetime import datetime as _dt
    now = _dt.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute('UPDATE users SET deleted_at = ? WHERE id = ?', (now, user['id']))
    # kill sessions so they can't stay logged in
    cur.execute('DELETE FROM sessions WHERE user_id = ?', (user['id'],))
    conn.commit()
    conn.close()
    return {
        'success': True,
        'mode': 'soft',
        'username': user['username'],
        'user_id': user['id'],
        'deleted_at': now,
        'message': 'User diarsip. Data absensi/tugas tetap tersimpan. Bisa restore dari Admin Room.',
    }


def restore_user(username: str) -> dict:
    """Restore soft-deleted staff."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cur.fetchall()}
    if 'deleted_at' not in cols:
        conn.close()
        return {'success': False, 'error': 'Kolom deleted_at belum ada'}
    uname = (username or '').strip().lower()
    cur.execute('SELECT id, username, deleted_at FROM users WHERE username = ?', (uname,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {'success': False, 'error': 'User tidak ditemukan'}
    if not row['deleted_at']:
        conn.close()
        return {'success': False, 'error': 'User tidak dalam arsip'}
    cur.execute('UPDATE users SET deleted_at = NULL WHERE id = ?', (row['id'],))
    conn.commit()
    conn.close()
    return {'success': True, 'username': uname, 'message': 'User di-restore'}


def delete_user_cascade(username: str, hard: bool = False) -> dict:
    """Default: soft-delete (archive). hard=True permanently deletes + cascade data.
    Safety: cannot delete system owner; must leave at least 1 active staff.
    """
    if not hard:
        return soft_delete_user(username)

    user = get_user_by_username(username)
    if not user:
        return {'success': False, 'error': 'User tidak ditemukan'}
    if (username or '').strip().lower() == 'owner':
        return {'success': False, 'error': 'Akun sistem Manager tidak bisa dihapus'}
    conn0 = get_db()
    if _active_staff_count(conn0) <= 1:
        # allow hard-delete of already-archived if other active staff remain
        cur0 = conn0.cursor()
        cur0.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur0.fetchall()}
        if 'deleted_at' in cols:
            cur0.execute('SELECT deleted_at FROM users WHERE id = ?', (user['id'],))
            dr = cur0.fetchone()
            if not (dr and dr['deleted_at']) and _active_staff_count(conn0) <= 1:
                conn0.close()
                return {'success': False, 'error': 'Wajib sisakan minimal 1 staff aktif.'}
        else:
            conn0.close()
            return {'success': False, 'error': 'Wajib sisakan minimal 1 staff. Tidak bisa hapus user terakhir.'}
    conn0.close()
    uid = user['id']
    uid = user['id']
    conn = get_db()
    cur = conn.cursor()
    file_urls = []
    cur.execute('SELECT id FROM tasks WHERE mentor_id = ? OR assigned_to = ?', (uid, uid))
    task_rows = cur.fetchall()
    task_ids = [r['id'] for r in task_rows]
    if task_ids:
        qmarks = ','.join('?' * len(task_ids))
        cur.execute(f'SELECT file_url FROM reports WHERE task_id IN ({qmarks}) OR user_id = ?', (*task_ids, uid))
    else:
        cur.execute('SELECT file_url FROM reports WHERE user_id = ?', (uid,))
    for r in cur.fetchall():
        if r['file_url']:
            file_urls.append(r['file_url'])
    cur.execute("PRAGMA table_info(attendance)")
    att_cols = {row[1] for row in cur.fetchall()}
    if 'photo_url' in att_cols:
        cur.execute('SELECT photo_url FROM attendance WHERE user_id = ?', (uid,))
        for r in cur.fetchall():
            if r['photo_url']:
                file_urls.append(r['photo_url'])
    if task_ids:
        qmarks = ','.join('?' * len(task_ids))
        cur.execute(f'DELETE FROM reports WHERE task_id IN ({qmarks}) OR user_id = ?', (*task_ids, uid))
    else:
        cur.execute('DELETE FROM reports WHERE user_id = ?', (uid,))
    cur.execute('DELETE FROM tasks WHERE mentor_id = ? OR assigned_to = ?', (uid, uid))
    cur.execute('DELETE FROM attendance WHERE user_id = ?', (uid,))
    cur.execute('DELETE FROM sessions WHERE user_id = ?', (uid,))
    cur.execute('DELETE FROM users WHERE id = ?', (uid,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    uniq = []
    seen = set()
    for u in file_urls:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    return {
        'success': deleted > 0,
        'mode': 'hard',
        'username': user['username'],
        'user_id': uid,
        'tasks_removed': len(task_ids),
        'file_urls': uniq,
    }


# ===== Seed Data =====

def seed_data():
    """Seed initial data — NO role column, every user is dual-role"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as c FROM users')
    if cur.fetchone()['c'] > 0:
        conn.close()
        return  # Already seeded
    
    # Create users — NO role field
    users = [
        ('mentor', 'Budi Santoso, S.T.'),
        ('andi', 'Andi Pratama'),
        ('budi', 'Budi Wijaya'),
        ('citra', 'Citra Dewi'),
        ('staff1', 'Staff Satu'),
    ]
    
    user_ids = {}
    for username, nama in users:
        cur.execute(
            'INSERT INTO users (username, password_hash, nama) VALUES (?, ?, ?)',
            (username, hash_password('123'), nama)
        )
        user_ids[username] = cur.lastrowid
    
    # Sample attendance for andi
    for i in range(7):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        cur.execute(
            'INSERT INTO attendance (user_id, date, clock_in, clock_out) VALUES (?, ?, ?, ?)',
            (user_ids['andi'], date, '08:00:00', '16:00:00')
        )
    
    # Sample task
    cur.execute('''
        INSERT INTO tasks (mentor_id, assigned_to, title, description, deadline)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_ids['mentor'], user_ids['andi'], 'Tugas HTML Dasar', 
          'Buat halaman web sederhana dengan HTML dan CSS', 
          (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')))
    
    conn.commit()
    conn.close()
    print("✅ Seeded: mentor, andi, budi, citra, staff1 — dual-role staff (password: 123)")

if __name__ == '__main__':
    init_db()
    seed_data()
    print("✅ Database initialized at", DB_PATH)