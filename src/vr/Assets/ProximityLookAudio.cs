using UnityEngine;

[RequireComponent(typeof(AudioSource))]
public class ProximityLookAudio : MonoBehaviour
{
  [Header("References")]
  public Transform listener; // XR camera (CenterEyeAnchor)

  [Header("Distance fading")]
  public float maxDistance = 55f; // distance where distFactor = 0
  public float minDistance = 1.5f; // distance where distFactor = 1
  [Range(0f, 1f)]
  public float minVolAtMaxDistance = 0.2f; // volume floor at maxDistance

  [Header("Look boosting")]
  public float lookThreshold = 0.6f; // dot threshold (0..1)
  public float lookMin = 0.6f; // multiplier when not looked at
  public float lookMax = 1.2f; // multiplier when centered

  [Header("Master")]
  public float baseVolume = 1f; // overall ceiling

  private AudioSource src;

  void Awake()
  {
    src = GetComponent<AudioSource>();
    src.loop = true;
    src.spatialBlend = 1f; // 3D
    src.Play();

    if (listener == null)
      listener = Camera.main.transform;
  }

  void Update()
  {
    if (!listener) return;

    // distance factor mapped to 0..1
    float dist = Vector3.Distance(transform.position, listener.position);
    float dist01 = Mathf.InverseLerp(maxDistance, minDistance, dist);
    dist01 = Mathf.Clamp01(dist01);

    // interpolate between floor volume and full (1)
    float distFactor = Mathf.Lerp(minVolAtMaxDistance, 1f, dist01);

    // look multiplier
    Vector3 toObj = (transform.position - listener.position).normalized;
    float dot = Vector3.Dot(listener.forward, toObj);

    float lookMul = dot > lookThreshold
                    ? Mathf.Lerp(lookMin, lookMax,
                                 Mathf.InverseLerp(lookThreshold, 1f, dot))
                    : lookMin;

    // final volume
    src.volume = baseVolume * distFactor * lookMul;
  }
}
