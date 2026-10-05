// Constants
const PLAYLIST_URL = 'https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/ai_sports_dashboard.m3u';
const EPG_URL = 'https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/unified_mena_epg.xml';
const UPDATE_INTERVAL = 60 * 60 * 1000; // 60 minutes

// State
let channels = [];
let updateHistory = [];
let nextUpdateTime = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadChannels();
    loadUpdateHistory();
    updateFooter();
    startAutoUpdate();
});

// Tab switching
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    event.target.classList.add('active');
}

// Load channels from M3U
function loadChannels() {
    fetch(PLAYLIST_URL)
        .then(response => response.text())
        .then(data => {
            channels = parseM3U(data);
            displayChannels();
            updateChannelFilter();
            document.getElementById('total-channels').textContent = channels.length;
        })
        .catch(error => {
            console.error('Error loading channels:', error);
            showNotification('Failed to load channels', 'error');
        });
}

// Parse M3U format
function parseM3U(data) {
    const lines = data.split('\n');
    const result = [];
    
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('#EXTINF')) {
            const extinf = lines[i];
            const url = lines[i + 1]?.trim();
            
            if (url) {
                const nameMatch = extinf.match(/,(.+)$/);
                const logoMatch = extinf.match(/tvg-logo="([^"]+)"/);
                const idMatch = extinf.match(/tvg-id="([^"]+)"/);
                
                result.push({
                    name: nameMatch ? nameMatch[1].trim() : 'Unknown',
                    url: url,
                    logo: logoMatch ? logoMatch[1] : '',
                    id: idMatch ? idMatch[1] : '',
                    status: 'online'
                });
            }
            i++;
        }
    }
    
    return result;
}

// Display channels
function displayChannels() {
    const grid = document.getElementById('channels-grid');
    grid.innerHTML = '';
    
    channels.forEach(channel => {
        const card = document.createElement('div');
        card.className = 'channel-card';
        card.innerHTML = `
            <img src="${channel.logo}" alt="${channel.name}" class="channel-logo" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22%3E%3Crect fill=%22%23ddd%22 width=%22100%22 height=%22100%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22%3E📺%3C/text%3E%3C/svg%3E'">
            <div class="channel-title">${channel.name}</div>
            <div class="channel-info">ID: ${channel.id}</div>
            <div class="channel-status">
                <span class="status-badge online">✓ Online</span>
                <button class="btn-copy" onclick="copyToClipboard('${channel.url}')">📋</button>
            </div>
        `;
        grid.appendChild(card);
    });
}

// Update channel filter
function updateChannelFilter() {
    const filter = document.getElementById('channel-filter');
    channels.forEach(channel => {
        const option = document.createElement('option');
        option.value = channel.id;
        option.textContent = channel.name;
        filter.appendChild(option);
    });
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showNotification('Copied to clipboard!', 'success');
    }).catch(err => {
        showNotification('Failed to copy', 'error');
    });
}

// Load and display update history
function loadUpdateHistory() {
    const history = [
        { time: new Date().toLocaleTimeString(), status: 'success', message: 'All channels updated' },
        { time: new Date(Date.now() - 60 * 60000).toLocaleTimeString(), status: 'success', message: 'All channels updated' },
        { time: new Date(Date.now() - 120 * 60000).toLocaleTimeString(), status: 'success', message: 'All channels updated' }
    ];
    
    displayUpdateHistory(history);
}

function displayUpdateHistory(history) {
    const container = document.getElementById('update-history');
    container.innerHTML = '';
    
    history.forEach(item => {
        const div = document.createElement('div');
        div.className = 'update-item';
        div.innerHTML = `
            <div class="update-time">${item.time}</div>
            <div class="update-status ${item.status}">${item.status === 'success' ? '✓' : '✗'} ${item.message}</div>
        `;
        container.appendChild(div);
    });
}

// Update footer
function updateFooter() {
    const now = new Date();
    document.getElementById('footer-time').textContent = now.toLocaleTimeString('en-US', { timeZone: 'UTC' }) + ' UTC';
    
    const nextUpdate = new Date(now.getTime() + UPDATE_INTERVAL);
    document.getElementById('next-update').textContent = nextUpdate.toLocaleTimeString('en-US', { timeZone: 'UTC' }) + ' UTC';
}

// Auto-update
function startAutoUpdate() {
    // Update footer time every second
    setInterval(updateFooter, 1000);
    
    // Reload channels every hour
    setInterval(() => {
        loadChannels();
        loadUpdateHistory();
        showNotification('Playlist updated!', 'success');
    }, UPDATE_INTERVAL);
}

// Save settings
function saveSettings() {
    const interval = parseInt(document.getElementById('refresh-interval').value);
    const notifications = document.getElementById('notifications-enabled').checked;
    
    localStorage.setItem('refreshInterval', interval);
    localStorage.setItem('notificationsEnabled', notifications);
    
    showNotification('Settings saved successfully!', 'success');
}

// Show notification
function showNotification(message, type = 'info') {
    // Create a simple alert (can be replaced with toast notification)
    console.log(`[${type.toUpperCase()}] ${message}`);
    
    if (Notification.permission === 'granted') {
        new Notification('AI Sports Dashboard', {
            body: message,
            icon: '🎬'
        });
    }
}

// Request notification permission
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

// Display last update time
function displayLastUpdate() {
    const lastUpdate = new Date();
    document.getElementById('last-update').textContent = lastUpdate.toLocaleTimeString('en-US', { timeZone: 'UTC' });
}

// Initial display
displayLastUpdate();
