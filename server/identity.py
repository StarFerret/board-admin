import hashlib
import re

_EMOJIS = ["🧠", "🦊", "🦉", "🐝", "🌊", "🔧", "📚", "🌙", "⚡", "🌿", "🎯", "🔮"]
_COLORS = ["#3b82f6", "#8b5cf6", "#059669", "#d97706", "#e11d48", "#0891b2", "#4f46e5", "#65a30d"]


def mint_identity(name: str) -> dict:
    """Local identity. Creating an agent does not call Ollama."""
    digest = hashlib.sha256((name or "agent").encode("utf-8")).digest()
    return {
        "emoji": _EMOJIS[digest[0] % len(_EMOJIS)],
        "color": _COLORS[digest[1] % len(_COLORS)],
        "tagline": "",
    }


def favicon_svg(emoji: str, color: str) -> str:
    safe_emoji = (
        emoji.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    safe_color = color if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) else "#4C8DFF"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <circle cx="32" cy="32" r="32" fill="{safe_color}"/>
  <text x="32" y="42" text-anchor="middle" font-size="28">{safe_emoji}</text>
</svg>
"""
