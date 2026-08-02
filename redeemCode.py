import sys
import time
import random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Force stdout to flush line-by-line instantly in GitHub Actions logs
sys.stdout.reconfigure(line_buffering=True)

# Google Sheet Details
SHEET_ID = "1GyVt_zaCZkL5R3q3veDWkahDgObumdLClu8l2hxMBuk"
GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

def setup_stealth_driver():
    """Initializes Chrome in stealth mode to bypass Cloudflare/Akamai bot detection."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Anti-bot detection flags
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    
    # Hide navigator.webdriver flag
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument", 
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
    )
    return driver

def redeem_code_for_player(driver, player_id, gift_code):
    """
    Attempts to redeem a gift code for a single player ID.
    Returns (status_code, in_game_name).
    """
    target_url = "https://ks-giftcode.centurygame.com/"
    max_retries = 3
    current_retry = 0
    in_game_name = "Unknown"

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
            
            # Step 2: Wait for Login Response & Extract Player Name
            try:
                WebDriverWait(driver, 15).until(
                    EC.any_of(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, ".roleInfo p.name")),
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "p.msg"))
                    )
                )

                # Check if popup error appeared
                try:
                    popup_msg = driver.find_element(By.CSS_SELECTOR, "p.msg")
                    msg_text = popup_msg.text.lower()
                    if "server busy" in msg_text:
                        driver.find_element(By.CSS_SELECTOR, ".message_modal .confirm_btn").click()
                        current_retry += 1
                        time.sleep(4 + (current_retry * 2))
                        continue
                    else:
                        print(f"[ID: {player_id}] Login failed: '{popup_msg.text}'")
                        return ("FAILED_UNEXPECTED_POPUP", in_game_name)
                except NoSuchElementException:
                    # Extract player name from <div class="roleInfo"><p class="name">
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
                time.sleep(4 + (current_retry * 2))
                continue
            else:
                print(f"[Player: {in_game_name} | ID: {player_id}] Result: '{response_text}'")
                return ("SUCCESS", in_game_name)

        except Exception as e:
            current_retry += 1
            time.sleep(3)

    print(f"[Player: {in_game_name} | ID: {player_id}] Failed after {max_retries} retries due to Server Busy.")
    return ("FAILED_BUSY", in_game_name)

def main():
    if len(sys.argv) < 2:
        print("Error: No gift code provided.")
        sys.exit(1)
        
    gift_code = sys.argv[1].strip()
    print(f"Starting redemption batch for Gift Code: {gift_code}")

    try:
        print("Fetching player list from Google Sheet...")
        df = pd.read_csv(SHEET_CSV_URL)
        player_ids = df.iloc[:, 0].dropna().astype(str).tolist() 
        print(f"Loaded {len(player_ids)} player IDs.")
    except Exception as e:
        print(f"Failed to read Google Sheet: {e}")
        return

    driver = setup_stealth_driver()
    successful_count = 0
    failed_players = []

    start_time = time.time()

    try:
        for p_id in player_ids:
            status, name = redeem_code_for_player(driver, p_id.strip(), gift_code)
            if status == "SUCCESS":
                successful_count += 1
            else:
                failed_players.append(f"{name} ({p_id})")
            
            # Short human delay between requests to avoid rate limits
            time.sleep(random.uniform(1.5, 2.5))
    finally:
        driver.quit()

    duration = time.time() - start_time

    print("\n--------------------------")
    print("    REDEMPTION SUMMARY    ")
    print("--------------------------")
    print(f"Total Players Processed: {len(player_ids)}")
    print(f"Successful Operations: {successful_count}")
    print(f"Failed/Skipped: {len(failed_players)}")
    print(f"Total Elapsed Time: {duration:.2f} seconds")
    print("--------------------------")

if __name__ == "__main__":
    main()
