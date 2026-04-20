"""Zara - Omni-Grasp Clipboard Processing Engine.

Abstracts multi-modal system memory ingestion via native OS callbacks.
"""

from typing import Dict, Any, Optional
import ctypes

def get_active_clipboard_data() -> Optional[Dict[str, Any]]:
    """
    Safely poll the active OS clipboard via PIL and C-struct arrays
    to capture visual CF_DIB or CF_UNICODETEXT streams.
    Returns: {"type": "image", "content": PIL_Object} or {"type": "text", "content": str}
    """
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
        if img:
            if isinstance(img, list) and len(img) > 0 and isinstance(img[0], str):
                import os
                ext = os.path.splitext(img[0])[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                    from PIL import Image
                    try:
                        img_obj = Image.open(img[0])
                        return {"type": "image", "content": img_obj}
                    except Exception as e:
                        print(f"[Clipboard Engine] Failed to open path: {e}")
                return None
            return {"type": "image", "content": img}
    except Exception as e:
        print(f"[Clipboard Engine] Image parse failure: {e}")

    try:
        # Fallback to Text extraction using natively ctypes in windows
        ctypes.windll.user32.OpenClipboard(0)
        data = ctypes.windll.user32.GetClipboardData(13) # CF_UNICODETEXT
        if data:
            pcontents = ctypes.windll.kernel32.GlobalLock(data)
            text = ctypes.c_wchar_p(pcontents).value
            ctypes.windll.kernel32.GlobalUnlock(data)
            ctypes.windll.user32.CloseClipboard()
            if text and text.strip():
                return {"type": "text", "content": text.strip()}
        ctypes.windll.user32.CloseClipboard()
    except Exception as e:
        print(f"[Clipboard Engine] Ctypes string execution failure: {e}")
        try:
            ctypes.windll.user32.CloseClipboard()
        except:
            pass

    return None
