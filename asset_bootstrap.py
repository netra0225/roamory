from __future__ import annotations

import base64
import hashlib
from pathlib import Path

_DASHBOARD_PALACE_BYTES = 69451
_DASHBOARD_PALACE_SHA256 = "761598ce50bfe9da82ec02806def50068cbbdaa64d4163ccc792c12f18c239a7"


def materialize_dashboard_assets(root_path: str) -> None:
    """Rebuild packaged binary dashboard assets without altering their source bytes."""
    upload_dir = Path(root_path) / "static" / "uploads"
    parts = sorted(upload_dir.glob(".dashboard-palace-part-*"))
    if len(parts) != 7:
        return

    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    image_bytes = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(image_bytes).hexdigest()

    if len(image_bytes) != _DASHBOARD_PALACE_BYTES or digest != _DASHBOARD_PALACE_SHA256:
        raise RuntimeError("Dashboard palace image source failed integrity validation.")

    target = upload_dir / "dashboard-palace-original.jpg"
    if not target.exists() or target.read_bytes() != image_bytes:
        target.write_bytes(image_bytes)
