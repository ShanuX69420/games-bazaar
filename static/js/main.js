function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

function unlockAudio() {
    // Skip audio unlock on mobile devices
    if (isMobileDevice()) {
        console.log("Audio disabled on mobile device");
        document.body.removeEventListener('click', unlockAudio);
        return;
    }
    
    const sound = document.getElementById('notification-sound');
    if (sound) {
        sound.muted = true;
        sound.play().then(() => {
            sound.pause();
            sound.currentTime = 0;
            sound.muted = false;
            console.log("✅ Audio permissions granted.");
            document.body.removeEventListener('click', unlockAudio);
        }).catch(error => {
            console.error("Audio unlock failed:", error);
        });
    }
}
// Only add audio unlock listener on desktop devices
if (!isMobileDevice()) {
    document.body.addEventListener('click', unlockAudio);
}

function playNotificationSound() {
    // Skip notification sounds on mobile devices
    if (isMobileDevice()) {
        console.log("Notification sound skipped on mobile");
        return;
    }
    
    const sound = document.getElementById('notification-sound');
    if (sound) {
        sound.play().catch(error => console.error("Notification sound failed to play:", error));
    }
}