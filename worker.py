import asyncio
import random
import sqlite3
from datetime import datetime, timedelta
import database
import parser
import time

START_HOURS = {"06-14": 6, "14-22": 14, "22-06": 22, "ANY": 6}

# Cache login errors to avoid spamming the user every minute
login_errors = {}

def get_users_with_requests():
    conn = sqlite3.connect('shifts.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT u.telegram_id, u.portal_login, u.portal_password, u.stop_timeout
        FROM users u
        JOIN shift_requests r ON u.telegram_id = r.telegram_id
        WHERE r.status = 'pending'
    ''')
    users = cursor.fetchall()
    conn.close()
    return users

async def check_timeout(req_id, target_date, time_type, timeout_hours):
    base_hour = START_HOURS.get(time_type, 6)
    dt_str = f"{target_date} {base_hour:02d}:00"
    target_dt = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
    now = datetime.now()
    if target_dt - now <= timedelta(hours=timeout_hours):
        return True
    return False

async def start_monitoring(bot_instance):
    from bot import notify_monitoring_stopped, notify_shift_booked, notify_error
    
    print("Background worker started!")
    
    while True:
        users = get_users_with_requests()
        
        for user in users:
            telegram_id, login, password, timeout_hours = user
            requests = database.get_active_requests(telegram_id)
            
            if not requests:
                continue
                
            driver = await asyncio.to_thread(parser.setup_driver)
            
            try:
                is_logged_in = await asyncio.to_thread(parser.login, driver, login, password)
                
                if not is_logged_in:
                    if not login_errors.get(telegram_id, False):
                        await notify_error(telegram_id, "Failed to log in to the portal! Check your password.")
                        login_errors[telegram_id] = True  # Remember that we already warned
                    continue
                else:
                    login_errors[telegram_id] = False  # Reset the error if login succeeds
                    
                await asyncio.to_thread(parser.show_maximum_shifts, driver)
                
                for req in requests:
                    # Unpack force_booking as part of the request data
                    req_id, target_date, time_type, target_shift_type, force_booking = req 
                    
                    is_expired = await check_timeout(req_id, target_date, time_type, timeout_hours)
                    if is_expired:
                        database.delete_request(req_id, telegram_id)
                        await notify_monitoring_stopped(telegram_id, target_date, time_type, timeout_hours)
                        continue
                    
                    # Try up to 2 times in case a conflicting shift had to be canceled first
                    max_retries = 2
                    for _ in range(max_retries):
                        success, error_msg = await asyncio.to_thread(parser.attempt_booking, driver, target_date, time_type, target_shift_type, force_booking)
                        
                        if success == "RELOAD":
                            await notify_error(telegram_id, f"⚠️ Conflict found for {target_date}! Automatically cancelled the blocking shift. Retrying to book the new one now...")
                            await asyncio.to_thread(driver.refresh)
                            time.sleep(2)
                            await asyncio.to_thread(parser.show_maximum_shifts, driver)
                            continue 
                            
                        # === New notification block ===
                        elif success == "NOTIFY":
                            database.delete_request(req_id, telegram_id)
                            from bot import notify_shift_found
                            await notify_shift_found(telegram_id, target_date, f"{time_type} ({target_shift_type})")
                            break  # Exit the retry loop
                            
                        elif success == True:
                            database.delete_request(req_id, telegram_id)
                            # notify_shift_booked import can be here or at the top
                            from bot import notify_shift_booked
                            await notify_shift_booked(telegram_id, target_date, f"{time_type} ({target_shift_type})")
                            break
                            
                        elif error_msg:
                            # notify_error import can be here or at the top
                            from bot import notify_error
                            await notify_error(telegram_id, error_msg)
                            break
                            
                        else:
                            break  # No shift found, success = False
                        
            except Exception as e:
                print(f"Error in worker: {e}")
            finally:
                await asyncio.to_thread(driver.quit)
                
        sleep_seconds = random.randint(100, 240)
        # sleep_seconds = random.randint(20, 40)
        print(f"Sleeping for {sleep_seconds} seconds...\n")
        await asyncio.sleep(sleep_seconds)