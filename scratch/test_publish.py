"""Test publishing a single post from the out/ folder to GCS + Instagram.

Usage:
    .venv/Scripts/python scratch/test_publish.py
"""
import io
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from PIL import Image
from google.cloud import storage
import requests

from app.config import config

# ------------------------------------------------------------------ #
# Image helpers
# ------------------------------------------------------------------ #
_INSTAGRAM_MAX_RATIO = 4 / 5   # portrait limit (width/height = 0.8)

def prepare_image(png_path: Path) -> bytes:
    """Convert PNG to JPEG and center-crop to Instagram's 4:5 portrait limit."""
    img = Image.open(png_path).convert("RGB")
    w, h = img.size
    # If taller than 4:5, center-crop height
    max_h = int(w / _INSTAGRAM_MAX_RATIO)
    if h > max_h:
        top = (h - max_h) // 2
        img = img.crop((0, top, w, top + max_h))
        print(f"  cropped {w}x{h} → {w}x{max_h}")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def upload_jpeg(jpeg_bytes: bytes, bucket_name: str, blob_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(jpeg_bytes, content_type="image/jpeg")
    blob.make_public()
    return blob.public_url


def post_to_instagram(ig_user_id: str, token: str, image_url: str, caption: str) -> str:
    from app.tools.instagram import post_to_instagram as _post
    return _post(ig_user_id, token, image_url, caption)


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #
def main():
    # Find most recent manifest
    manifests = sorted(Path("out").glob("*_posts.json"), reverse=True)
    if not manifests:
        print("No manifest found in out/. Run the pipeline first.")
        return
    manifest = manifests[0]
    print(f"Using manifest: {manifest}")

    posts = json.loads(manifest.read_text(encoding="utf-8"))
    if not posts:
        print("Manifest is empty.")
        return

    # Credentials
    bucket = config.gcs_bucket_name()
    ig_user_id = config.instagram_user_id()
    ig_token = config.instagram_access_token()

    success = 0
    for i, post in enumerate(posts, 1):
        idea_id = post["idea_id"]
        image_path = Path(post["image_path"])
        caption = post["caption"]
        print(f"\n[{i}/{len(posts)}] {idea_id[:16]}...")
        print(f"  Caption: {caption[:80]}...")
        try:
            jpeg_bytes = prepare_image(image_path)
            blob_name = f"posts/{idea_id}/image.jpg"
            public_url = upload_jpeg(jpeg_bytes, bucket, blob_name)
            print(f"  GCS: {public_url}")
            media_id = post_to_instagram(ig_user_id, ig_token, public_url, caption)
            print(f"  Instagram media_id: {media_id}")
            success += 1
        except Exception as e:
            print(f"  FAILED: {e}")

    print(f"\nDone. {success}/{len(posts)} published.")


if __name__ == "__main__":
    main()
