"""Instagram Graph API — create and publish a single image post."""
import time
import requests

_GRAPH_API_BASE = "https://graph.facebook.com/v25.0"
_TIMEOUT = 60
# Instagram needs time to fetch and process the image after container creation.
# Poll status up to this many times with this sleep between each check.
_STATUS_POLL_INTERVAL_S = 5
_STATUS_POLL_MAX_ATTEMPTS = 24  # up to 120s total wait


def post_to_instagram(
    ig_user_id: str,
    access_token: str,
    image_url: str,
    caption: str,
) -> str:
    """Create an Instagram image post and return the published media ID.

    Requires a token with instagram_basic and instagram_content_publish permissions.
    The image_url must be publicly accessible when Instagram fetches it.
    """
    # Step 1 — create media container
    resp = requests.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media",
        params={
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=_TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError(f"media container creation failed {resp.status_code}: {resp.text}")
    container_id = resp.json()["id"]

    # Step 2 — wait for container status = FINISHED
    for attempt in range(1, _STATUS_POLL_MAX_ATTEMPTS + 1):
        time.sleep(_STATUS_POLL_INTERVAL_S)
        status_resp = requests.get(
            f"{_GRAPH_API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=_TIMEOUT,
        )
        if not status_resp.ok:
            continue
        status = status_resp.json().get("status_code", "")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError(f"container {container_id} processing failed (status=ERROR)")
    else:
        raise RuntimeError(f"container {container_id} not ready after {_STATUS_POLL_MAX_ATTEMPTS} polls")

    # Step 3 — publish
    resp = requests.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media_publish",
        params={
            "creation_id": container_id,
            "access_token": access_token,
        },
        timeout=_TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError(f"media_publish failed {resp.status_code}: {resp.text}")
    return resp.json()["id"]
