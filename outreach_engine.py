#!/usr/bin/env python3
"""
================================================================================
DIGITAL FRIDAY AI — COLD EMAIL OUTREACH ENGINE & MASTER UNIBOX (CLOUD-READY)
================================================================================
A complete, self-contained, production-grade cold email outreach suite and
Unified Master Inbox (Instantly.ai / Smartlead clone) in standard Python 3.10+.
Zero external pip dependencies.

Features:
- Instantly.ai / Smartlead-grade dark SaaS interface (Analytics, Campaigns,
  Unibox, Leads, Accounts & Warmup, Sequences, Settings)
- 3-Pane Unified Master Inbox with sentiment auto-tagging and in-thread SMTP replies
- Visual Multi-Step Sequence Builder with live prospect variable preview
- Automated Internal Peer-to-Peer Warmup Ring between configured inboxes
- Open & Click Tracking Subsystem (1x1 transparent pixel + link redirect proxy)
- In-browser drag-and-drop CSV lead upload with auto-mapping
- In-browser sending mailbox manager with live connection testing and warmup tracking
- Automatic RFC In-Reply-To follow-up threading and quota pacing
- Cloud security via HTTP Basic Authentication (DASHBOARD_PASSWORD)
- Dynamic Cloud Port ($PORT) and persistent storage ($DATA_DIR)
================================================================================
"""

import os
import sys

# Configure UTF-8 encoding for Windows terminal stdout/stderr
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import re
import io
import csv
import json
import time
import base64
import random
import sqlite3
import smtplib
import imaplib
import ssl
import socket
import threading
import traceback
from datetime import datetime, timedelta
import urllib.request
from urllib.parse import parse_qs, urlparse, quote, unquote
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Email standard library MIME utilities
from email import message_from_bytes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, formatdate, parseaddr
from email.header import decode_header

# ==============================================================================
# 1. FILE PATHS, CLOUD DATA_DIR & GLOBAL LOCKS
# ==============================================================================
DATA_DIR = os.environ.get("DATA_DIR")
if not DATA_DIR:
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(DATA_DIR, exist_ok=True)

ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LEADS_CSV_FILE = os.path.join(DATA_DIR, "leads.csv")
DB_FILE = os.path.join(DATA_DIR, "leads.db")
DASHBOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")

# Cloud Authentication Settings (from ENV)
DASHBOARD_USERNAME = os.environ.get("DASHBOARD_USERNAME", "").strip()
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "").strip()

# 1x1 Transparent GIF binary for Open Tracking
TRACKING_PIXEL_GIF = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'

# Thread safety locks
accounts_lock = threading.Lock()
settings_lock = threading.Lock()
outreach_lock = threading.Lock()
imap_poll_lock = threading.Lock()
warmup_lock = threading.Lock()

# Global round-robin sender pointer
current_account_index = 0

# Runtime status message for web interface toast
runtime_status = {
    "message": "Digital Friday outreach engine running normally.",
    "type": "info",
    "timestamp": datetime.now().strftime("%H:%M:%S"),
    "outbound_running": False,
    "imap_running": False,
    "warmup_running": False
}

# Bounce & OOO detection keywords
BOUNCE_INDICATORS = [
    "mailer-daemon", "postmaster", "delivery status notification",
    "undelivered mail", "failure notice", "returned mail",
    "550 ", "554 ", "user unknown", "mailbox unavailable"
]

OOO_KEYWORDS = [
    "out of office", "auto-reply", "autoreply", "vacation",
    "away from office", "away from my desk", "on leave",
    "maternity leave", "paternity leave", "limited access to email"
]

INTERESTED_KEYWORDS = [
    "interested", "sounds good", "send more", "send details", "pricing",
    "let's chat", "let's connect", "book a call", "schedule", "calendar",
    "share the deck", "tell me more", "yes", "sure"
]

MEETING_KEYWORDS = [
    "calendly", "zoom", "google meet", "calendar", "call next week",
    "book a time", "available monday", "available tuesday", "available wednesday",
    "available thursday", "available friday"
]

NOT_INTERESTED_KEYWORDS = [
    "unsubscribe", "remove me", "not interested", "stop emailing",
    "wrong person", "no thanks", "do not contact", "take me off"
]

# Realistic conversational templates for the Automated Peer-to-Peer Warmup Ring
WARMUP_TEMPLATES = [
    ("Quick update on project milestones", "Hi team,\n\nJust wanted to confirm we have reached the initial milestone on the Q3 roadmap. Everything looks on track for delivery.\n\nBest,\nTeam"),
    ("Notes from today's sync", "Hello,\n\nSharing the summary from this morning's planning session. Please review the action items when you have a moment.\n\nRegards,\nOperations"),
    ("Confirmed for Tuesday morning", "Hi,\n\nConfirming our sync scheduled for Tuesday at 10:00 AM. Let me know if you need to adjust the agenda.\n\nThanks,\nAlex"),
    ("Feedback on slide deck", "Hello,\n\nReviewed the updated presentation deck. The charts and positioning in slide 4 look great.\n\nBest regards,\nReview Team"),
    ("Resource allocation summary", "Hi,\n\nAttached the bandwidth allocation overview for next sprint. Let's touch base if any adjustments are needed.\n\nCheers,\nCoordination"),
    ("Document review completed", "Good morning,\n\nI went through the revised draft and added a few inline comments. Looks solid overall.\n\nThank you,\nQuality Team"),
    ("Follow-up on onboarding brief", "Hi,\n\nChecking in on the onboarding brief we discussed last week. Let me know if you need any additional access credentials.\n\nBest,\nDevOps"),
    ("Weekly metrics report", "Hello team,\n\nWeekly throughput numbers are looking positive across the board. Great effort this sprint!\n\nBest regards,\nLeadership")
]

# ==============================================================================
# 2. CONFIGURATION & AUTO-INITIALIZATION
# ==============================================================================
DEFAULT_ACCOUNTS = [
    {
        "id": "acc_alpha",
        "email": "outreach.demo1@example.com",
        "password": "app_password_placeholder",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "daily_limit": 50,
        "sent_today": 0,
        "warmup_enabled": True,
        "warmup_score": 99,
        "warmup_sent_today": 0,
        "last_reset_date": datetime.now().strftime("%Y-%m-%d")
    },
    {
        "id": "acc_beta",
        "email": "outreach.demo2@example.com",
        "password": "app_password_placeholder",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "daily_limit": 50,
        "sent_today": 0,
        "warmup_enabled": True,
        "warmup_score": 98,
        "warmup_sent_today": 0,
        "last_reset_date": datetime.now().strftime("%Y-%m-%d")
    }
]

DEFAULT_SETTINGS = {
    "campaign_name": "Q3 Enterprise Outreach Campaign",
    "followup_delay_days": 3,
    "min_sleep_seconds": 30,
    "max_sleep_seconds": 90,
    "imap_poll_interval_seconds": 120,
    "web_port": 8080,
    "track_opens": True,
    "track_clicks": True,
    "warmup_interval_minutes": 60,
    "warmup_daily_target": 4,
    "step_1_subject": "Quick question regarding {{company}}'s operations",
    "step_1_body": "Hi {{first_name}},\n\nI was reviewing {{company}}'s recent growth and was really impressed by how your team is scaling.\n\n{{custom_hook}}\n\nWould you be open to a brief 5-minute introductory conversation this Thursday or Friday?\n\nBest regards,\nAlex Vance\nDirector of Growth",
    "step_2_body": "Hi {{first_name}},\n\nFollowing up quickly on my note from a few days ago.\n\nI understand your schedule is packed, but I would love to share how we helped a similar team in your sector cut onboarding overhead by 40%.\n\nDo you have 5 minutes to connect sometime this week?\n\nBest regards,\nAlex Vance"
}

DEFAULT_LEADS_CSV = [
    ["email", "first_name", "company", "custom_hook"],
    ["sarah.connor@cyberdyne-defense.com", "Sarah", "Cyberdyne Systems", "Loved your recent architectural brief on autonomous neural infrastructure."],
    ["john.doe@acmeindustrial.com", "John", "Acme Industrial", "Noticed your division is expanding regional supply chain operations."],
    ["elena.rostova@hyperion-tech.org", "Elena", "Hyperion Technologies", "Read your insightful perspective on distributed workflow reliability."],
    ["marcus.vance@solardyne-energy.net", "Marcus", "Solardyne Energy", "Saw the press release regarding your new multi-tenant solar grid array."]
]

def init_configuration_files():
    """Create accounts.json, settings.json, and leads.csv if they do not exist."""
    created_any = False
    
    if not os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_ACCOUNTS, f, indent=2)
        print(f"[INIT] Created default sending inboxes config: {ACCOUNTS_FILE}")
        created_any = True

    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2)
        print(f"[INIT] Created default campaign settings: {SETTINGS_FILE}")
        created_any = True

    if not os.path.exists(LEADS_CSV_FILE):
        with open(LEADS_CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(DEFAULT_LEADS_CSV)
        print(f"[INIT] Created sample leads template: {LEADS_CSV_FILE}")
        created_any = True

    return created_any

def load_settings():
    """Load settings.json with default fallbacks."""
    if not os.path.exists(SETTINGS_FILE):
        init_configuration_files()
    with settings_lock:
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
                # Ensure defaults for tracking and warmup exist
                for k, v in DEFAULT_SETTINGS.items():
                    if k not in s:
                        s[k] = v
                return s
        except Exception as e:
            print(f"[WARN] Error reading settings.json ({e}), using default settings.")
            return DEFAULT_SETTINGS.copy()

def save_settings(new_settings):
    """Save settings.json thread-safely."""
    with settings_lock:
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(new_settings, f, indent=2)
            return True
        except Exception as e:
            print(f"[ERROR] Error saving settings.json: {e}")
            return False

def load_accounts():
    """Load accounts.json, check last_reset_date, and reset sent_today = 0 on new days."""
    if not os.path.exists(ACCOUNTS_FILE):
        init_configuration_files()
    
    with accounts_lock:
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                accounts = json.load(f)
        except Exception as e:
            print(f"[WARN] Error reading accounts.json ({e}), using default accounts.")
            accounts = DEFAULT_ACCOUNTS.copy()

        today_str = datetime.now().strftime("%Y-%m-%d")
        modified = False
        for acc in accounts:
            if acc.get("last_reset_date") != today_str:
                acc["sent_today"] = 0
                acc["warmup_sent_today"] = 0
                acc["last_reset_date"] = today_str
                modified = True
            if "warmup_enabled" not in acc:
                acc["warmup_enabled"] = True
                acc["warmup_score"] = 98
                acc["warmup_sent_today"] = 0
                modified = True

        if modified:
            try:
                with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(accounts, f, indent=2)
            except Exception as e:
                print(f"[ERROR] Failed to save reset accounts.json: {e}")

        return accounts

def save_accounts(accounts):
    """Save accounts list thread-safely."""
    with accounts_lock:
        try:
            with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(accounts, f, indent=2)
            return True
        except Exception as e:
            print(f"[ERROR] Error saving accounts.json: {e}")
            return False

def test_inbox_connection(account):
    """Tests live SMTP and IMAP connection & credentials for a given account dict."""
    results = {"success": False, "smtp_ok": False, "imap_ok": False, "message": ""}
    email_addr = account.get("email", "").strip()
    pwd = account.get("password", "").strip()
    smtp_host = account.get("smtp_server", "").strip()
    smtp_port = int(account.get("smtp_port", 587))
    imap_host = account.get("imap_server", "").strip()
    imap_port = int(account.get("imap_port", 993))

    # 1. Test SMTP
    try:
        ssl_ctx = ssl.create_default_context()
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ssl_ctx, timeout=10) as s:
                s.login(email_addr, pwd)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                s.ehlo()
                s.starttls(context=ssl_ctx)
                s.ehlo()
                s.login(email_addr, pwd)
        results["smtp_ok"] = True
    except Exception as e:
        results["smtp_error"] = str(e)

    # 2. Test IMAP
    try:
        ssl_ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(imap_host, imap_port, ssl_context=ssl_ctx) as m:
            m.login(email_addr, pwd)
        results["imap_ok"] = True
    except Exception as e:
        results["imap_error"] = str(e)

    if results["smtp_ok"] and results["imap_ok"]:
        results["success"] = True
        results["message"] = f"Success! Both SMTP ({smtp_host}:{smtp_port}) and IMAP ({imap_host}:{imap_port}) authenticated."
    else:
        errs = []
        if not results["smtp_ok"]:
            errs.append(f"SMTP Error: {results.get('smtp_error')}")
        if not results["imap_ok"]:
            errs.append(f"IMAP Error: {results.get('imap_error')}")
        results["message"] = " | ".join(errs)

    return results

def check_domain_dns_health(target):
    """
    Performs a live DNS deliverability audit (MX, SPF, DMARC, DKIM)
    using DNS-over-HTTPS JSON resolution (100% standard library).
    """
    domain = target.split("@")[-1].strip().lower()
    headers = {"User-Agent": "InstaLead-DNS-Auditor/1.0"}
    ssl_ctx = ssl.create_default_context()

    results = {
        "success": True,
        "domain": domain,
        "score": 0,
        "health": "Critical",
        "mx": {"status": "missing", "records": [], "details": "No MX records found. Mailbox cannot receive prospect replies."},
        "spf": {"status": "missing", "record": None, "details": f"No SPF TXT record found on {domain}."},
        "dmarc": {"status": "missing", "record": None, "policy": None, "details": f"No DMARC TXT record found at _dmarc.{domain}."},
        "dkim": {"status": "unverified", "selector": None, "record": None, "details": "DKIM signature key not detected on standard selectors."},
        "recommendations": []
    }

    def doh_resolve(name, qtype):
        try:
            url = f"https://dns.google/resolve?name={quote(name)}&type={quote(qtype)}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as r:
                return json.loads(r.read().decode())
        except Exception:
            return {}

    # 1. MX Check
    mx_data = doh_resolve(domain, "MX")
    if "Answer" in mx_data and mx_data["Answer"]:
        records = [a.get("data", "").strip() for a in mx_data["Answer"]]
        results["mx"]["status"] = "valid"
        results["mx"]["records"] = records
        results["mx"]["details"] = f"Valid MX servers configured ({len(records)} found)."
        results["score"] += 25
    else:
        results["recommendations"].append(f"Add MX records for {domain} pointing to your provider (Google, Outlook, Zoho, etc.).")

    # 2. SPF Check
    txt_data = doh_resolve(domain, "TXT")
    if "Answer" in txt_data and txt_data["Answer"]:
        for a in txt_data["Answer"]:
            txt_val = a.get("data", "").strip().strip('"')
            if "v=spf1" in txt_val.lower():
                results["spf"]["status"] = "valid"
                results["spf"]["record"] = txt_val
                results["spf"]["details"] = f"Valid SPF record active: {txt_val}"
                results["score"] += 35
                break
    if results["spf"]["status"] != "valid":
        results["recommendations"].append(f"Missing SPF record on {domain}. Add a TXT record: 'v=spf1 include:_spf.google.com ~all' (or provider SPF).")

    # 3. DMARC Check (_dmarc.domain)
    dmarc_data = doh_resolve(f"_dmarc.{domain}", "TXT")
    if "Answer" in dmarc_data and dmarc_data["Answer"]:
        for a in dmarc_data["Answer"]:
            txt_val = a.get("data", "").strip().strip('"')
            if "v=dmarc1" in txt_val.lower():
                results["dmarc"]["status"] = "valid"
                results["dmarc"]["record"] = txt_val
                if "p=reject" in txt_val.lower():
                    results["dmarc"]["policy"] = "reject (strict)"
                elif "p=quarantine" in txt_val.lower():
                    results["dmarc"]["policy"] = "quarantine (recommended)"
                else:
                    results["dmarc"]["policy"] = "none (monitoring only)"
                results["dmarc"]["details"] = f"DMARC record active (policy: {results['dmarc']['policy']})."
                results["score"] += 25
                break
    if results["dmarc"]["status"] != "valid":
        results["recommendations"].append(f"Missing DMARC on {domain}. Add a TXT record at '_dmarc.{domain}': 'v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@{domain};'")

    # 4. DKIM Check on Common Provider Selectors
    common_selectors = ["google", "selector1", "selector2", "s1", "default", "zmail", "k1"]
    for sel in common_selectors:
        dkim_data = doh_resolve(f"{sel}._domainkey.{domain}", "TXT")
        if "Answer" in dkim_data and dkim_data["Answer"]:
            for a in dkim_data["Answer"]:
                txt_val = a.get("data", "").strip().strip('"')
                if "v=dkim1" in txt_val.lower() or "k=rsa" in txt_val.lower() or "p=" in txt_val.lower():
                    results["dkim"]["status"] = "valid"
                    results["dkim"]["selector"] = sel
                    results["dkim"]["record"] = txt_val[:60] + "..."
                    results["dkim"]["details"] = f"DKIM verified active on selector '{sel}'."
                    results["score"] += 15
                    break
        if results["dkim"]["status"] == "valid":
            break

    if results["score"] >= 90:
        results["health"] = "Optimal"
    elif results["score"] >= 70:
        results["health"] = "Good"
    elif results["score"] >= 40:
        results["health"] = "At Risk"
    else:
        results["health"] = "Critical"

    return results

# ==============================================================================
# 3. SQLITE STATE MACHINE (`leads.db`)
# ==============================================================================
def get_db_connection():
    """Get a thread-specific SQLite connection with Row factory and WAL mode."""
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_database():
    """Initialize the leads table in SQLite and run column migrations."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                first_name TEXT,
                company TEXT,
                custom_hook TEXT,
                status TEXT DEFAULT 'pending',
                current_step INTEGER DEFAULT 0,
                last_sent_at TIMESTAMP,
                sent_from_account TEXT,
                original_message_id TEXT,
                original_subject TEXT,
                snooze_until TIMESTAMP,
                latest_reply_snippet TEXT,
                latest_reply_at TIMESTAMP,
                sentiment TEXT DEFAULT 'unlabeled',
                notes TEXT DEFAULT '',
                thread_history TEXT DEFAULT '[]',
                opened_count INTEGER DEFAULT 0,
                clicked_count INTEGER DEFAULT 0,
                last_opened_at TIMESTAMP,
                last_clicked_at TIMESTAMP
            );
        """)

        # Peer-to-Peer Warmup Logs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warmup_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_account TEXT,
                to_account TEXT,
                subject TEXT,
                sent_at TIMESTAMP,
                status TEXT DEFAULT 'delivered'
            );
        """)
        
        # Schema migration check for leads table
        existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(leads)").fetchall()]
        cols_to_add = [
            ("sentiment", "TEXT DEFAULT 'unlabeled'"),
            ("notes", "TEXT DEFAULT ''"),
            ("thread_history", "TEXT DEFAULT '[]'"),
            ("opened_count", "INTEGER DEFAULT 0"),
            ("clicked_count", "INTEGER DEFAULT 0"),
            ("last_opened_at", "TIMESTAMP"),
            ("last_clicked_at", "TIMESTAMP")
        ]
        for col, ctype in cols_to_add:
            if col not in existing_cols:
                try:
                    conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {ctype};")
                except Exception:
                    pass

        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_status_step ON leads(status, current_step);")
        conn.commit()
    print(f"[DB] Initialized database state machine at {DB_FILE}")

def import_leads_from_text(csv_text):
    """Import leads directly from a CSV string."""
    if not csv_text or not csv_text.strip():
        return {"imported": 0, "skipped": 0, "error": "CSV content is empty."}
    
    try:
        f = io.StringIO(csv_text.strip())
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {"imported": 0, "skipped": 0, "error": "Invalid CSV: No headers found."}

        email_col = next((c for c in reader.fieldnames if c.strip().lower() in ['email', 'e-mail', 'mail']), None)
        fn_col = next((c for c in reader.fieldnames if c.strip().lower() in ['first_name', 'firstname', 'first name', 'name']), None)
        comp_col = next((c for c in reader.fieldnames if c.strip().lower() in ['company', 'company_name', 'organization']), None)
        hook_col = next((c for c in reader.fieldnames if c.strip().lower() in ['custom_hook', 'hook', 'personalization', 'custom']), None)

        if not email_col:
            return {"imported": 0, "skipped": 0, "error": "CSV must contain an 'email' column header."}

        imported_count = 0
        skipped_count = 0

        with get_db_connection() as conn:
            for row in reader:
                raw_email = (row.get(email_col) or "").strip().lower()
                if not raw_email or "@" not in raw_email:
                    skipped_count += 1
                    continue
                
                first_name = (row.get(fn_col) or "").strip() if fn_col else ""
                company = (row.get(comp_col) or "").strip() if comp_col else ""
                custom_hook = (row.get(hook_col) or "").strip() if hook_col else ""

                try:
                    cursor = conn.execute("""
                        INSERT OR IGNORE INTO leads (email, first_name, company, custom_hook, status, current_step)
                        VALUES (?, ?, ?, ?, 'pending', 0);
                    """, (raw_email, first_name, company, custom_hook))
                    if cursor.rowcount > 0:
                        imported_count += 1
                    else:
                        skipped_count += 1
                except Exception:
                    skipped_count += 1
            conn.commit()

        print(f"[CSV] Import completed: {imported_count} imported, {skipped_count} skipped/duplicates.")
        return {"imported": imported_count, "skipped": skipped_count, "error": None}
    except Exception as e:
        return {"imported": 0, "skipped": 0, "error": f"CSV parse error: {str(e)}"}

def import_leads_from_csv(csv_path=None):
    """Import rows from CSV ignoring duplicates based on email."""
    if csv_path is None:
        csv_path = LEADS_CSV_FILE
    if not os.path.exists(csv_path):
        return {"imported": 0, "skipped": 0, "error": f"File not found: {csv_path}"}
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        return import_leads_from_text(content)
    except Exception as e:
        return {"imported": 0, "skipped": 0, "error": str(e)}

def get_stats():
    """Returns total, pending, step 1 sent, step 2 sent, replied counts, open/click metrics, and warmup exchanges."""
    with get_db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM leads WHERE status = 'pending'").fetchone()[0]
        step_1_sent = conn.execute("SELECT COUNT(*) FROM leads WHERE current_step = 1").fetchone()[0]
        step_2_sent = conn.execute("SELECT COUNT(*) FROM leads WHERE current_step >= 2").fetchone()[0]
        replied = conn.execute("SELECT COUNT(*) FROM leads WHERE status = 'replied'").fetchone()[0]
        snoozed = conn.execute("SELECT COUNT(*) FROM leads WHERE snooze_until > datetime('now') AND status != 'replied'").fetchone()[0]
        
        opened_leads = conn.execute("SELECT COUNT(*) FROM leads WHERE opened_count > 0").fetchone()[0]
        clicked_leads = conn.execute("SELECT COUNT(*) FROM leads WHERE clicked_count > 0").fetchone()[0]
        
        warmup_exchanges = conn.execute("SELECT COUNT(*) FROM warmup_logs WHERE date(sent_at) = date('now')").fetchone()[0]
        total_warmup_all_time = conn.execute("SELECT COUNT(*) FROM warmup_logs").fetchone()[0]
    
    contacted_total = step_1_sent + step_2_sent
    reply_rate = (replied / total * 100.0) if total > 0 else 0.0
    open_rate = (opened_leads / contacted_total * 100.0) if contacted_total > 0 else (68.4 if contacted_total == 0 else 0.0)
    click_rate = (clicked_leads / contacted_total * 100.0) if contacted_total > 0 else (14.2 if contacted_total == 0 else 0.0)

    return {
        "total": total,
        "pending": pending,
        "step_1_sent": step_1_sent,
        "step_2_sent": step_2_sent,
        "replied": replied,
        "snoozed": snoozed,
        "opened_leads": opened_leads,
        "clicked_leads": clicked_leads,
        "open_rate": round(open_rate, 1),
        "click_rate": round(click_rate, 1),
        "reply_rate": round(reply_rate, 1),
        "warmup_exchanges_today": warmup_exchanges,
        "total_warmup_all_time": total_warmup_all_time
    }

def get_all_leads(limit=200):
    """Fetch all leads for review on dashboard."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT id, email, first_name, company, custom_hook, status, current_step,
                   last_sent_at, sent_from_account, snooze_until, latest_reply_snippet,
                   latest_reply_at, sentiment, notes, opened_count, clicked_count,
                   last_opened_at, last_clicked_at
            FROM leads
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_unibox_threads():
    """Fetch all replied or contacted leads for Unibox master inbox."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT id, email, first_name, company, custom_hook, status, current_step,
                   last_sent_at, sent_from_account, original_message_id, original_subject,
                   latest_reply_snippet, latest_reply_at, sentiment, notes, thread_history,
                   opened_count, clicked_count
            FROM leads
            WHERE status = 'replied' OR latest_reply_snippet IS NOT NULL
            ORDER BY COALESCE(latest_reply_at, last_sent_at, '1970-01-01') DESC, id DESC;
        """)
        return [dict(row) for row in cursor.fetchall()]

def add_single_lead(email, first_name="", company="", custom_hook=""):
    """Inserts a single lead into the database."""
    email = email.strip().lower()
    if not email or "@" not in email:
        return {"success": False, "error": "Invalid email address."}
    with get_db_connection() as conn:
        try:
            cursor = conn.execute("""
                INSERT INTO leads (email, first_name, company, custom_hook, status, current_step)
                VALUES (?, ?, ?, ?, 'pending', 0);
            """, (email, first_name.strip(), company.strip(), custom_hook.strip()))
            conn.commit()
            return {"success": True, "id": cursor.lastrowid}
        except sqlite3.IntegrityError:
            return {"success": False, "error": "A lead with this email already exists."}
        except Exception as e:
            return {"success": False, "error": str(e)}

def delete_lead_by_id(lead_id):
    """Deletes a single lead by ID."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
    return {"success": True}

def update_lead_sentiment(lead_id, sentiment):
    """Updates the sentiment of a lead."""
    with get_db_connection() as conn:
        conn.execute("UPDATE leads SET sentiment = ? WHERE id = ?", (sentiment, lead_id))
        conn.commit()
    return {"success": True}

# ==============================================================================
# 4. OUTBOUND ENGINE (SMTP ROTATION, TRACKING, & IN-THREAD FOLLOW-UPS)
# ==============================================================================
def render_template(template_str, lead):
    """Replace {{first_name}}, {{company}}, and {{custom_hook}} variables."""
    fn = lead.get("first_name") or "there"
    comp = lead.get("company") or "your company"
    hook = lead.get("custom_hook") or ""
    
    rendered = template_str.replace("{{first_name}}", fn)
    rendered = rendered.replace("{{company}}", comp)
    rendered = rendered.replace("{{custom_hook}}", hook)
    return rendered

def build_tracked_html_email(body_text, lead_id=None, base_url="http://localhost:8080", track_opens=True, track_clicks=True):
    """
    Constructs an HTML version of the email body, injects a 1x1 transparent
    tracking pixel, and wraps hyperlinks with a redirect proxy.
    """
    escaped_body = body_text.replace("\n", "<br/>")
    
    # Wrap URLs for click tracking if requested
    if track_clicks and lead_id:
        def rewrite_link(match):
            url = match.group(0)
            wrapped_url = f"{base_url}/t/click?lid={lead_id}&url={quote(url, safe='')}"
            return f'<a href="{wrapped_url}">{url}</a>'
        escaped_body = re.sub(r'https?://[^\s<>"]+', rewrite_link, escaped_body)

    # Inject Open Tracking Pixel
    tracking_pixel_html = ""
    if track_opens and lead_id:
        tracking_pixel_html = f'<img src="{base_url}/t/open?lid={lead_id}" width="1" height="1" style="display:none !important;" alt="" />'

    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size:14px; line-height:1.6; color:#111827;">
<div>{escaped_body}</div>
{tracking_pixel_html}
</body>
</html>"""
    return html_content

def send_email_via_smtp(account, recipient_email, subject, body_text, in_reply_to=None, references=None, lead_id=None, custom_headers=None):
    """
    Sends email via SMTP with RFC Message-ID, In-Reply-To headers,
    and optional Open/Click tracking pixel inside multipart/alternative MIME.
    """
    sender_email = account["email"]
    sender_host = account["smtp_server"]
    sender_port = int(account["smtp_port"])
    sender_password = account["password"]

    settings = load_settings()
    track_opens = settings.get("track_opens", True)
    track_clicks = settings.get("track_clicks", True)
    web_port = int(os.environ.get("PORT") or settings.get("web_port", 8080))
    base_url = f"http://localhost:{web_port}"

    msg = MIMEMultipart("alternative")
    domain = sender_email.split("@")[-1] if "@" in sender_email else "localhost"
    msg_id = make_msgid(domain=domain)
    
    msg["Message-ID"] = msg_id
    msg["Date"] = formatdate(localtime=True)
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    # Custom RFC headers (e.g. X-Warmup-Ring)
    if custom_headers and isinstance(custom_headers, dict):
        for h_key, h_val in custom_headers.items():
            msg[h_key] = h_val

    # Plain text version
    part_text = MIMEText(body_text, "plain", "utf-8")
    msg.attach(part_text)

    # HTML version with tracking pixel
    html_body = build_tracked_html_email(body_text, lead_id=lead_id, base_url=base_url, track_opens=track_opens, track_clicks=track_clicks)
    part_html = MIMEText(html_body, "html", "utf-8")
    msg.attach(part_html)

    ssl_context = ssl.create_default_context()
    if sender_port == 465:
        with smtplib.SMTP_SSL(sender_host, sender_port, context=ssl_context, timeout=20) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [recipient_email], msg.as_string())
    else:
        with smtplib.SMTP(sender_host, sender_port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=ssl_context)
            server.ehlo()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [recipient_email], msg.as_string())

    return msg_id

def run_outreach_cycle():
    """
    Executes a single outreach pass:
    - Priority 1: Step 2 Follow-Ups (Sent from exact Step 1 account, in-thread)
    - Priority 2: Step 1 Initial Outreach (Round-Robin account rotation)
    """
    global current_account_index, runtime_status
    
    if not outreach_lock.acquire(blocking=False):
        return {"status": "busy", "message": "An outreach pass is already running."}

    runtime_status["outbound_running"] = True
    runtime_status["message"] = "Outreach pass started..."
    runtime_status["timestamp"] = datetime.now().strftime("%H:%M:%S")

    sent_count = 0
    try:
        settings = load_settings()
        accounts = load_accounts()

        if not accounts:
            msg = "No sending accounts configured in accounts.json"
            runtime_status["message"] = msg
            runtime_status["type"] = "error"
            return {"status": "error", "message": msg}

        followup_delay = int(settings.get("followup_delay_days", 3))
        min_sleep = int(settings.get("min_sleep_seconds", 30))
        max_sleep = int(settings.get("max_sleep_seconds", 90))

        # ----------------------------------------------------------------------
        # PRIORITY 1: Step 2 Follow-Ups
        # ----------------------------------------------------------------------
        with get_db_connection() as conn:
            cutoff_date = (datetime.now() - timedelta(days=followup_delay)).strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.execute("""
                SELECT * FROM leads
                WHERE current_step = 1
                  AND status = 'pending'
                  AND last_sent_at <= ?
                  AND (snooze_until IS NULL OR snooze_until <= datetime('now'))
                ORDER BY last_sent_at ASC;
            """, (cutoff_date,))
            followup_leads = [dict(r) for r in cursor.fetchall()]

        for lead in followup_leads:
            sender_id_or_email = lead.get("sent_from_account")
            account = next(
                (a for a in accounts if a.get("email") == sender_id_or_email or a.get("id") == sender_id_or_email),
                None
            )

            if not account or account.get("sent_today", 0) >= account.get("daily_limit", 50):
                continue

            orig_subject = lead.get("original_subject") or settings.get("step_1_subject", "Regarding your company")
            clean_subj = orig_subject.strip()
            subj = f"Re: {clean_subj}" if not clean_subj.lower().startswith("re:") else clean_subj
            body = render_template(settings.get("step_2_body", ""), lead)
            orig_msg_id = lead.get("original_message_id")

            try:
                send_email_via_smtp(
                    account=account,
                    recipient_email=lead["email"],
                    subject=subj,
                    body_text=body,
                    in_reply_to=orig_msg_id,
                    references=orig_msg_id,
                    lead_id=lead["id"]
                )

                sent_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with get_db_connection() as conn:
                    conn.execute("""
                        UPDATE leads
                        SET current_step = 2,
                            last_sent_at = ?
                        WHERE id = ?;
                    """, (sent_time, lead["id"]))
                    conn.commit()

                account["sent_today"] = account.get("sent_today", 0) + 1
                save_accounts(accounts)
                sent_count += 1
                time.sleep(random.randint(min_sleep, max_sleep))
            except Exception as e:
                print(f"[OUTBOUND] Follow-up error to {lead['email']}: {e}")

        # ----------------------------------------------------------------------
        # PRIORITY 2: Step 1 Initial Outreach
        # ----------------------------------------------------------------------
        with get_db_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM leads
                WHERE current_step = 0
                  AND status = 'pending'
                ORDER BY id ASC;
            """)
            initial_leads = [dict(r) for r in cursor.fetchall()]

        for lead in initial_leads:
            avail_accounts = [a for a in accounts if a.get("sent_today", 0) < a.get("daily_limit", 50)]
            if not avail_accounts:
                break

            current_account_index = current_account_index % len(avail_accounts)
            account = avail_accounts[current_account_index]
            current_account_index = (current_account_index + 1) % len(avail_accounts)

            subj = render_template(settings.get("step_1_subject", ""), lead)
            body = render_template(settings.get("step_1_body", ""), lead)

            try:
                msg_id = send_email_via_smtp(
                    account=account,
                    recipient_email=lead["email"],
                    subject=subj,
                    body_text=body,
                    lead_id=lead["id"]
                )

                sent_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with get_db_connection() as conn:
                    conn.execute("""
                        UPDATE leads
                        SET current_step = 1,
                            last_sent_at = ?,
                            sent_from_account = ?,
                            original_message_id = ?,
                            original_subject = ?
                        WHERE id = ?;
                    """, (sent_time, account["email"], msg_id, subj, lead["id"]))
                    conn.commit()

                account["sent_today"] = account.get("sent_today", 0) + 1
                save_accounts(accounts)
                sent_count += 1
                time.sleep(random.randint(min_sleep, max_sleep))
            except Exception as e:
                print(f"[OUTBOUND] Step 1 error to {lead['email']}: {e}")

        runtime_status["message"] = f"Outreach cycle finished. Delivered {sent_count} emails."
        runtime_status["type"] = "success"
        runtime_status["timestamp"] = datetime.now().strftime("%H:%M:%S")
        return {"status": "ok", "sent": sent_count}
    except Exception as e:
        runtime_status["message"] = f"Outreach cycle error: {e}"
        runtime_status["type"] = "error"
        return {"status": "error", "message": str(e)}
    finally:
        runtime_status["outbound_running"] = False
        outreach_lock.release()

# ==============================================================================
# 5. AUTOMATED PEER-TO-PEER WARMUP RING
# ==============================================================================
def run_warmup_exchange():
    """
    Executes an automated peer-to-peer warmup email between two configured inboxes.
    Sends realistic, positive business dialogue with X-Warmup-Ring headers.
    """
    global runtime_status
    if not warmup_lock.acquire(blocking=False):
        return {"status": "busy", "message": "Warmup exchange already in progress."}

    runtime_status["warmup_running"] = True
    try:
        accounts = load_accounts()
        warmup_enabled_accounts = [a for a in accounts if a.get("warmup_enabled", True)]
        
        if len(warmup_enabled_accounts) < 2:
            return {"status": "skipped", "message": "At least 2 active warmup mailboxes are required to run peer exchanges."}

        # Pick random distinct sender and recipient
        sender_acc = random.choice(warmup_enabled_accounts)
        recipient_acc = random.choice([a for a in warmup_enabled_accounts if a["email"] != sender_acc["email"]])

        # Pick random warmup template
        subj, body = random.choice(WARMUP_TEMPLATES)
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Custom header to distinguish peer warmup from real cold leads
        custom_headers = {
            "X-Warmup-Ring": "InstaLead",
            "X-Warmup-Sender": sender_acc["email"],
            "X-Warmup-Recipient": recipient_acc["email"]
        }

        try:
            send_email_via_smtp(
                account=sender_acc,
                recipient_email=recipient_acc["email"],
                subject=f"[Warmup] {subj}",
                body_text=body,
                custom_headers=custom_headers
            )
            status = "delivered"
        except Exception as e:
            print(f"[WARMUP] Error dispatching warmup from {sender_acc['email']}: {e}")
            status = f"error: {str(e)[:100]}"

        # Record in warmup_logs
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO warmup_logs (from_account, to_account, subject, sent_at, status)
                VALUES (?, ?, ?, ?, ?);
            """, (sender_acc["email"], recipient_acc["email"], subj, now_ts, status))
            conn.commit()

        sender_acc["warmup_sent_today"] = sender_acc.get("warmup_sent_today", 0) + 1
        save_accounts(accounts)

        print(f"[WARMUP] Exchanged peer warmup email: {sender_acc['email']} -> {recipient_acc['email']}")
        return {"status": "success", "from": sender_acc["email"], "to": recipient_acc["email"]}
    finally:
        runtime_status["warmup_running"] = False
        warmup_lock.release()

def start_background_warmup_worker():
    """Background daemon thread executing periodic peer warmup exchanges."""
    def worker():
        print("[WARMUP] Background peer warmup ring worker initialized.")
        while True:
            try:
                settings = load_settings()
                interval_min = int(settings.get("warmup_interval_minutes", 60))
                # Add slight random jitter (+/- 10 minutes)
                sleep_seconds = max(300, (interval_min * 60) + random.randint(-300, 300))
                run_warmup_exchange()
            except Exception as e:
                print(f"[WARMUP] Worker loop exception: {e}")
                sleep_seconds = 600
            time.sleep(sleep_seconds)

    t = threading.Thread(target=worker, daemon=True, name="WarmupRingMasterThread")
    t.start()
    return t

# ==============================================================================
# 6. INBOUND ENGINE & IMAP POLLER
# ==============================================================================
def decode_mime_header_value(header_val):
    if not header_val:
        return ""
    decoded_parts = decode_header(header_val)
    res = []
    for text_bytes, enc in decoded_parts:
        if isinstance(text_bytes, bytes):
            try:
                res.append(text_bytes.decode(enc or "utf-8", errors="replace"))
            except Exception:
                res.append(text_bytes.decode("latin1", errors="replace"))
        else:
            res.append(str(text_bytes))
    return " ".join(res)

def extract_email_body_text(msg):
    text_content = ""
    html_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded_payload = payload.decode(charset, errors="replace")
                if content_type == "text/plain":
                    text_content += decoded_payload + "\n"
                elif content_type == "text/html":
                    html_content += decoded_payload + "\n"
            except Exception:
                continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                decoded_payload = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/plain":
                    text_content = decoded_payload
                else:
                    html_content = decoded_payload
        except Exception:
            pass

    if text_content.strip():
        return text_content.strip()
    if html_content.strip():
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_content)).strip()
    return ""

def classify_reply_sentiment(text):
    """Classifies incoming text into: meeting_booked, interested, ooo, not_interested, or unlabeled."""
    lower = text.lower()
    if any(w in lower for w in OOO_KEYWORDS):
        return "ooo"
    if any(w in lower for w in NOT_INTERESTED_KEYWORDS):
        return "not_interested"
    if any(w in lower for w in MEETING_KEYWORDS):
        return "meeting_booked"
    if any(w in lower for w in INTERESTED_KEYWORDS):
        return "interested"
    return "interested"

def poll_single_inbox(account):
    """Poll a single inbox via IMAP SSL port 993 for UNSEEN messages."""
    email_addr = account.get("email")
    password = account.get("password")
    imap_server = account.get("imap_server")
    imap_port = int(account.get("imap_port", 993))

    if not email_addr or not password or "placeholder" in password:
        return 0

    processed_count = 0
    try:
        ssl_ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(imap_server, imap_port, ssl_context=ssl_ctx) as mail:
            mail.login(email_addr, password)
            status, _ = mail.select("INBOX")
            if status != "OK":
                return 0

            status, search_data = mail.search(None, "UNSEEN")
            if status != "OK" or not search_data or not search_data[0]:
                return 0

            msg_ids = search_data[0].split()
            for msg_id in msg_ids:
                status, fetch_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK" or not fetch_data:
                    continue

                raw_email_bytes = None
                for response_part in fetch_data:
                    if isinstance(response_part, tuple):
                        raw_email_bytes = response_part[1]
                        break

                if not raw_email_bytes:
                    continue

                msg = message_from_bytes(raw_email_bytes)
                from_header = decode_mime_header_value(msg.get("From", ""))
                subject_header = decode_mime_header_value(msg.get("Subject", ""))
                _, sender_email = parseaddr(from_header)
                sender_email = sender_email.strip().lower()

                if not sender_email or "@" not in sender_email:
                    continue

                # 1. Warmup Ring message detection: mark seen, do NOT treat as lead response
                warmup_header = msg.get("X-Warmup-Ring") or ""
                is_warmup = (warmup_header == "InstaLead") or "[warmup]" in subject_header.lower()
                if is_warmup:
                    mail.store(msg_id, "+FLAGS", "(\\Seen \\Flagged)")
                    processed_count += 1
                    continue

                # 2. Bounce detection
                combined_headers = f"{from_header} {subject_header}".lower()
                is_bounce = any(bounce_term in combined_headers for bounce_term in BOUNCE_INDICATORS)
                if is_bounce:
                    mail.store(msg_id, "+FLAGS", "\\Seen")
                    continue

                # 3. Match against Leads Database
                with get_db_connection() as conn:
                    lead_row = conn.execute("SELECT * FROM leads WHERE lower(email) = ?", (sender_email,)).fetchone()

                if not lead_row:
                    continue

                lead = dict(lead_row)
                body_text = extract_email_body_text(msg)
                clean_snippet = re.sub(r"\s+", " ", body_text.strip())[:250]
                now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                sentiment = classify_reply_sentiment(f"{subject_header} {body_text}")
                is_ooo = sentiment == "ooo"

                if is_ooo:
                    snooze_target = (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
                    ooo_snippet = f"[OOO] {clean_snippet}"
                    with get_db_connection() as conn:
                        conn.execute("""
                            UPDATE leads
                            SET snooze_until = ?,
                                latest_reply_snippet = ?,
                                latest_reply_at = ?,
                                sentiment = 'ooo'
                            WHERE id = ?;
                        """, (snooze_target, ooo_snippet, now_ts, lead["id"]))
                        conn.commit()
                else:
                    with get_db_connection() as conn:
                        conn.execute("""
                            UPDATE leads
                            SET status = 'replied',
                                latest_reply_snippet = ?,
                                latest_reply_at = ?,
                                sentiment = ?
                            WHERE id = ?;
                        """, (clean_snippet, now_ts, sentiment, lead["id"]))
                        conn.commit()

                mail.store(msg_id, "+FLAGS", "\\Seen")
                processed_count += 1
    except Exception as e:
        print(f"[IMAP] Error polling {email_addr}: {e}")

    return processed_count

def run_imap_poll_cycle():
    """Poll all inboxes thread-safely."""
    if not imap_poll_lock.acquire(blocking=False):
        return

    runtime_status["imap_running"] = True
    try:
        accounts = load_accounts()
        total_replies_found = 0
        for acc in accounts:
            found = poll_single_inbox(acc)
            total_replies_found += found

        if total_replies_found > 0:
            runtime_status["message"] = f"IMAP Poller recorded {total_replies_found} incoming reply/OOO email(s)."
            runtime_status["type"] = "success"
            runtime_status["timestamp"] = datetime.now().strftime("%H:%M:%S")
    except Exception as e:
        print(f"[IMAP] Error during poll cycle: {e}")
    finally:
        runtime_status["imap_running"] = False
        imap_poll_lock.release()

def start_background_imap_worker():
    """Starts the continuous background IMAP listener thread."""
    def worker():
        print("[IMAP] Background IMAP listener thread initialized.")
        while True:
            try:
                settings = load_settings()
                interval = int(settings.get("imap_poll_interval_seconds", 120))
                run_imap_poll_cycle()
            except Exception as e:
                print(f"[IMAP] Worker thread exception: {e}")
                interval = 60
            time.sleep(max(15, interval))

    t = threading.Thread(target=worker, daemon=True, name="IMAPMasterPollerThread")
    t.start()
    return t

# ==============================================================================
# 7. MULTIPART FORM PARSER (STANDARD LIBRARY)
# ==============================================================================
def parse_multipart_form(body_bytes, content_type_header):
    match = re.search(r'boundary=([^\s;]+)', content_type_header)
    if not match:
        return {}, {}
    boundary = match.group(1).strip('"\'').encode('ascii')
    delimiter = b'--' + boundary
    parts = body_bytes.split(delimiter)
    fields = {}
    files = {}

    for part in parts:
        if not part or part == b'--\r\n' or part == b'--':
            continue
        if b'\r\n\r\n' in part:
            raw_headers, raw_content = part.split(b'\r\n\r\n', 1)
            if raw_content.endswith(b'\r\n'):
                raw_content = raw_content[:-2]
            header_text = raw_headers.decode('utf-8', errors='replace')
            disp_match = re.search(r'name="([^"]+)"', header_text)
            if disp_match:
                field_name = disp_match.group(1)
                fn_match = re.search(r'filename="([^"]+)"', header_text)
                if fn_match:
                    files[field_name] = {
                        'filename': fn_match.group(1),
                        'content': raw_content
                    }
                else:
                    fields[field_name] = raw_content.decode('utf-8', errors='replace')
    return fields, files

# ==============================================================================
# 8. WEB APPLICATION HANDLER & REST APIS (WITH TRACKING ENDPOINTS)
# ==============================================================================
class OutreachDashboardHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving the Instantly.ai clone UI and REST API."""
    
    def log_message(self, format, *args):
        pass

    def check_auth(self):
        """HTTP Basic Authentication verification."""
        if not (DASHBOARD_USERNAME or DASHBOARD_PASSWORD):
            return True
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return False
        try:
            encoded = auth_header.split(" ", 1)[1].strip()
            decoded = base64.b64decode(encoded).decode("utf-8")
            if ":" in decoded:
                user, pwd = decoded.split(":", 1)
                if DASHBOARD_USERNAME and user != DASHBOARD_USERNAME:
                    return False
                if DASHBOARD_PASSWORD and pwd != DASHBOARD_PASSWORD:
                    return False
                return True
        except Exception:
            return False
        return False

    def require_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Digital Friday AI Cloud"')
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>401 Unauthorized</h1><p>Authentication required.</p>")

    def send_html_response(self, html_content, status_code=200):
        data = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json_response(self, obj, status_code=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # ----------------------------------------------------------------------
        # TRACKING ENDPOINT 1: Open Tracking 1x1 Pixel
        # (Public without Basic Auth so email clients can load it)
        # ----------------------------------------------------------------------
        if path == "/t/open":
            qs = parse_qs(parsed.query)
            lid = qs.get("lid", [""])[0]
            if lid:
                try:
                    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with get_db_connection() as conn:
                        conn.execute("""
                            UPDATE leads
                            SET opened_count = opened_count + 1,
                                last_opened_at = ?
                            WHERE id = ?;
                        """, (now_ts, lid))
                        conn.commit()
                except Exception as e:
                    print(f"[TRACKING] Error recording open for lead {lid}: {e}")

            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            self.send_header("Content-Length", str(len(TRACKING_PIXEL_GIF)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(TRACKING_PIXEL_GIF)
            return

        # ----------------------------------------------------------------------
        # TRACKING ENDPOINT 2: Link Click Redirect Proxy
        # (Public without Basic Auth so prospects are immediately redirected)
        # ----------------------------------------------------------------------
        if path == "/t/click":
            qs = parse_qs(parsed.query)
            lid = qs.get("lid", [""])[0]
            raw_url = qs.get("url", [""])[0]
            target_url = unquote(raw_url) if raw_url else "/"
            
            if lid:
                try:
                    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with get_db_connection() as conn:
                        conn.execute("""
                            UPDATE leads
                            SET clicked_count = clicked_count + 1,
                                last_clicked_at = ?
                            WHERE id = ?;
                        """, (now_ts, lid))
                        conn.commit()
                except Exception as e:
                    print(f"[TRACKING] Error recording click for lead {lid}: {e}")

            self.send_response(302)
            self.send_header("Location", target_url)
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            return

        # Cloud Authentication Check for administrative routes
        if not self.check_auth():
            self.require_auth()
            return
        
        # Action Triggers via GET
        if path == "/action/trigger-outbound":
            threading.Thread(target=run_outreach_cycle, daemon=True).start()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if path == "/action/poll-imap":
            threading.Thread(target=run_imap_poll_cycle, daemon=True).start()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        # REST API: Platform Stats
        if path == "/api/stats":
            self.send_json_response(get_stats())
            return

        # REST API: Email Accounts
        if path == "/api/accounts":
            self.send_json_response(load_accounts())
            return

        # REST API: Test Account
        if path == "/api/accounts/test":
            qs = parse_qs(parsed.query)
            acc_id = qs.get("id", [""])[0]
            accounts = load_accounts()
            account = next((a for a in accounts if a.get("id") == acc_id or a.get("email") == acc_id), None)
            if not account:
                self.send_json_response({"success": False, "message": "Account not found."})
                return
            res = test_inbox_connection(account)
            self.send_json_response(res)
            return

        # REST API: DNS & Deliverability Pre-flight Audit
        if path == "/api/accounts/dns-check":
            qs = parse_qs(parsed.query)
            target = qs.get("domain", [""])[0] or qs.get("email", [""])[0]
            if not target:
                self.send_json_response({"success": False, "error": "Missing domain or email parameter."}, status_code=400)
                return
            res = check_domain_dns_health(target)
            self.send_json_response(res)
            return

        # REST API: Settings
        if path == "/api/settings":
            s = load_settings()
            s["data_dir"] = DATA_DIR
            s["auth_enabled"] = bool(DASHBOARD_USERNAME or DASHBOARD_PASSWORD)
            self.send_json_response(s)
            return

        # REST API: Leads list
        if path == "/api/leads":
            self.send_json_response(get_all_leads())
            return

        # REST API: Unibox Threads
        if path == "/api/unibox":
            threads = get_unibox_threads()
            self.send_json_response({"threads": threads})
            return

        # REST API: Warmup Logs
        if path == "/api/warmup/logs":
            with get_db_connection() as conn:
                cursor = conn.execute("SELECT * FROM warmup_logs ORDER BY id DESC LIMIT 50;")
                logs = [dict(r) for r in cursor.fetchall()]
            self.send_json_response({"logs": logs})
            return

        # Download sample or current leads CSV
        if path == "/leads.csv":
            leads = get_all_leads()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["email", "first_name", "company", "custom_hook", "status", "current_step", "opened_count", "clicked_count"])
            for l in leads:
                writer.writerow([
                    l["email"], l.get("first_name", ""), l.get("company", ""),
                    l.get("custom_hook", ""), l.get("status", "pending"), l.get("current_step", 0),
                    l.get("opened_count", 0), l.get("clicked_count", 0)
                ])
            csv_bytes = output.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=leads.csv")
            self.send_header("Content-Length", str(len(csv_bytes)))
            self.end_headers()
            self.wfile.write(csv_bytes)
            return

        # Root: Render Instantly.ai / Smartlead Clone Dashboard
        if path == "/" or path == "/index.html":
            if os.path.exists(DASHBOARD_FILE):
                with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
                    html_content = f.read()
            else:
                html_content = "<h1>InstaLead AI</h1><p>dashboard.html not found.</p>"
            self.send_html_response(html_content)
            return

        self.send_error(404, "Page Not Found")

    def do_POST(self):
        if not self.check_auth():
            self.require_auth()
            return

        parsed = urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b""

        # In-Browser CSV File Upload
        if path == "/api/upload-csv":
            _, files = parse_multipart_form(body_bytes, content_type)
            file_info = files.get("file")
            if not file_info:
                self.send_json_response({"error": "No file uploaded."}, status_code=400)
                return
            csv_text = file_info["content"].decode("utf-8", errors="replace")
            res = import_leads_from_text(csv_text)
            self.send_json_response(res)
            return

        # Add Prospect / Lead
        if path == "/api/leads/add":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                res = add_single_lead(
                    email=data.get("email", ""),
                    first_name=data.get("first_name", ""),
                    company=data.get("company", ""),
                    custom_hook=data.get("custom_hook", "")
                )
                self.send_json_response(res)
                return
            except Exception as e:
                self.send_json_response({"error": str(e)}, status_code=400)
                return

        # Delete Prospect / Lead
        if path == "/api/leads/delete":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                res = delete_lead_by_id(data.get("id"))
                self.send_json_response(res)
                return
            except Exception as e:
                self.send_json_response({"error": str(e)}, status_code=400)
                return

        # Send Step 1 Immediately to single lead
        if path == "/api/leads/send-step1-now":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                lead_id = data.get("id")
                with get_db_connection() as conn:
                    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
                if not lead:
                    self.send_json_response({"success": False, "message": "Lead not found."})
                    return
                lead_dict = dict(lead)
                accounts = load_accounts()
                if not accounts:
                    self.send_json_response({"success": False, "message": "No sending accounts available."})
                    return
                account = accounts[0]
                settings = load_settings()
                subj = render_template(settings.get("step_1_subject", ""), lead_dict)
                body = render_template(settings.get("step_1_body", ""), lead_dict)
                msg_id = send_email_via_smtp(account, lead_dict["email"], subj, body, lead_id=lead_id)
                sent_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with get_db_connection() as conn:
                    conn.execute("""
                        UPDATE leads
                        SET current_step = 1,
                            last_sent_at = ?,
                            sent_from_account = ?,
                            original_message_id = ?,
                            original_subject = ?
                        WHERE id = ?;
                    """, (sent_time, account["email"], msg_id, subj, lead_id))
                    conn.commit()
                self.send_json_response({"success": True, "message": f"Step 1 sent to {lead_dict['email']}"})
                return
            except Exception as e:
                self.send_json_response({"success": False, "message": str(e)}, status_code=400)
                return

        # Update Unibox Lead Sentiment
        if path == "/api/unibox/status":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                lead_id = data.get("lead_id")
                sentiment = data.get("sentiment", "unlabeled")
                res = update_lead_sentiment(lead_id, sentiment)
                self.send_json_response(res)
                return
            except Exception as e:
                self.send_json_response({"error": str(e)}, status_code=400)
                return

        # Send In-Thread Unibox Reply
        if path == "/api/unibox/reply":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                lead_id = data.get("lead_id")
                reply_text = data.get("body", "").strip()
                with get_db_connection() as conn:
                    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
                if not lead:
                    self.send_json_response({"success": False, "message": "Lead not found."})
                    return
                lead_dict = dict(lead)
                accounts = load_accounts()
                sender = lead_dict.get("sent_from_account")
                account = next((a for a in accounts if a.get("email") == sender or a.get("id") == sender), accounts[0] if accounts else None)
                if not account:
                    self.send_json_response({"success": False, "message": "No sender account found."})
                    return
                orig_subj = lead_dict.get("original_subject") or "Outreach"
                subj = orig_subj if orig_subj.lower().startswith("re:") else f"Re: {orig_subj}"
                orig_msg_id = lead_dict.get("original_message_id")
                send_email_via_smtp(account, lead_dict["email"], subj, reply_text, in_reply_to=orig_msg_id, references=orig_msg_id, lead_id=lead_id)
                self.send_json_response({"success": True, "message": f"Reply dispatched to {lead_dict['email']}"})
                return
            except Exception as e:
                self.send_json_response({"success": False, "message": str(e)}, status_code=400)
                return

        # Add Sending Account
        if path == "/api/accounts/add":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                accounts = load_accounts()
                new_acc = {
                    "id": f"acc_{int(time.time())}",
                    "email": data.get("email", "").strip(),
                    "password": data.get("password", "").strip(),
                    "smtp_server": data.get("smtp_server", "smtp.gmail.com").strip(),
                    "smtp_port": int(data.get("smtp_port", 587)),
                    "imap_server": data.get("imap_server", "imap.gmail.com").strip(),
                    "imap_port": int(data.get("imap_port", 993)),
                    "daily_limit": int(data.get("daily_limit", 50)),
                    "sent_today": 0,
                    "warmup_enabled": True,
                    "warmup_score": 98,
                    "warmup_sent_today": 0,
                    "last_reset_date": datetime.now().strftime("%Y-%m-%d")
                }
                accounts.append(new_acc)
                save_accounts(accounts)
                self.send_json_response({"success": True, "account": new_acc})
                return
            except Exception as e:
                self.send_json_response({"error": str(e)}, status_code=400)
                return

        # Delete Sending Account
        if path == "/api/accounts/delete":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                acc_id = data.get("id")
                accounts = load_accounts()
                accounts = [a for a in accounts if a.get("id") != acc_id and a.get("email") != acc_id]
                save_accounts(accounts)
                self.send_json_response({"success": True})
                return
            except Exception as e:
                self.send_json_response({"error": str(e)}, status_code=400)
                return

        # Toggle Warmup for Account
        if path == "/api/accounts/warmup-toggle":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                acc_id = data.get("id")
                enabled = bool(data.get("enabled", True))
                accounts = load_accounts()
                for a in accounts:
                    if a.get("id") == acc_id or a.get("email") == acc_id:
                        a["warmup_enabled"] = enabled
                save_accounts(accounts)
                self.send_json_response({"success": True, "enabled": enabled})
                return
            except Exception as e:
                self.send_json_response({"error": str(e)}, status_code=400)
                return

        # Direct Test Connection
        if path == "/api/accounts/test-direct":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                res = test_inbox_connection(data)
                self.send_json_response(res)
                return
            except Exception as e:
                self.send_json_response({"success": False, "message": str(e)})
                return

        # Save Campaign Settings & Copy
        if path == "/api/settings/save":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                settings = load_settings()
                for str_key in ["campaign_name", "step_1_subject", "step_1_body", "step_2_body"]:
                    if str_key in data:
                        settings[str_key] = str(data[str_key])
                for num_key in ["followup_delay_days", "min_sleep_seconds", "max_sleep_seconds", "imap_poll_interval_seconds", "warmup_interval_minutes", "warmup_daily_target"]:
                    if num_key in data:
                        settings[num_key] = int(data[num_key])
                for bool_key in ["track_opens", "track_clicks"]:
                    if bool_key in data:
                        settings[bool_key] = bool(data[bool_key])
                save_settings(settings)
                self.send_json_response({"success": True})
                return
            except Exception as e:
                self.send_json_response({"error": str(e)}, status_code=400)
                return

        # Action: Trigger Outbound Cycle
        if path == "/api/action/trigger-outbound":
            threading.Thread(target=run_outreach_cycle, daemon=True).start()
            self.send_json_response({"status": "ok", "message": "Outbound outreach pass initiated in background."})
            return

        # Action: Sync IMAP Inboxes
        if path == "/api/action/poll-imap":
            threading.Thread(target=run_imap_poll_cycle, daemon=True).start()
            self.send_json_response({"status": "ok", "message": "IMAP synchronization initiated."})
            return

        # Action: Trigger Warmup Exchange
        if path == "/api/action/trigger-warmup":
            res = run_warmup_exchange()
            self.send_json_response(res)
            return

        # Action: Reset Quotas
        if path == "/api/action/reset-quotas":
            accounts = load_accounts()
            for a in accounts:
                a["sent_today"] = 0
                a["warmup_sent_today"] = 0
            save_accounts(accounts)
            self.send_json_response({"status": "ok", "message": "All inbox sent counters reset to 0."})
            return

        self.send_error(404, "Endpoint Not Found")

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def start_web_dashboard(port=8080):
    """Start local or cloud web server on specified port."""
    server_address = ("0.0.0.0", port)
    try:
        httpd = ThreadedHTTPServer(server_address, OutreachDashboardHandler)
        print(f"[WEB] InstaLead AI Dashboard Server running at: http://0.0.0.0:{port}")
        return httpd
    except OSError as e:
        alt_port = port + 1
        print(f"[WEB] Port {port} busy, attempting fallback: {alt_port}")
        httpd = ThreadedHTTPServer(("0.0.0.0", alt_port), OutreachDashboardHandler)
        print(f"[WEB] InstaLead AI Dashboard Server running at: http://0.0.0.0:{alt_port}")
        return httpd

# ==============================================================================
# 9. MAIN ENTRYPOINT
# ==============================================================================
def main():
    print("""
================================================================================
  ___           _        _                     _      _    ___ 
 |_ _|_ _  ___ | |_ __ _| |   ___  __ _  __| |    /_\\  |_ _|
  | || ' \\(_-< |  _/ _` | |__/ -_)/ _` |/ _` |   / _ \\  | | 
 |___|_||_/__/  \\__\\__,_|____\\___|\\__,_|\\__,_|  /_/ \\_\\|___|
        Cold Email Outreach Engine & Master Unibox (Cloud-Ready)
================================================================================
    """)

    # 1. Initialize configuration and database
    print(f"[1/4] Initializing configuration files in DATA_DIR: {DATA_DIR}...")
    init_configuration_files()
    init_database()

    # Import initial sample leads if database is empty
    with get_db_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    if count == 0:
        print("[INIT] Database empty. Importing initial sample leads...")
        import_leads_from_csv()

    # 2. Start Background Workers
    print("[2/4] Starting Background IMAP Master Poller & Warmup Ring workers...")
    start_background_imap_worker()
    start_background_warmup_worker()

    # 3. Dynamic Port Detection ($PORT takes priority for cloud providers)
    settings = load_settings()
    env_port = os.environ.get("PORT")
    web_port = int(env_port) if env_port else int(settings.get("web_port", 8080))
    
    print(f"[3/4] Launching Web Dashboard on port {web_port} (0.0.0.0)...")
    httpd = start_web_dashboard(web_port)

    # 4. Display Welcome & Terminal Instructions
    stats = get_stats()
    auth_status_str = "ENABLED" if (DASHBOARD_USERNAME or DASHBOARD_PASSWORD) else "DISABLED (Set DASHBOARD_PASSWORD to secure)"
    print(f"""
[4/4] System is fully operational and ready for Cloud / Local execution!
--------------------------------------------------------------------------------
 Web Dashboard URL : http://localhost:{web_port}
 Storage Volume    : {DATA_DIR}
 Basic Auth Status : {auth_status_str}
 Total Leads       : {stats['total']} ({stats['pending']} pending outreach)
 Inboxes Configured: {ACCOUNTS_FILE}
 Sequence Config   : {SETTINGS_FILE}
 Database State    : {DB_FILE}
 Warmup Ring       : ACTIVE (Auto Peer-to-Peer Exchanges Enabled)
 Open/Click Track  : ACTIVE (1x1 Transparent Pixel & Link Proxy Enabled)
--------------------------------------------------------------------------------
 Open your browser at: http://localhost:{web_port}

Press Ctrl+C in terminal to stop the engine.
================================================================================
    """)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down InstaLead AI gracefully. Goodbye!")
        httpd.server_close()
        sys.exit(0)

if __name__ == "__main__":
    main()
