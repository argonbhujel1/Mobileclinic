"""
Image management: File Picker uploads + ImgBB URL import → Cloudinary → Turso metadata.
"""
import os
import logging
import requests
from io import BytesIO
from typing import Optional, Dict, Tuple
from flask import current_app
from werkzeug.datastructures import FileStorage
from app.utils.security import is_private_or_local_url, validate_image_content
from app import db

logger = logging.getLogger(__name__)


def _cloudinary_configured() -> bool:
    return bool(
        current_app.config.get("CLOUDINARY_CLOUD_NAME")
        and current_app.config.get("CLOUDINARY_API_KEY")
        and current_app.config.get("CLOUDINARY_API_SECRET")
    )


def _configure_cloudinary():
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=current_app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=current_app.config["CLOUDINARY_API_KEY"],
        api_secret=current_app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    return cloudinary


def _save_local(file: FileStorage, folder: str = "mobile-clinic") -> Dict:
    """Save image to static/uploads for local development without Cloudinary."""
    import uuid
    from werkzeug.utils import secure_filename

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    safe_folder = secure_filename(folder.replace("/", "_")) or "uploads"
    upload_dir = os.path.join(current_app.static_folder, "uploads", safe_folder)
    os.makedirs(upload_dir, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(upload_dir, name)
    file.seek(0)
    file.save(path)
    rel = f"uploads/{safe_folder}/{name}"
    url = f"/static/{rel}"
    size = os.path.getsize(path)
    logger.info("Saved image locally: %s", path)
    return {
        "url": url,
        "public_id": f"local/{safe_folder}/{name}",
        "width": None,
        "height": None,
        "format": ext,
        "bytes": size,
    }


def upload_file_to_cloudinary(
    file: FileStorage,
    folder: str = "mobile-clinic",
    public_id: Optional[str] = None,
) -> Optional[Dict]:
    """Upload a file from FileStorage to Cloudinary, or local static/uploads if Cloudinary is not configured."""
    if not file or not file.filename:
        return None
    if not validate_image_content(file):
        raise ValueError("Invalid image content")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ValueError(f"Extension .{ext} not allowed")

    if not _cloudinary_configured():
        logger.warning("Cloudinary not configured — using local upload fallback")
        return _save_local(file, folder=folder)

    try:
        _configure_cloudinary()
        import cloudinary.uploader
        file.seek(0)
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            public_id=public_id,
            resource_type="image",
            overwrite=True,
            quality="auto:good",
            fetch_format="auto",
        )
        return {
            "url": result.get("secure_url"),
            "public_id": result.get("public_id"),
            "width": result.get("width"),
            "height": result.get("height"),
            "format": result.get("format"),
            "bytes": result.get("bytes"),
        }
    except Exception as e:
        logger.error("Cloudinary upload failed: %s — falling back to local", e)
        try:
            file.seek(0)
            return _save_local(file, folder=folder)
        except Exception as e2:
            raise ValueError(f"Image upload failed: {str(e)}; local fallback also failed: {e2}")


def import_imgbb_url(url: str, folder: str = "mobile-clinic") -> Optional[Dict]:
    """Fetch image from ImgBB (or any direct image URL) with SSRF protection, then upload to Cloudinary (or local)."""
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("Invalid URL")
    if is_private_or_local_url(url):
        raise ValueError("URL points to a restricted address")

    try:
        resp = requests.get(
            url,
            timeout=10,
            stream=True,
            headers={"User-Agent": "MobileClinic/1.0"},
            allow_redirects=True,
        )
        if resp.history:
            for r in resp.history:
                if is_private_or_local_url(r.url):
                    raise ValueError("Redirect to restricted address blocked")
            if is_private_or_local_url(resp.url):
                raise ValueError("Final URL is restricted")

        content_type = resp.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            raise ValueError("URL does not point to an image")

        content = b""
        for chunk in resp.iter_content(8192):
            content += chunk
            if len(content) > 10 * 1024 * 1024:
                raise ValueError("Image too large (max 10 MB)")

        from io import BytesIO
        bio = BytesIO(content)

        class FakeFile:
            def read(self, n=-1):
                return bio.read(n)

            def seek(self, pos):
                bio.seek(pos)

            @property
            def filename(self):
                return "import.jpg"

        if not validate_image_content(FakeFile()):
            raise ValueError("Invalid image content from URL")

        if not _cloudinary_configured():
            # Local: save bytes to static/uploads
            import uuid
            from werkzeug.utils import secure_filename
            safe_folder = secure_filename(folder.replace("/", "_")) or "uploads"
            upload_dir = os.path.join(current_app.static_folder, "uploads", safe_folder)
            os.makedirs(upload_dir, exist_ok=True)
            name = f"{uuid.uuid4().hex}.jpg"
            path = os.path.join(upload_dir, name)
            with open(path, "wb") as f:
                f.write(content)
            return {
                "url": f"/static/uploads/{safe_folder}/{name}",
                "public_id": f"local/{safe_folder}/{name}",
                "width": None,
                "height": None,
                "format": "jpg",
                "bytes": len(content),
            }

        _configure_cloudinary()
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            BytesIO(content),
            folder=folder,
            resource_type="image",
            quality="auto:good",
            fetch_format="auto",
        )
        return {
            "url": result.get("secure_url"),
            "public_id": result.get("public_id"),
            "width": result.get("width"),
            "height": result.get("height"),
            "format": result.get("format"),
            "bytes": result.get("bytes"),
        }
    except requests.RequestException as e:
        logger.error("ImgBB/URL fetch failed: %s", e)
        raise ValueError(f"Failed to fetch image: {str(e)}")


def delete_cloudinary_image(public_id: str) -> bool:
    if not public_id:
        return False
    try:
        _configure_cloudinary()
        import cloudinary.uploader
        cloudinary.uploader.destroy(public_id)
        return True
    except Exception as e:
        logger.warning("Failed to delete Cloudinary image %s: %s", public_id, e)
        return False


def save_product_image(product_id: int, upload_result: Dict, display_order: int = 0, is_primary: bool = False):
    db.execute(
        """INSERT INTO product_images (product_id, cloudinary_url, cloudinary_public_id, display_order, is_primary)
           VALUES (?, ?, ?, ?, ?)""",
        (product_id, upload_result["url"], upload_result["public_id"], display_order, 1 if is_primary else 0),
    )


def save_profile_photo(user_id: int, upload_result: Dict):
    # Remove old if exists
    old = db.fetch_one("SELECT profile_photo_public_id FROM users WHERE id = ?", (user_id,))
    if old and old.get("profile_photo_public_id"):
        delete_cloudinary_image(old["profile_photo_public_id"])
    db.execute(
        "UPDATE users SET profile_photo_url = ?, profile_photo_public_id = ?, updated_at = datetime('now') WHERE id = ?",
        (upload_result["url"], upload_result["public_id"], user_id),
    )
