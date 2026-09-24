# Benchmark Case Manifest

| Case | File | Modality | Required role | Ground-truth access |
|---|---|---|---|---|
| T-01 | `text/case_text_01.txt` | Text/log | Instructor Test A | Validate directly from numbered/source lines and conventional text tools |
| I-01 | `image/case_image_01.png` | Image | Instructor Test A | Validate visible content manually and with conventional metadata/OCR tools |
| A-01 | `audio/case_audio_01.wav` | Audio | Instructor Test A | Produce and manually verify a timestamped transcript |
| V-01 | `video/case_video_01.mp4` | Video | Instructor Test A | Verify by playback, frame extraction, and separate audio inspection |

All files are fictional synthetic teaching materials. The image was generated
with an AI image generator. The text was authored for the course. The audio was
synthesized from a fictional script. The video is a deterministic animation.
No real person, organization, credential, incident, or operational address is
represented. The files may be used for this course; do not present them as
authentic forensic evidence.

Verify every distributed file against `SHA256SUMS.txt` before analysis. If a
file is transformed, hash the derived file and document the tool, version,
command/settings, input hash, output hash, and purpose.
