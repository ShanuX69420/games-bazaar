// This function's only job is to get the browser's permission to play audio.
function unlockAudio() {
    const sound = document.getElementById('notification-sound');
    if (sound) {
        sound.muted = true; // We play it muted to unlock it.
        sound.play().then(() => {
            sound.pause();
            sound.currentTime = 0;
            sound.muted = false; // Unmute it for later.
            console.log("✅ Audio permissions granted.");
            // We remove the listener so this only ever happens once.
            document.body.removeEventListener('click', unlockAudio);
        }).catch(error => {
            console.error("Audio unlock failed:", error);
        });
    }
}

// Listen for the very first click on the page to run the unlock function.
document.body.addEventListener('click', unlockAudio);

// This function will be called by our other script when a notification actually comes in.
function playNotificationSound() {
    const sound = document.getElementById('notification-sound');
    if (sound) {
        sound.play().catch(error => console.error("Notification sound failed to play:", error));
    }
}