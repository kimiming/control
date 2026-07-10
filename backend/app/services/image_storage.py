from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_SIDE = 960
JPEG_QUALITY = 45


async def save_compressed_image(upload: UploadFile, directory: str) -> str:
    data = await upload.read()
    try:
        image = Image.open(BytesIO(data))
    except UnidentifiedImageError as exc:
        raise ValueError("Invalid image file") from exc

    image.load()
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)

    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.convert("RGBA").getchannel("A")
        background.paste(image.convert("RGBA"), mask=alpha)
        image = background
    else:
        image = image.convert("RGB")

    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{uuid4().hex}.jpg"
    image.save(
        file_path,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )
    return "/" + str(file_path)
