"""GCS upload helper for generated post images."""
import io
from pathlib import Path

from google.cloud import storage
from PIL import Image

# Instagram feed posts require 4:5 max portrait ratio (width/height).
# gpt-image-2 outputs 1024x1536 (2:3), which exceeds this — center-crop before upload.
_INSTAGRAM_MAX_RATIO = 4 / 5


def upload_image(local_path: Path, bucket_name: str, blob_name: str) -> str:
    """Convert PNG to JPEG, crop to Instagram's 4:5 portrait limit, upload to GCS.

    Returns the public HTTPS URL.

    Requires: bucket must use fine-grained access control (not uniform bucket-level).
    """
    img = Image.open(local_path).convert("RGB")
    w, h = img.size
    max_h = int(w / _INSTAGRAM_MAX_RATIO)
    if h > max_h:
        top = (h - max_h) // 2
        img = img.crop((0, top, w, top + max_h))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    jpeg_bytes = buf.getvalue()

    # Use .jpg extension in blob name regardless of what was passed in
    blob_name = str(blob_name).rsplit(".", 1)[0] + ".jpg"

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(jpeg_bytes, content_type="image/jpeg")
    blob.make_public()
    return blob.public_url
