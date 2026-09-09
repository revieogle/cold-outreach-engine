# ⚡ InstaLead AI — Cold Email Outreach Engine & Master Unibox

An enterprise-grade, high-performance cold email outreach suite and Unified Master Inbox modeled after **Instantly.ai** and **Smartlead.ai**. Designed for both local development and 24/7 cloud hosting (Docker, Render, Railway, Fly.io, AWS, VPS).

Built strictly with **Python 3.10+ standard libraries** (`sqlite3`, `smtplib`, `imaplib`, `http.server`, `threading`, `json`, `csv`, `ssl`) — **zero external pip dependencies**.

---

## 🌟 Key Features (Instantly.ai / Smartlead Clone)

- 📊 **Analytics Overview**: Real-time KPI metrics (Total Prospects, Contacted %, Follow-up count, Replies, High Intent Opportunities, 99.4% Deliverability Health), dynamic SVG Outreach Volume & Velocity chart, and 5-stage conversion pipeline funnel.
- 🚀 **Campaigns Manager**: Multi-step drip campaign orchestration, sequence summaries, delay indicators, and pipeline activity tracking.
- 📬 **3-Pane Master Unibox**:
  - **Category Folders**: All Inboxes, Interested 🔥, Meeting Booked 📅, Out of Office 🏖️, Not Interested ❌, and Unlabeled.
  - **Thread List**: Searchable thread cards with contact avatars, company tags, and snippet previews.
  - **Conversation Reader & Inline Reply Composer**: View full email thread history and dispatch manual replies in-thread directly via SMTP!
- 👥 **Leads Database**: Filterable prospect table (`Pending`, `Step 1 Sent`, `Step 2 Sent`, `Replied`, `Snoozed`), search box, single prospect creation, and CSV export.
- 📥 **Drag-and-Drop CSV Importer**: Upload prospect lists with automatic header mapping (`email`, `first_name`, `company`, `custom_hook`).
- 📧 **Email Accounts & Warmup**: Mailbox rotation with warmup health scores (98%+), daily quota progress bars (`sent / limit`), live SMTP/IMAP connection tester, and provider presets (Google Workspace, Microsoft 365, Custom SMTP/IMAP).
- ⚡ **Visual Sequence Builder**: Multi-step editor for Step 1 Initial Outreach and Step 2 Threaded Follow-up, variable inserter chips (`{{first_name}}`, `{{company}}`, `{{custom_hook}}`), delay nodes ("Wait 3 Days"), and a **live side-by-side prospect preview pane**.
- ⚙️ **Delivery Pacing & Anti-Spam Jitter**: Configurable minimum/maximum sleep intervals between sends, follow-up delays, and automatic IMAP poll frequency.
- 🔒 **Cloud Security**: Optional HTTP Basic Authentication (`DASHBOARD_USERNAME` & `DASHBOARD_PASSWORD`) for public internet deployments.
- 🌐 **Cloud-Ready Storage**: Dynamic `$PORT` binding and persistent storage volume support via `$DATA_DIR`.

---

## 💻 Local Execution

Run locally with standard Python (no `pip install` required):
```bash
python outreach_engine.py
```
Open **`http://localhost:8080`** in your browser.

---

## 🚀 Cloud Deployment Options

### Option 1: Deploy on Render (Recommended)
1. Push this directory to a GitHub repository.
2. In [Render Dashboard](https://dashboard.render.com/):
   - Click **New** -> **Web Service**.
   - Connect your GitHub repository.
   - Select **Docker** as the Environment.
3. Under **Advanced**:
   - Add a **Persistent Disk**: Mount path `/data` (Size: 1GB).
   - Set Environment Variables:
     - `DATA_DIR` = `/data`
     - `DASHBOARD_USERNAME` = `admin`
     - `DASHBOARD_PASSWORD` = `YourStrongSecretPassword`
4. Click **Create Web Service**. Your cloud dashboard will be live at `https://your-service.onrender.com`.

---

### Option 2: Deploy on Railway
1. Push this directory to GitHub.
2. Go to [Railway](https://railway.app/) -> **New Project** -> **Deploy from GitHub repo**.
3. Railway will automatically detect the `Dockerfile`.
4. Add a Persistent Volume mounted at `/data`.
5. Set variables:
   - `DATA_DIR` = `/data`
   - `DASHBOARD_USERNAME` = `admin`
   - `DASHBOARD_PASSWORD` = `YourStrongPassword`
6. Click **Deploy**. Generate a public domain under Settings -> Networking.

---

### Option 3: Deploy via Docker Compose (VPS / Ubuntu / Debian)
```bash
docker compose up -d
```
Open `http://your-server-ip:8080`.
