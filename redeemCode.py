import sys
import time
import requests
import pandas as pd

# Force stdout to flush line-by-line instantly in GitHub Actions logs
sys.stdout.reconfigure(line_buffering=True)

# Google Sheet Details
SHEET_ID = "1GyVt_zaCZkL5R3q3veDWkahDgObumdLClu8l2hxMBuk"
GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

# Direct Century Game API Endpoints
LOGIN_URL = "https://ks-giftcode.centurygame.com/api/player"
REDEEM_URL = "https://ks-giftcode.centurygame.com/api/gift_code"

# Standard Headers to emulate a browser request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://ks-giftcode.centurygame.com",
    "Referer": "https://ks-giftcode.centurygame.com/"
}

def process_player_redemption(session, player_id, gift_code):
    """
    Directly queries Century Game backend APIs for login and gift code redemption.
    Returns (status_code, player_name, server_response_message).
    """
    # Step 1: Login / Fetch Player Info
    login_payload = {"fid": str(player_id)}
    in_game_name = "Unknown"
    
    try:
        login_res = session.post(LOGIN_URL, data=login_payload, headers=HEADERS, timeout=10)
        login_data = login_res.json()
        
        # Check login status
        if login_data.get("code") == 0 and "data" in login_data:
            in_game_name = login_data["data"].get("nickname", "Logged In")
        elif "server busy" in str(login_data.get("msg", "")).lower():
            return ("FAILED_BUSY", in_game_name, "Server Busy at Login")
        else:
            msg = login_data.get("msg", "Player not found")
            return ("FAILED_LOGIN", in_game_name, msg)
            
    except Exception as e:
        return ("ERROR", in_game_name, f"Network error during login: {e}")

    # Step 2: Submit Gift Code Redemption
    redeem_payload = {
        "fid": str(player_id),
        "cdk": gift_code
    }
    
    try:
        time.sleep(0.5) # Brief pause between login and redeem API calls
        redeem_res = session.post(REDEEM_URL, data=redeem_payload, headers=HEADERS, timeout=10)
        redeem_data = redeem_res.json()
        
        response_msg = redeem_data.get("msg", "Unknown response from server")
        
        if redeem_data.get("code") == 0:
            return ("SUCCESS", in_game_name, response_msg)
        elif "server busy" in response_msg.lower():
            return ("FAILED_BUSY", in_game_name, "Server Busy at Redemption")
        else:
            # Captures 'Gift has already been claimed!', 'Code expired', etc.
            return ("SUCCESS_LOGGED", in_game_name, response_msg)

    except Exception as e:
        return ("ERROR", in_game_name, f"Network error during redemption: {e}")


def main():
    if len(sys.argv) < 2:
        print("Error: No gift code provided.")
        sys.exit(1)
        
    gift_code = sys.argv[1].strip()
    print(f"Starting API redemption batch for Gift Code: {gift_code}")

    # Step 1: Fetch Google Sheet Data
    try:
        print("Fetching player list from Google Sheet...")
        df = pd.read_csv(SHEET_CSV_URL)
        player_ids = df.iloc[:, 0].dropna().astype(str).tolist() 
        print(f"Loaded {len(player_ids)} player IDs.")
    except Exception as e:
        print(f"Failed to read Google Sheet: {e}")
        return

    # Step 2: Process All Players via Persistent HTTP Session
    session = requests.Session()
    successful_count = 0
    failed_players = []

    start_time = time.time()

    for p_id in player_ids:
        clean_id = p_id.strip()
        status, player_name, result_msg = process_player_redemption(session, clean_id, gift_code)
        
        if status in ["SUCCESS", "SUCCESS_LOGGED"]:
            successful_count += 1
            print(f"[Player: {player_name} | ID: {clean_id}] Result: '{result_msg}'")
        else:
            failed_players.append(f"{player_name} ({clean_id}) - {result_msg}")
            print(f"[Player: {player_name} | ID: {clean_id}] Failed: '{result_msg}'")
            
        # Short pause between HTTP requests to stay under rate limits
        time.sleep(0.8)

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
