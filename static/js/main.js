function unlockAudio() {
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
document.body.addEventListener('click', unlockAudio);

function playNotificationSound() {
    const sound = document.getElementById('notification-sound');
    if (sound) {
        sound.play().catch(error => console.error("Notification sound failed to play:", error));
    }
}