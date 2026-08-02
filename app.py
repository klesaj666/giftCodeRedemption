import os
import time
import requests
import pandas as pd
import streamlit as st

# Configuration
SHEET_ID = "1GyVt_zaCZkL5R3q3veDWkahDgObumdLClu8l2hxMBuk"
GID = "0"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

LOGIN_URL = "https://ks-giftcode.centurygame.com/api/player"
REDEEM_URL = "https://ks-giftcode.centurygame.com/api/gift_code"

# Page UI Layout
st.set_page_config(page_title="KingShot Auto-Redeemer", page_icon="🎁")
st.title("🎁 KingShot Gift Code Redeemer")
st.write("Redeem codes across all Player IDs in the shared Google Sheet instantly.")

# User Inputs
gift_code = st.text_input("Enter Gift Code:", placeholder="e.g. KS0803").strip()
zenrows_api_key = st.text_input("ZenRows API Key (optional if stored in Secrets):", type="password").strip()

# Retrieve API Key from Streamlit Secrets or user input
api_key = zenrows_api_key or os.environ.get("ZENROWS_API_KEY", "")

def make_proxy_request(target_url, payload, api_key):
    """Routes POST requests through ZenRows residential proxy API."""
    if not api_key:
        # Fallback to direct request if no key provided
        res = requests.post(
            target_url, 
            data=payload, 
            headers={"User-Agent": "Mozilla/5.0"}, 
            timeout=15
        )
        return res.json()
    
    # ZenRows proxy endpoint
    proxy_url = f"https://api.zenrows.com/v1/?key={api_key}&url={target_url}"
    res = requests.post(proxy_url, data=payload, timeout=20)
    return res.json()

def redeem_for_player(player_id, code, api_key):
    """Processes login and gift code redemption for a single ID."""
    # 1. Login / Fetch Player Info
    try:
        login_data = make_proxy_request(LOGIN_URL, {"fid": str(player_id)}, api_key)
        
        if login_data.get("code") == 0 and "data" in login_data:
            player_name = login_data["data"].get("nickname", "Logged In")
        elif "server busy" in str(login_data.get("msg", "")).lower():
            return "FAILED_BUSY", "Unknown", "Server Busy at Login"
        else:
            return "FAILED_LOGIN", "Unknown", login_data.get("msg", "Player not found")
    except Exception as e:
        return "ERROR", "Unknown", f"Network error: {e}"

    # 2. Redeem Code
    try:
        time.sleep(0.5)
        redeem_data = make_proxy_request(REDEEM_URL, {"fid": str(player_id), "cdk": code}, api_key)
        response_msg = redeem_data.get("msg", "No response")
        
        if redeem_data.get("code") == 0 or "already been claimed" in response_msg.lower():
            return "SUCCESS", player_name, response_msg
        elif "server busy" in response_msg.lower():
            return "FAILED_BUSY", player_name, "Server Busy at Redemption"
        else:
            return "SUCCESS", player_name, response_msg
    except Exception as e:
        return "ERROR", player_name, f"Network error: {e}"

# Start Button
if st.button("🚀 Start Redemption Process", type="primary"):
    if not gift_code:
        st.error("Please enter a valid Gift Code first.")
    else:
        st.info("Fetching player list from Google Sheet...")
        try:
            df = pd.read_csv(SHEET_CSV_URL)
            player_ids = df.iloc[:, 0].dropna().astype(str).tolist()
            st.success(f"Loaded {len(player_ids)} players from Google Sheet!")
        except Exception as e:
            st.error(f"Failed to read Google Sheet: {e}")
            st.stop()

        # UI Progress Bar and Live Output Console
        progress_bar = st.progress(0)
        log_box = st.empty()
        logs = []

        success_count = 0
        failed_count = 0

        total_players = len(player_ids)
        
        for index, p_id in enumerate(player_ids):
            clean_id = p_id.strip()
            status, name, msg = redeem_for_player(clean_id, gift_code, api_key)
            
            if status == "SUCCESS":
                success_count += 1
                logs.append(f"✅ [Player: {name} | ID: {clean_id}] {msg}")
            else:
                failed_count += 1
                logs.append(f"❌ [Player: {name} | ID: {clean_id}] Failed: {msg}")

            # Update Streamlit UI in real-time
            progress_bar.progress((index + 1) / total_players)
            log_box.code("\n".join(logs[-15:]), language="text") # Displays last 15 log lines
            time.sleep(0.5)

        st.balloons()
        st.success(f"Finished! Success: {success_count} | Failed/Skipped: {failed_count}")
