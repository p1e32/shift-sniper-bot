import sqlite3
import os

from cryptography.fernet import Fernet, InvalidToken


ENCRYPTED_PASSWORD_PREFIX = "fernet:"


def _get_password_cipher():
    key = os.getenv("PASSWORD_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "PASSWORD_ENCRYPTION_KEY is not configured. "
            "Generate one with `Fernet.generate_key()` and add it to .env."
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError("PASSWORD_ENCRYPTION_KEY is invalid.") from exc


def _encrypt_password(password):
    return ENCRYPTED_PASSWORD_PREFIX + _get_password_cipher().encrypt(
        password.encode()
    ).decode()


def _decrypt_password(stored_password):
    if not stored_password.startswith(ENCRYPTED_PASSWORD_PREFIX):
        return stored_password, False

    token = stored_password[len(ENCRYPTED_PASSWORD_PREFIX):].encode()
    try:
        password = _get_password_cipher().decrypt(token).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("Unable to decrypt a stored portal password.") from exc
    return password, True

def init_db():
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            portal_login TEXT,
            portal_password TEXT,
            stop_timeout INTEGER DEFAULT 8
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shift_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            target_date TEXT,
            target_time_type TEXT,
            target_shift_type TEXT,
            force_booking INTEGER DEFAULT 0, -- NEW COLUMN (0 = no, 1 = yes)
            status TEXT DEFAULT 'pending',
            FOREIGN KEY(telegram_id) REFERENCES users(telegram_id)
        )
    ''')
    conn.commit()
    conn.close()

def add_user(telegram_id, login, password):
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    encrypted_password = _encrypt_password(password)
    cursor.execute('INSERT OR REPLACE INTO users (telegram_id, portal_login, portal_password, stop_timeout) VALUES (?, ?, ?, 8)', (telegram_id, login, encrypted_password))
    conn.commit()
    conn.close()


def get_users_with_requests():
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT u.telegram_id, u.portal_login, u.portal_password, u.stop_timeout
        FROM users u
        JOIN shift_requests r ON u.telegram_id = r.telegram_id
        WHERE r.status = 'pending'
    ''')
    stored_users = cursor.fetchall()
    users = []

    for telegram_id, login, stored_password, stop_timeout in stored_users:
        password, is_encrypted = _decrypt_password(stored_password)
        users.append((telegram_id, login, password, stop_timeout))
        if not is_encrypted:
            cursor.execute(
                'UPDATE users SET portal_password = ? WHERE telegram_id = ?',
                (_encrypt_password(password), telegram_id),
            )

    conn.commit()
    conn.close()
    return users

def user_exists(telegram_id):
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM users WHERE telegram_id = ?', (telegram_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def add_shift_request(telegram_id, date, time_type, shift_type, force_booking):
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO shift_requests (telegram_id, target_date, target_time_type, target_shift_type, force_booking) VALUES (?, ?, ?, ?, ?)', (telegram_id, date, time_type, shift_type, force_booking))
    conn.commit()
    conn.close()

def get_active_requests(telegram_id):
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, target_date, target_time_type, target_shift_type, force_booking FROM shift_requests WHERE telegram_id = ? AND status = 'pending'", (telegram_id,))
    requests = cursor.fetchall()
    conn.close()
    return requests

def delete_request(request_id, telegram_id):
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM shift_requests WHERE id = ? AND telegram_id = ?', (request_id, telegram_id))
    conn.commit()
    conn.close()

def update_timeout(telegram_id, hours):
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET stop_timeout = ? WHERE telegram_id = ?', (hours, telegram_id))
    conn.commit()
    conn.close()

def get_user_timeout(telegram_id):
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute('SELECT stop_timeout FROM users WHERE telegram_id = ?', (telegram_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else 8