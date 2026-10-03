import sqlite3

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
    cursor.execute('INSERT OR REPLACE INTO users (telegram_id, portal_login, portal_password, stop_timeout) VALUES (?, ?, ?, 8)', (telegram_id, login, password))
    conn.commit()
    conn.close()

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