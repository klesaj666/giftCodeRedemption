import os
import time
import hashlib
import requests
import pandas as pd
import streamlit as st

# Configuration
SHEET_ID = "1GyVt_zaCZkL5R3q3veDWkahDgObumdLClu8l2hxMBuk"
GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

# Default Kingdom and ZenRows API Key
DEFAULT_KINGDOM = "113"
DEFAULT_ZENROWS_KEY = "3e252db2ff3782d8d5d0f585f85a2dbda6e7b4db"

SECRET_SALT = "tB87#kPtkxqOS2"
REDEEM_URL = "https://kingshot-giftcode.centurygame.com/api/gift_code"

# Streamlit UI Configuration
st.set_page_config(page_title="KingShot Auto-Redeemer", page_icon="🎁")
st.title("🎁 KingShot Gift Code Redeemer")
st.write("Redeem gift codes across all Player IDs in your shared Google Sheet.")

# Single User Input: Gift Code
gift_code = st.text_input("Enter Gift Code:", placeholder="e.g. KS0803").strip()

def generate_signature(params):
    """
    Sorts payload keys alphabetically, creates a query string,
    appends secret salt, and returns the required MD5 signature.
    """
    sorted_keys = sorted(params.keys())
    query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
    to_hash = query_string + SECRET_SALT
    return hashlib.md5(to_hash.encode("utf-8")).hexdigest()

def make_request(target_url, payload, api_key):
    """Routes the POST request through ZenRows residential proxy."""
    if api_key:
        proxy_url = f"https://api.zenrows.com/v1/?key={api_key}&url={target_url}"
        res = requests.post(proxy_url, data=payload, timeout=20)
    else:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://ks-giftcode.centurygame.com",
            "Referer": "https://ks-giftcode.centurygame.com/"
        }
        res = requests.post(target_url, data=payload, headers=headers, timeout=15)
    
    return res.json()

def redeem_for_player(player_id, code, kingdom_id=DEFAULT_KINGDOM, api_key=DEFAULT_ZENROWS_KEY):
    """Sends signed redemption payload directly to Century Game backend."""
    current_time = str(int(time.time())) # Time must be in seconds
    
    params = {
        "cdk": str(code),
        "fid": str(player_id),
        "kid": str(kingdom_id),
        "time": current_time
    }
    params["sign"] = generate_signature(params)

    try:
        data = make_request(REDEEM_URL, params, api_key)
        msg = data.get("msg", "No message returned")
        
        if data.get("code") == 0:
            return "SUCCESS", msg
        elif "already been claimed" in msg.lower():
            return "SUCCESS_LOGGED", msg
        elif "server busy" in msg.lower():
            return "FAILED_BUSY", "Server Busy"
        else:
            return "FAILED", msg
    except Exception as e:
        return "ERROR", f"Connection error: {e}"

# Start Button Trigger
if st.button("🚀 Start Redemption Process", type="primary"):
    if not gift_code:
        st.error("Please enter a Gift Code first.")
    else:
        st.info("Fetching player list from Google Sheet...")
        try:
            df = pd.read_csv(SHEET_CSV_URL)
            player_ids = df.iloc[:, 0].dropna().astype(str).tolist()
            st.success(f"Loaded {len(player_ids)} players from Google Sheet!")
        except Exception as e:
            st.error(f"Failed to read Google Sheet: {e}")
            st.stop()

        progress_bar = st.progress(0)
        log_box = st.empty()
        logs = []

        success_count = 0
        failed_count = 0
        total_players = len(player_ids)

        for index, p_id in enumerate(player_ids):
            clean_id = p_id.strip()
            status, msg = redeem_for_player(clean_id, gift_code)
            
            if status in ["SUCCESS", "SUCCESS_LOGGED"]:
                success_count += 1
                logs.append(f"✅ [ID: {clean_id} | Kingdom: {DEFAULT_KINGDOM}] Result: '{msg}'")
            else:
                failed_count += 1
                logs.append(f"❌ [ID: {clean_id} | Kingdom: {DEFAULT_KINGDOM}] Failed: '{msg}'")

            # Update live UI console
            progress_bar.progress((index + 1) / total_players)
            log_box.code("\n".join(logs[-15:]), language="text")
            time.sleep(0.4)

        st.balloons()
        st.success(f"Finished! Successfully Handled: {success_count} | Failed/Skipped: {failed_count}")
