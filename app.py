from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import scraper
import os
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import json
from pywebpush import webpush, WebPushException

app = Flask(__name__, static_folder='frontend/dist', template_folder='frontend/dist')
CORS(app) # Enable CORS for cross-origin mobile access

# Configuration
PORT = int(os.environ.get("PORT", 5000))
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY")
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "mailto:admin@example.com")

# Global variables to track state
scraping_active = False
last_results = []
last_csv_path = "liste_annonces_v2.csv" # Fixed path for persistence

# Load VAPID keys from file if not in environment
if not VAPID_PRIVATE_KEY and os.path.exists("vapid_keys.json"):
    with open("vapid_keys.json", "r") as f:
        keys = json.load(f)
        VAPID_PRIVATE_KEY = keys.get("private_key")
        VAPID_PUBLIC_KEY = keys.get("public_key")

# Subscriptions storage
SUBSCRIPTIONS_FILE = "subscriptions.json"

def get_subscriptions():
    if os.path.exists(SUBSCRIPTIONS_FILE):
        try:
            with open(SUBSCRIPTIONS_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_subscription(sub):
    subs = get_subscriptions()
    if sub not in subs:
        subs.append(sub)
        with open(SUBSCRIPTIONS_FILE, "w") as f:
            json.dump(subs, f)

def send_notification(title, body):
    if not VAPID_PRIVATE_KEY:
        print("VAPID_PRIVATE_KEY not set, skipping notification")
        return
        
    subs = get_subscriptions()
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_EMAIL}
            )
        except WebPushException as ex:
            print(f"Notification error for {sub.get('endpoint')}: {ex}")
        except Exception as e:
            print(f"Unexpected notification error: {e}")

def perform_scrape(keyword='minibus', avito_url='https://www.avito.ma/fr/maroc/fourgon_et_minibus'):
    global scraping_active, last_results, last_csv_path
    if scraping_active:
        return
        
    scraping_active = True
    try:
        results, csv_path = scraper.run_full_scrape(keyword, avito_url)
        last_results = results
        # Ensure results are persistent
        if results:
            send_notification("Scraping Terminé", f"J'ai trouvé {len(results)} minibus pour vous !")
    except Exception as e:
        print(f"Scraping error: {e}")
        send_notification("Erreur Scraping", f"Une erreur est survenue : {str(e)[:50]}")
    finally:
        scraping_active = False

# Setup APScheduler
scheduler = BackgroundScheduler()
# Run daily at 20:00 (8 PM)
scheduler.add_job(func=perform_scrape, id='daily_scrape', trigger="cron", hour=20, minute=0, replace_existing=True)
scheduler.start()

@app.route('/')
def index():
    if os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return send_from_directory(app.static_folder, 'index.html')
    return "Frontend non trouvé. Veuillez lancer 'npm run build' dans le dossier frontend.", 404

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/scrape', methods=['POST'])
def run_scrape():
    if scraping_active:
        return jsonify({"status": "error", "message": "Scrape already in progress"}), 400
    
    data = request.json or {}
    keyword = data.get('keyword', 'minibus')
    avito_url = data.get('avito_url', 'https://www.avito.ma/fr/maroc/fourgon_et_minibus')
    
    thread = threading.Thread(target=perform_scrape, args=(keyword, avito_url))
    thread.start()
    return jsonify({"status": "started"})

@app.route('/status')
def status():
    # Try to reload last results from CSV if memory is empty (e.g. after server restart)
    global last_results
    if not last_results and os.path.exists(last_csv_path):
        import pandas as pd
        try:
            df = pd.read_csv(last_csv_path)
            last_results = df.to_dict('records')
        except:
            pass

    return jsonify({
        "active": scraping_active,
        "count": len(last_results),
        "results": last_results
    })

@app.route('/vapid-public-key')
def get_public_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})

@app.route('/subscribe', methods=['POST'])
def subscribe():
    save_subscription(request.json)
    return jsonify({"status": "success"})

@app.route('/download')
def download():
    if os.path.exists(last_csv_path):
        return send_file(last_csv_path, as_attachment=True)
    return "Aucun fichier disponible", 404

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False)
    finally:
        scheduler.shutdown()
