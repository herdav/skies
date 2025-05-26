using UnityEngine;
using UnityEngine.Video;
using System.IO;

public class VideoLoader : MonoBehaviour
{
    public VideoPlayer videoPlayer;

    void Start()
    {
        string videoPath = Path.Combine(Application.streamingAssetsPath, "skies.mp4");

#if UNITY_ANDROID && !UNITY_EDITOR
        // On Android, Application.streamingAssetsPath is already a valid URL
        videoPlayer.url = videoPath;
#else
        // In the Editor (and on other platforms), prepend file:// to the path
        videoPlayer.url = "file://" + videoPath;
#endif

        videoPlayer.source = VideoSource.Url;
        videoPlayer.isLooping = true;
        videoPlayer.prepareCompleted += vp => {
            Debug.Log("Video is prepared. Starting playback...");
            videoPlayer.Play();
        };

        Debug.Log("Loading video from: " + videoPlayer.url);
        videoPlayer.Prepare();
    }
}
