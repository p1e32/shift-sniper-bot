from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import time
import os
from datetime import datetime, timedelta

def setup_driver():
    options = Options()
    # options.add_argument("--headless=new") # Enable headless mode
    # options.add_argument("--no-sandbox") # Required for Linux servers
    # options.add_argument("--disable-dev-shm-usage") # Helps with memory issues on Linux
    
    options.add_argument("--headless=new")  # Headless mode
    
    # --- New flags for better stability in headless mode ---
    options.add_argument("--window-size=1920,1080")  # Set a full HD screen size
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    return driver

def login(driver, username, password):
    print(f"Attempting login for user: {username}")
    portal_url = os.getenv("PORTAL_URL", "https://example.com")
    driver.get(portal_url)
    wait = WebDriverWait(driver, 10)
    try:
        wait.until(EC.presence_of_element_located((By.ID, "login"))).send_keys(username)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        wait.until(EC.presence_of_element_located((By.ID, "invitations_table")))
        return True
    except TimeoutException:
        return False

def show_maximum_shifts(driver):
    try:
        wait = WebDriverWait(driver, 10)
        invitations_select = wait.until(EC.presence_of_element_located((By.NAME, "invitations_table_length")))
        driver.execute_script("arguments[0].value = '100'; arguments[0].dispatchEvent(new Event('change'));", invitations_select)
        
        try:
            scheduled_select = driver.find_element(By.NAME, "scheduled_shifts_table_length")
            driver.execute_script("arguments[0].value = '100'; arguments[0].dispatchEvent(new Event('change'));", scheduled_select)
        except NoSuchElementException:
            pass
            
        time.sleep(2)
    except Exception as e:
        print(f"Error while changing table display: {e}")

def resolve_conflict_and_cancel(driver, target_date_str, target_from_str, target_to_str):
    """Looks for a conflicting shift in the lower table and cancels it."""
    # Create datetime objects for the desired shift
    t_start = datetime.strptime(f"{target_date_str} {target_from_str}", "%d.%m.%Y %H:%M")
    t_end = datetime.strptime(f"{target_date_str} {target_to_str}", "%d.%m.%Y %H:%M")
    margin = timedelta(hours=10)  # Required rest period
    
    rows = driver.find_elements(By.CSS_SELECTOR, "#scheduled_shifts_table tbody tr")
    for row in rows:
        try:
            s_date = row.find_element(By.CSS_SELECTOR, "td[name='date']").text
            s_from = row.find_element(By.CSS_SELECTOR, "td[name='time_from']").text
            s_to = row.find_element(By.CSS_SELECTOR, "td[name='time_to']").text
            
            s_start = datetime.strptime(f"{s_date} {s_from}", "%d.%m.%Y %H:%M")
            s_end = datetime.strptime(f"{s_date} {s_to}", "%d.%m.%Y %H:%M")
            
            # Check whether a conflict exists (whether there is 10 hours of rest before or after)
            is_conflict = True
            if (s_end + margin <= t_start) or (t_end + margin <= s_start):
                is_conflict = False  # Enough rest, no conflict
                
            if is_conflict:
                print(f"CONFLICT FOUND! The shift {s_date} {s_from}-{s_to} is blocking")
                
                try:
                    cancel_btn = row.find_element(By.CSS_SELECTOR, "button.cancel_shift")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cancel_btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", cancel_btn)
                    
                    wait = WebDriverWait(driver, 5)
                    confirm_btn = wait.until(EC.element_to_be_clickable((By.ID, "cancel_submit")))
                    
                    confirm_btn.click()  # Final confirmation click to cancel
                    
                    print("[TEST] Cancellation confirmation window passed!")
                    return True, None
                except NoSuchElementException:
                    return False, f"Shift {s_date} {s_from} is blocking, but has no Cancel button!"
                except TimeoutException:
                    return False, "Could not click confirm button on Cancel modal."
                    
        except NoSuchElementException:
            continue
            
    return False, "Conflict block is present, but I couldn't find which shift is causing it."

def attempt_booking(driver, target_date, target_time_type, target_shift_type, force_booking):
    """Looks for a shift and returns (Status, Message). Status can be True, False, 'RELOAD', or 'NOTIFY'."""
    base_hours = {"06-14": 6, "14-22": 14, "22-06": 22}
    
    # --- Internal row-scanning helper function ---
    def scan_rows(rows_to_check):
        for row in rows_to_check:
            try:
                date = row.find_element(By.CSS_SELECTOR, "td[name='date']").text
                time_from = row.find_element(By.CSS_SELECTOR, "td[name='time_from']").text
                time_to = row.find_element(By.CSS_SELECTOR, "td[name='time_to']").text
                
                if date == target_date:
                    shift_start_hour = int(time_from.split(":")[0])
                    is_match = False
                    
                    if target_time_type == "ANY":
                        is_match = True
                    else:
                        target_hour = base_hours.get(target_time_type)
                        if abs(shift_start_hour - target_hour) <= 2:
                            is_match = True
                            
                    if is_match:
                        try:
                            subscribe_btn = row.find_element(By.CSS_SELECTOR, "button.subscribe_shift")
                        except NoSuchElementException:
                            # Check for a lock (10-hour rule)
                            try:
                                row.find_element(By.CSS_SELECTOR, ".fa-ban")
                                if force_booking == 1:
                                    print(f"The shift {time_from} is blocked. Starting Force Booking...")
                                    resolved, err = resolve_conflict_and_cancel(driver, date, time_from, time_to)
                                    if resolved:
                                        return "RELOAD", None 
                                    else:
                                        return False, err
                                else:
                                    continue
                            except NoSuchElementException:
                                continue

                        shift_info = subscribe_btn.get_attribute("data-name").upper()
                        
                        is_type_match = False
                        if target_shift_type == "IMPORT" and "IMPORT" in shift_info:
                            is_type_match = True
                        elif target_shift_type == "EXPORT" and "EXPORT" in shift_info:
                            is_type_match = True
                        elif target_shift_type == "ANY" and ("IMPORT" in shift_info or "EXPORT" in shift_info):
                            is_type_match = True
                            
                        if not is_type_match:
                            continue 

                        if force_booking == 2:
                            print(f"🔔 Found shift {date} {time_from}. Mode 'Notify Only'.")
                            return "NOTIFY", None

                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", subscribe_btn)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", subscribe_btn)
                        except Exception:
                            return False, f"Could not click 'Subscribe' for {date} {time_from}."

                        wait = WebDriverWait(driver, 5)
                        try:
                            lunch_radio = wait.until(EC.element_to_be_clickable((By.ID, "lunch_yes")))
                            lunch_radio.click()
                        except TimeoutException:
                            return False, f"Could not find 'Lunch' checkbox for {date} {time_from}."
                        
                        try:
                            confirm_btn = wait.until(EC.element_to_be_clickable((By.ID, "subscribe_submit")))
                            # confirm_btn.click()  # Uncomment for live booking
                            print("[TEST] Subscription confirmation window passed!")
                            return True, None
                        except TimeoutException:
                            return False, f"Could not find 'Confirm' button for {date} {time_from}."
                        
            except NoSuchElementException:
                continue
                
        return None  # If the loop finished and nothing matched

    # --- Search logic ---
    
    # 1. First attempt (visible rows)
    rows = driver.find_elements(By.CSS_SELECTOR, "#invitations_table tbody tr")
    result = scan_rows(rows)
    if result is not None:
        return result
        
    # 2. Second attempt (fallback via the search box)
    print(f"The shift for {target_date} was not found immediately. Trying the search field...")
    try:
        search_input = driver.find_element(By.CSS_SELECTOR, "#invitations_table_filter input[type='search']")
        search_input.clear()
        search_input.send_keys(target_date)
        time.sleep(1.5)  # Wait until the table is filtered (JavaScript)
        
        # Fetch rows again from the filtered table
        rows = driver.find_elements(By.CSS_SELECTOR, "#invitations_table tbody tr")
        result = scan_rows(rows)
        if result is not None:
            return result
            
    except NoSuchElementException:
        print("Search field not found on the page.")
        
    return False, None  # If no shifts are found at all, return False