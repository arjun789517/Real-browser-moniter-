import streamlit as st
import sqlite3
import time
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ------------------- Database -------------------
DB_FILE = "monitor.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS monitors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        url TEXT,
        interval_minutes INTEGER DEFAULT 5,
        timeout_seconds INTEGER DEFAULT 60,
        enabled INTEGER DEFAULT 1,
        last_status TEXT,  -- "online" or "offline"
        last_check TEXT,
        last_success TEXT,
        uptime_start TEXT,
        memory_mb REAL,
        error_msg TEXT
    )''')
    conn.commit()
    conn.close()

def add_monitor(name, url, interval=5, timeout=60):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO monitors (name, url, interval_minutes, timeout_seconds, enabled)
                 VALUES (?,?,?,?,1)''', (name, url, interval, timeout))
    conn.commit()
    conn.close()

def get_all_monitors():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM monitors ORDER BY id")
    rows = c.fetchall()
    conn.close()
    columns = ['id', 'name', 'url', 'interval_minutes', 'timeout_seconds', 'enabled',
               'last_status', 'last_check', 'last_success', 'uptime_start', 'memory_mb', 'error_msg']
    return [dict(zip(columns, row)) for row in rows]

def update_monitor_status(monitor_id, status, memory_mb=None, error=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().isoformat()
    if status == "online":
        c.execute('''UPDATE monitors SET last_status=?, last_check=?, last_success=?, memory_mb=?, error_msg=?
                     WHERE id=?''', (status, now, now, memory_mb, None, monitor_id))
    else:
        c.execute('''UPDATE monitors SET last_status=?, last_check=?, error_msg=?, memory_mb=?
                     WHERE id=?''', (status, now, error, memory_mb, monitor_id))
    conn.commit()
    conn.close()

def toggle_monitor(monitor_id, enabled):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE monitors SET enabled=? WHERE id=?", (1 if enabled else 0, monitor_id))
    conn.commit()
    conn.close()

def delete_monitor(monitor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM monitors WHERE id=?", (monitor_id,))
    conn.commit()
    conn.close()

# ------------------- Browser Check Function -------------------
def check_url_with_browser(url, timeout_sec, monitor_id):
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--enable-precise-memory-info')  # for memory measurement
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(timeout_sec)
        start = time.time()
        driver.get(url)
        # Wait for body to be present (customize selector as needed)
        WebDriverWait(driver, timeout_sec).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        load_time = time.time() - start

        # Optional: wait for a specific element that indicates the app is ready
        # e.g., 'div[data-testid="app-ready"]'
        # For now, just check page title or a simple selector

        # Get memory usage (JS heap)
        memory_mb = 0
        try:
            memory_mb = driver.execute_script(
                "return performance.memory.usedJSHeapSize / 1048576;"
            )
        except:
            pass

        update_monitor_status(monitor_id, "online", memory_mb=memory_mb)
        return True
    except Exception as e:
        update_monitor_status(monitor_id, "offline", error=str(e))
        return False
    finally:
        if driver:
            driver.quit()

# ------------------- Scheduler -------------------
scheduler = BackgroundScheduler()

def scheduled_check(monitor):
    if not monitor['enabled']:
        return
    check_url_with_browser(monitor['url'], monitor['timeout_seconds'], monitor['id'])

def start_scheduler():
    monitors = get_all_monitors()
    for m in monitors:
        if m['enabled']:
            scheduler.add_job(
                func=lambda mid=m['id']: scheduled_check(get_all_monitors()[mid-1]),  # crude
                trigger='interval',
                minutes=m['interval_minutes'],
                id=f"monitor_{m['id']}",
                replace_existing=True
            )
    scheduler.start()

# ------------------- Streamlit Dashboard -------------------
st.set_page_config(page_title="Real Browser Monitor", layout="wide")
st.title("🌐 Real Browser Monitor")

init_db()

# Sidebar for adding new monitor
with st.sidebar:
    st.header("➕ Add Monitor")
    name = st.text_input("Name")
    url = st.text_input("URL (https://...)")
    interval = st.number_input("Check interval (minutes)", min_value=1, value=5)
    timeout = st.number_input("Timeout (seconds)", min_value=10, value=60)
    if st.button("Add Monitor"):
        if name and url:
            add_monitor(name, url, interval, timeout)
            st.success("Monitor added. Restart scheduler or wait for next cycle.")
            st.rerun()
        else:
            st.error("Name and URL required")

# Main area: display monitors
monitors = get_all_monitors()

if not monitors:
    st.info("No monitors yet. Add one from the sidebar.")
else:
    for mon in monitors:
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            with col1:
                st.subheader(mon['name'])
                st.write(f"🔗 [{mon['url']}]({mon['url']})")
            with col2:
                status_color = "🟢" if mon['last_status'] == "online" else "🔴"
                st.metric("Status", f"{status_color} {mon['last_status'] or 'unknown'.upper()}")
                if mon['last_status'] == "online" and mon['uptime_start']:
                    uptime = datetime.now() - datetime.fromisoformat(mon['uptime_start'])
                    hours = uptime.total_seconds() // 3600
                    minutes = (uptime.total_seconds() % 3600) // 60
                    st.caption(f"Uptime: {int(hours)}h {int(minutes)}m")
            with col3:
                st.metric("Memory", f"{mon['memory_mb']:.1f} MB" if mon['memory_mb'] else "N/A")
                st.caption(f"Interval: {mon['interval_minutes']} min")
                st.caption(f"Timeout: {mon['timeout_seconds']} sec")
            with col4:
                if st.button("✅ Check", key=f"check_{mon['id']}"):
                    check_url_with_browser(mon['url'], mon['timeout_seconds'], mon['id'])
                    st.rerun()
                if mon['enabled']:
                    if st.button("⏸️ Disable", key=f"disable_{mon['id']}"):
                        toggle_monitor(mon['id'], False)
                        st.rerun()
                else:
                    if st.button("▶️ Enable", key=f"enable_{mon['id']}"):
                        toggle_monitor(mon['id'], True)
                        st.rerun()
                if st.button("🗑️ Delete", key=f"delete_{mon['id']}"):
                    delete_monitor(mon['id'])
                    st.rerun()
            st.divider()
            # Show last check info
            if mon['last_check']:
                st.caption(f"📅 Last check: {mon['last_check']}")
            if mon['error_msg']:
                st.error(f"Error: {mon['error_msg']}")

# Start scheduler only once
if 'scheduler_started' not in st.session_state:
    start_scheduler()
    st.session_state.scheduler_started = True
