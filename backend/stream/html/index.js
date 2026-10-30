const { search, origin } = window.location;
const params = new URLSearchParams(search);
const token = params.get("token");
const streamURL = `${origin}/hls/${token}.m3u8`;

const video = document.getElementById("live-stream");
const playVideo = () => video.play();
const useHls = Hls.isSupported();
let hls;

const baseDelay = 5_000;
let retryDelay = baseDelay;
const startStream = () => {
    console.log("Retrying...");
    if (useHls) {
        if (hls) hls.destroy();

        hls = new Hls({
            backBufferLength: 15,
            maxBufferSize: 15 * 1024 * 1024,
            maxBufferLength: 15,
            enableWorker: false,
        });
        hls.loadSource(streamURL);
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
            retryDelay = baseDelay;
            video.play();
        });
        hls.on(Hls.Events.ERROR, (_, _) => {
            hls.destroy();
            retryDelay = Math.min(retryDelay * 2, 60_000);
            setTimeout(startStream, retryDelay);
        });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = streamURL;

        video.addEventListener("canplay", playVideo);
        video.onerror = () => {
            video.removeEventListener("canplay", playVideo);
            setTimeout(startStream, retryDelay);
        };
    }
};
startStream();