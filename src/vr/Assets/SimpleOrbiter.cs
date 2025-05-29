using UnityEngine;

public class SimpleOrbiter : MonoBehaviour
{
  [Header("Orbit target")]
  public Transform target; // object to circle (e.g. XR camera)

  [Header("Orbit parameters")]
  public float orbitRadius = 1.5f; // metres
  public float orbitSpeedDeg = 30f; // degrees per second
  public bool faceCamera = false; // look-at target (optional)

  [Header("Self-rotation (spin)")]
  public Vector3 spinAxis = Vector3.up; // local axis
  public float spinSpeedDeg = 45f; // deg/s (0 = none)

  // internal
  private Vector3 startOffset;

  void Start()
  {
    if (target == null)
      target = Camera.main.transform; // fallback

    spinAxis.Normalize(); // ensure unit length

    // initial position on +Z
    startOffset = Vector3.forward * orbitRadius;
    transform.position = target.position + startOffset;
  }

  void Update()
  {
    // orbit around target
    transform.RotateAround(
        target.position,
        Vector3.up,
        orbitSpeedDeg * Time.deltaTime);

    // self-spin
    if (spinSpeedDeg != 0f)
    {
      transform.Rotate(
          spinAxis,
          spinSpeedDeg * Time.deltaTime,
          Space.Self);
    }

    // optional look-at
    if (faceCamera)
      transform.LookAt(target);
  }
}
