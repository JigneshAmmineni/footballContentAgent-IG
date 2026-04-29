import os
from io import BytesIO

from PIL import Image

_MODEL = "imagen-3.0-generate-002"
_ASPECT = "1:1"


def generate_imagen(prompt: str, size: tuple[int, int] = (1080, 1080)) -> Image.Image:
    """Generate an image via Gemini Imagen 3 and return as PIL Image.
    Falls back to a programmatic dark background if the API call fails.
    """
    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client()
        response = client.models.generate_images(
            model=_MODEL,
            prompt=prompt,
            config=genai_types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=_ASPECT,
            ),
        )
        if response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            return img.resize(size, Image.LANCZOS)
    except Exception:
        pass
    return _dark_fallback(size)


def _dark_fallback(size: tuple[int, int]) -> Image.Image:
    """Plain dark background used when Imagen is unavailable."""
    return Image.new("RGB", size, (18, 18, 28))
