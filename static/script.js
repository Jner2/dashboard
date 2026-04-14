document.addEventListener('DOMContentLoaded', () => {
    const sideMenu = document.querySelector("aside");
    const menuBtn = document.querySelector("#menu-btn");
    const closeBtn = document.querySelector("#close-btn");
    const themeToggler = document.querySelector(".theme-toggler");
    const imageInput = document.getElementById('imageInput');

    // --- 1. SIDEBAR TOGGLE LOGIC ---
    if (menuBtn && sideMenu) {
        menuBtn.addEventListener('click', () => {
            sideMenu.style.display = 'block';
        });
    }

    if (closeBtn && sideMenu) {
        closeBtn.addEventListener('click', () => {
            sideMenu.style.display = 'none';
        });
    }

    // --- 2. DARK MODE LOGIC ---
    if (themeToggler) {
        themeToggler.addEventListener('click', () => {
            document.body.classList.toggle('dark-theme-variables');
            themeToggler.querySelector('span:nth-child(1)').classList.toggle('active');
            themeToggler.querySelector('span:nth-child(2)').classList.toggle('active');
            
            const isDark = document.body.classList.contains('dark-theme-variables');
            localStorage.setItem('darkMode', isDark);
        });
    }

    if (localStorage.getItem('darkMode') === 'true') {
        document.body.classList.add('dark-theme-variables');
        if (themeToggler) {
            themeToggler.querySelector('span:nth-child(1)').classList.remove('active');
            themeToggler.querySelector('span:nth-child(2)').classList.add('active');
        }
    }

    // --- 3. IMAGE UPLOAD TRIGGER ---
    if (imageInput) {
        imageInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                uploadImage(file);
            }
        });
    }

    // --- 4. LIVE DATA REFRESH ---
    fetchFloodData(); // Initial call
    setInterval(fetchFloodData, 3000); // Refresh every 3 seconds
});

// Global state to prevent the 3-second loop from overwriting manual uploads
let isPaused = false;

// Function to send image to Flask
function uploadImage(file) {
    const formData = new FormData();
    formData.append('image', file);

    const statusText = document.getElementById('upload-status-text');
    const timeText = document.getElementById('upload-time');
    
    if (statusText) statusText.innerText = "Analyzing...";
    
    // Pause the live sensor loop
    isPaused = true;

    fetch('http://127.0.0.1:5000/api/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (statusText) statusText.innerText = "Result: " + data.result;
        if (timeText) timeText.innerText = "Confidence: " + data.confidence;

        // Keep the result on screen for 10 seconds, then resume live feed
        setTimeout(() => {
            if (statusText) statusText.innerText = "Click to Analyze";
            if (timeText) timeText.innerText = "Manual Check";
            isPaused = false;
        }, 10000);
    })
    .catch(error => {
        console.error('Error:', error);
        if (statusText) statusText.innerText = "Upload Failed";
        isPaused = false;
    });
}

// Function to fetch live status from Python
function fetchFloodData() {
    // If we are showing an upload result, skip this update
    if (isPaused) return;

    fetch('http://raspberrypi.local:5000/api/flood-status')
        .then(response => response.json())
        .then(data => {
            const statusText = document.getElementById('flood-level-text');
            const confidenceText = document.getElementById('current-confidence');
            const updateText = document.getElementById('last-update');

            if (statusText) {
                statusText.innerText = data.status;
                statusText.className = ""; 
                const lowerStatus = data.status.toLowerCase();
                
                if (lowerStatus === 'normal') {
                    statusText.classList.add('status-normal');
                } else if (lowerStatus === 'warning' || lowerStatus === 'overflow') {
                    statusText.classList.add('status-overflow');
                } else if (lowerStatus === 'critical') {
                    statusText.classList.add('status-critical');
                }
            }

            if (confidenceText) {
                confidenceText.innerText = `Confidence: ${data.confidence}`;
            }

            if (updateText) {
                updateText.innerText = `Last Update: ${data.timestamp}`;
            }
        })
        .catch(err => {
            const statusText = document.getElementById('flood-level-text');
            if (statusText && statusText.innerText === "Detecting...") {
                statusText.innerText = "Offline";
            }
        });
}