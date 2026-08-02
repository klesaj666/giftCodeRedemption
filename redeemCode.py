import sys
import time
import random
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Force stdout to flush line-by-line instantly in GitHub Actions
sys.stdout.reconfigure(line_buffering=True)

# Google Sheet Details
SHEET_ID = "1GyVt_zaCZkL5R3q3veDWkahDgObumdLClu8l2hxMBuk"
GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

# Reduced from 4 to 2 to prevent rate-limiting/Server Busy errors
MAX_WORKERS = 2 

def setup_headless_driver():
    """Initializes Chrome in headless mode."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def redeem_code_for_player(player_id, gift_code):
    """
    Spawns an isolated browser session to handle a single player ID.
    Returns a tuple: (status_code, in_game_name)
    """
    # Stagger thread starts slightly so workers don't hit the site at the exact same millisecond
    time.sleep(random.uniform(0.2, 0.8))

    driver = setup_headless_driver()
    target_url = "https://ks-giftcode.centurygame.com/"
    max_retries = 3
    current_retry = 0
    in_game_name = "Unknown"

    try:
        while current_retry < max_retries:
            try:
                driver.get(target_url)

                # Step 1: Enter Player ID
                player_id_field = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Player ID']"))
                )
                player_id_field.clear()
                player_id_field.send_keys(str(player_id))

                login_button = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".login_btn"))
                )
                login_button.click()
                
                # Step 2: Wait for Login Response & Grab Player Name
                try:
                    WebDriverWait(driver, 15).until(
                        EC.any_of(
                            EC.visibility_of_element_located((By.CSS_SELECTOR, ".roleInfo p.name")),
                            EC.visibility_of_element_located((By.CSS_SELECTOR, "p.msg"))
                        )
                    )

                    # Check if error/popup appeared instead of name
                    try:
                        popup_msg = driver.find_element(By.CSS_SELECTOR, "p.msg")
                        msg_text = popup_msg.text.lower()
                        if "server busy" in msg_text:
                            driver.find_element(By.CSS_SELECTOR, ".message_modal .confirm_btn").click()
                            current_retry += 1
                            # Increasing wait on retry (2s, 4s, 6s) to let server cool down
                            time.sleep(2 * current_retry + random.uniform(0.5, 1.5))
                            continue
                        else:
                            print(f"[ID: {player_id}] Login failed: '{popup_msg.text}'")
                            return ("FAILED_UNEXPECTED_POPUP", in_game_name)
                    except NoSuchElementException:
                        # Grab In-Game Player Name from <div class="roleInfo"><p class="name">...</p></div>
                        try:
                            name_element = driver.find_element(By.CSS_SELECTOR, ".roleInfo p.name")
                            if name_element.text.strip():
                                in_game_name = name_element.text.strip()
                        except Exception:
                            in_game_name = "Logged In"

                except TimeoutException:
                    print(f"[ID: {player_id}] Login timed out.")
                    return ("FAILED_LOGIN", in_game_name)

                # Step 3: Enter Gift Code
                gift_code_field = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Enter Gift Code']"))
                )
                gift_code_field.clear()
                gift_code_field.send_keys(gift_code)

                # Step 4: Click Confirm
                confirm_xpath = "//*[contains(translate(text(), 'CONFIRM', 'confirm'), 'confirm') or contains(@class, 'confirm')]"
                confirm_button = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, confirm_xpath))
                )
                
                try:
                    confirm_button.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", confirm_button)

                # Step 5: Handle Final Result Popup
                popup_msg = WebDriverWait(driver, 15).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "p.msg"))
                )
                msg_text = popup_msg.text.lower()
                response_text = popup_msg.text

                # Close Popup
                try:
                    confirm_btn = driver.find_element(By.CSS_SELECTOR, ".message_modal .confirm_btn")
                    confirm_btn.click()
                except Exception:
                    pass

                if "server busy" in msg_text:
                    current_retry += 1
                    # Increasing wait on retry
                    time.sleep(2 * current_retry + random.uniform(0.5, 1.5))
                    continue
                else:
                    # Print formatted result with extracted in-game name
                    print(f"[Player: {in_game_name} | ID: {player_id}] Result: '{response_text}'")
                    return ("SUCCESS", in_game_name)

            except Exception as e:
                current_retry += 1
                time.sleep(2 * current_retry)

        print(f"[Player: {in_game_name} | ID: {player_id}] Failed after {max_retries} retries due to Server Busy.")
        return ("FAILED_BUSY", in_game_name)

    finally:
        driver.quit()

def main():
    if len(sys.argv) < 2:
        print("Error: No gift code provided.")
        sys.exit(1)
        
    gift_code = sys.argv[1]
    print(f"Starting parallel redemption batch for Gift Code: {gift_code}")

    # Fetch Player IDs directly from public Google Sheet CSV
    try:
        print("Fetching player list from Google Sheet...")
        df = pd.read_csv(SHEET_CSV_URL)
        player_ids = df.iloc[:, 0].dropna().astype(str).tolist() 
        print(f"Loaded {len(player_ids)} player IDs. Running with {MAX_WORKERS} parallel workers...")
    except Exception as e:
        print(f"Failed to read Google Sheet: {e}")
        return

    successful_redemptions = 0
    failed_players = []

    start_time = time.time()

    # Execute in parallel threads
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_id = {
            executor.submit(redeem_code_for_player, p_id.strip(), gift_code): p_id 
            for p_id in player_ids
        }
        
        for future in as_completed(future_to_id):
            p_id = future_to_id[future]
            try:
                status, name = future.result()
                if status == "SUCCESS":
                    successful_redemptions += 1
                else:
                    failed_players.append(f"{name} ({p_id})")
            except Exception as exc:
                failed_players.append(f"Unknown ({p_id})")

    duration = time.time() - start_time

    print("\n--------------------------")
    print("    REDEMPTION SUMMARY    ")
    print("--------------------------")
    print(f"Total Players Processed: {len(player_ids)}")
    print(f"Successful Operations: {successful_redemptions}")
    print(f"Failed/Skipped: {len(failed_players)}")
    print(f"Total Elapsed Time: {duration:.2f} seconds")
    print("--------------------------")

if __name__ == "__main__":
    main()
