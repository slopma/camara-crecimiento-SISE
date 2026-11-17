const { search, origin } = window.location;
const params = new URLSearchParams(search);
const token = params.get("token") || "m1";
const streamURL = `${origin}/hls/${token}.m3u8`;

const video = document.getElementById("live-stream");
const playVideo = () => video.play();
const useHls = Hls.isSupported();
let hls;

const baseDelay = 1_000;
let retryDelay = baseDelay;
const startStream = () => {
    if (useHls) {
        if (hls) hls.destroy();

        hls = new Hls({
            enableWorker: true,
            lowLatencyMode: true,
            liveSyncDurationCount: 1,
            liveMaxLatencyDurationCount: 2,
            maxBufferLength: 2,
            maxMaxBufferLength: 3,
            liveDurationInfinity: true,
            backBufferLength: 0
        });
        hls.loadSource(streamURL);
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
            retryDelay = baseDelay;
            video.play().catch(e => console.log('Autoplay:', e));
        });
        hls.on(Hls.Events.ERROR, (_, data) => {
            if (data.fatal) {
                hls.destroy();
                setTimeout(startStream, 1500);
            }
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
