import sys
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Public Google Sheet ID & GID from your link
SHEET_ID = "1GyVt_zaCZkL5R3q3veDWkahDgObumdLClu8l2hxMBuk"
GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

def setup_headless_driver():
    """Initializes Chrome in headless mode for cloud environments."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def redeem_code_for_player(driver, player_id, gift_code):
    target_url = "https://ks-giftcode.centurygame.com/"
    max_retries = 3
    current_retry = 0

    while current_retry < max_retries:
        try:
            print(f"\nAttempting redemption for Player ID: {player_id} (Attempt {current_retry + 1})")
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
            
            # Wait for Login Response
            try:
                WebDriverWait(driver, 15).until(
                    EC.any_of(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "p.name")),
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "p.msg"))
                    )
                )

                try:
                    popup_msg = driver.find_element(By.CSS_SELECTOR, "p.msg")
                    msg_text = popup_msg.text.lower()
                    if "server busy" in msg_text:
                        print("- Server busy at login. Retrying...")
                        driver.find_element(By.CSS_SELECTOR, ".message_modal .confirm_btn").click()
                        current_retry += 1
                        time.sleep(2)
                        continue
                    else:
                        print(f"- Unexpected popup: '{popup_msg.text}'. Skipping.")
                        return "FAILED_UNEXPECTED_POPUP"
                except NoSuchElementException:
                    print("- Player logged in successfully.")

            except TimeoutException:
                print("- Login timed out. Skipping.")
                return "FAILED_LOGIN"

            # Step 2: Enter Gift Code
            gift_code_field = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Enter Gift Code']"))
            )
            gift_code_field.clear()
            gift_code_field.send_keys(gift_code)

            # Step 3: Click Confirm
            confirm_xpath = "//*[contains(translate(text(), 'CONFIRM', 'confirm'), 'confirm') or contains(@class, 'confirm')]"
            confirm_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, confirm_xpath))
            )
            
            try:
                confirm_button.click()
            except Exception:
                driver.execute_script("arguments[0].click();", confirm_button)

            # Step 4: Handle Result
            popup_msg = WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "p.msg"))
            )
            msg_text = popup_msg.text.lower()
            print(f"- Result: '{popup_msg.text}'")

            confirm_btn = driver.find_element(By.CSS_SELECTOR, ".message_modal .confirm_btn")
            confirm_btn.click()

            if "server busy" in msg_text:
                current_retry += 1
                time.sleep(2)
                continue
            else:
                return "SUCCESS"

        except Exception as e:
            print(f"- Error: {e}")
            current_retry += 1
            time.sleep(2)

    return "FAILED_BUSY"

def main():
    # Read gift code passed from GitHub Actions argument
    if len(sys.argv) < 2:
        print("Error: No gift code provided.")
        sys.exit(1)
        
    gift_code = sys.argv[1]
    print(f"Starting redemption batch for Gift Code: {gift_code}")

    # Fetch Player IDs directly from public Google Sheet CSV
    try:
        print("Fetching player list from Google Sheet...")
        df = pd.read_csv(SHEET_CSV_URL)
        # Ensure column header matches your sheet (e.g., 'PlayerID')
        player_ids = df.iloc[:, 0].dropna().astype(str).tolist() 
        print(f"Loaded {len(player_ids)} player IDs.")
    except Exception as e:
        print(f"Failed to read Google Sheet: {e}")
        return

    driver = setup_headless_driver()
    failed_players = []

    try:
        for p_id in player_ids:
            res = redeem_code_for_player(driver, p_id.strip(), gift_code)
            if res != "SUCCESS":
                failed_players.append(p_id)
            time.sleep(1)
    finally:
        driver.quit()

    print("\n--- Summary ---")
    print(f"Total Processed: {len(player_ids)}")
    print(f"Failed: {len(failed_players)}")

if __name__ == "__main__":
    main()