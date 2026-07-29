const alarm = document.getElementById("alarm");
const status = document.getElementById("status");
const enableButton = document.getElementById("enableAudio");

let audioEnabled = false;
let alarmPlaying = false;

// Browser requires a user click before audio can play
enableButton.addEventListener("click", () => {
    audioEnabled = true;

    alarm.play().then(() => {
        alarm.pause();
        alarm.currentTime = 0;
    });

    alert("Audio enabled.");
});

// Check the backend every 5 seconds
setInterval(checkGemma, 5000);

// Also check once when the page loads
checkGemma();

async function checkGemma() {
    try {
        const response = await fetch("/api/gemma");
        const data = await response.json();

        if (data.alert === "yes") {

            status.innerHTML = "ALERT";

            if (audioEnabled && !alarmPlaying) {
                alarm.loop = true;
                await alarm.play();
                alarmPlaying = true;
            }

        } else {

            status.innerHTML = "Normal";

            if (alarmPlaying) {
                alarm.pause();
                alarm.currentTime = 0;
                alarmPlaying = false;
            }
        }

    } catch (error) {
        console.error(error);
        status.innerHTML = "Unable to contact API";
    }
}