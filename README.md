# Microsoft Rewards Gift Card Stock Tracker 🎁⚡

Automated real-time stock tracker with **WhatsApp & Telegram** notifications for **Microsoft Rewards (`rewards.bing.com`)**.

Specifically built to monitor high-demand shopping vouchers in India:
- **Flipkart Gift Cards** (catches restocks when they stop showing *"So popular we are restocking back soon"*)
- **Amazon Pay Gift Cards**
- **Croma Gift Cards**
- **Any Major Shopping / Retail Vouchers** (Myntra, Swiggy, Zomato, BookMyShow, Lifestyle, Reliance)

---

## ⚡ Two Ways to Run

### Method 1: Local Background Daemon on Your Laptop
* While your laptop is **ON** (working, gaming, or screen locked):
  - Run [`start_background.vbs`](file:///d:/Ideas/ms-rewards-tracker/start_background.vbs) &rarr; Runs completely silently with zero open windows.
  - Run [`install_autostart.bat`](file:///d:/Ideas/ms-rewards-tracker/install_autostart.bat) &rarr; Automatically launches whenever you turn on your PC.

### Method 2: 24/7 Cloud Monitoring (Runs Even When Laptop is Powered Off / Shut Down)
* When your laptop is **turned off, asleep, or you are traveling**:
  - A local computer has no power or Wi-Fi when shut down.
  - To monitor 24/7 continuously, use the included **GitHub Actions Cloud Runner** ([`.github/workflows/rewards_tracker.yml`](file:///d:/Ideas/ms-rewards-tracker/.github/workflows/rewards_tracker.yml) & [`cloud_tracker.py`](file:///d:/Ideas/ms-rewards-tracker/cloud_tracker.py)).
  - Runs in the cloud every 5 minutes automatically, 100% free, and alerts your phone on WhatsApp and Telegram!

---

## ☁️ Setting Up 24/7 Cloud Tracking (When Laptop is Off)

Just like in your Amul tracker:
1. Create a new **Private Repository** on your GitHub account (e.g. `ms-rewards-tracker`).
2. Push this folder to GitHub:
   ```bash
   git add .
   git commit -m "Add MS Rewards 24/7 Tracker"
   git remote add origin https://github.com/<YOUR_USERNAME>/ms-rewards-tracker.git
   git branch -M main
   git push -u origin main
   ```
3. In your GitHub repository, go to **Settings &rarr; Secrets and variables &rarr; Actions &rarr; New repository secret**:
   - `MS_COOKIE`: Your Microsoft Rewards cookie.
   - `TELEGRAM_BOT_TOKEN`: Your Telegram Bot token from @BotFather.
   - `TELEGRAM_CHAT_ID`: Your Telegram Chat ID from @userinfobot.
   - `GREEN_API_INSTANCE_ID`: Your Green-API instance (optional).
   - `GREEN_API_TOKEN_INSTANCE`: Your Green-API token (optional).
   - `WHATSAPP_PHONE`: Your WhatsApp phone number (optional).
   - `CALLMEBOT_API_KEY`: Your CallMeBot API key (optional).
4. Go to the **Actions** tab on GitHub &rarr; click **"Microsoft Rewards 24/7 Restock Tracker"** &rarr; click **Run workflow**.
5. It will now run **every 5 minutes 24/7** in the cloud. Your laptop can be completely off!

---

## 💻 Local Quick Start (Web Dashboard)

1. Launch via [`run.bat`](file:///d:/Ideas/ms-rewards-tracker/run.bat) or:
   ```bash
   python app.py
   ```
   Opens **`http://localhost:5001`**.
2. **Connect Session Cookie**:
   - Open [rewards.bing.com/redeem](https://rewards.bing.com/redeem/) in Edge/Chrome.
   - Press `F12` &rarr; Network tab &rarr; Refresh &rarr; Right click first `redeem` request &rarr; Copy request headers.
   - Paste into Settings &rarr; MS Session.
3. Configure Telegram Bot Token & Chat ID (or WhatsApp).
4. Click **"Test WhatsApp & Telegram"** at the top to test your alert!

---

## 🛠️ Local Control Scripts

- **Silent Background Run:** Double-click [`start_background.vbs`](file:///d:/Ideas/ms-rewards-tracker/start_background.vbs)
- **Stop Tracker:** Double-click [`stop_tracker.bat`](file:///d:/Ideas/ms-rewards-tracker/stop_tracker.bat)
- **Auto-Start on Boot:** Double-click [`install_autostart.bat`](file:///d:/Ideas/ms-rewards-tracker/install_autostart.bat)
