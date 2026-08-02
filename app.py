import os
import time
import hashlib
import requests
import pandas as pd
import streamlit as st

# Google Sheet Details
SHEET_ID = "1GyVt_zaCZkL5R3q3veDWkahDgObumdLClu8l2hxMBuk"
GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

# Century Game Constants
DEFAULT_KINGDOM = "113"
SECRET_SALT = "tB87#kPtkxqOS2"
# Working API Endpoint (Bypasses Akamai blocks on ks-giftcode)
REDEEM_API_URL = "https://kingshot-giftcode.centurygame.com/api/gift_code"

# Streamlit Page UI
st.set_page_config(page_title="KingShot Auto-Redeemer", page_icon="🎁")
st.title("🎁 KingShot Gift Code Redeemer")
st.write("Redeem gift codes across all Player IDs in your shared Google Sheet.")

gift_code = st.text_input("Enter Gift Code:", placeholder="e.g. KS0803").strip()

def generate_signature(params):
    """
    Sorts payload keys alphabetically, creates a query string,
    appends secret salt, and generates the MD5 signature hash.
    """
    sorted_keys = sorted(params.keys())
    query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
    to_hash = query_string + SECRET_SALT
    return hashlib.md5(to_hash.encode("utf-8")).hexdigest()

def redeem_for_player(player_id, code, kingdom_id=DEFAULT_KINGDOM):
    """
    Sends signed redemption payload directly to Century Game backend API.
    """
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://ks-giftcode.centurygame.com",
        "Referer": "https://ks-giftcode.centurygame.com/"
    }

    # Time must be Unix timestamp in SECONDS
    current_time = str(int(time.time()))
    
    params = {
        "cdk": str(code),
        "fid": str(player_id),
        "kid": str(kingdom_id),
        "time": current_time
    }
    params["sign"] = generate_signature(params)

    try:
        res = session.post(REDEEM_API_URL, data=params, headers=headers, timeout=12)
        data = res.json()
        
        msg = data.get("msg", "Unknown response from server")
        code_val = data.get("code")

        if code_val == 0:
            return "SUCCESS", msg
        elif "already" in msg.lower() or "claimed" in msg.lower():
            return "ALREADY_CLAIMED", msg
        elif "server busy" in msg.lower():
            return "FAILED_BUSY", "Server Busy"
        else:
            return "FAILED", msg

    except Exception as e:
        return "ERROR", f"Network error: {e}"

# Start Execution Button
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
            
            if status in ["SUCCESS", "ALREADY_CLAIMED"]:
                success_count += 1
                logs.append(f"✅ [ID: {clean_id} | Kingdom: {DEFAULT_KINGDOM}] Result: '{msg}'")
            else:
                failed_count += 1
                logs.append(f"❌ [ID: {clean_id} | Kingdom: {DEFAULT_KINGDOM}] Failed: '{msg}'")

            # Update live UI console
            progress_bar.progress((index + 1) / total_players)
            log_box.code("\n".join(logs[-15:]), language="text")
            
            # Short pause between API calls to prevent rate limiting
            time.sleep(0.3)

        st.balloons()
        st.success(f"Finished! Successfully Handled: {success_count} | Failed/Skipped: {failed_count}")
