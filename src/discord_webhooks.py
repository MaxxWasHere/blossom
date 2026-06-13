"""Post messages to Discord webhook URLs from macro config."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

DISCORD_WEBHOOK_RE = re.compile(
    r"^https://(?:(?:ptb|canary|discordapp)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$",
    re.IGNORECASE,
)

# Soft, on-brand accent colors per merchant (kept simple + readable in Discord).
MERCHANT_COLORS: dict[str, int] = {
    "Mari": 0xF49AC2,   # rose
    "Jester": 0xF1C40F,  # gold
    "Rin": 0x9B59B6,  # violet
}
MERCHANT_THUMBNAILS: dict[str, str] = {
    "Mari": "https://static.wikia.nocookie.net/sol-rng/images/d/df/Mari_cropped.png/revision/latest?cb=20241015111527",
    "Jester": "https://static.wikia.nocookie.net/sol-rng/images/d/db/Headshot_of_Jester.png/revision/latest?cb=20240630142936",
}


def _merchant_embed_base(merchant_name: str) -> dict[str, Any]:
    """Shared embed fields for merchant alerts."""
    embed: dict[str, Any] = {
        "color": MERCHANT_COLORS.get(merchant_name, BLOSSOM_ACCENT),
        "timestamp": _now_iso(),
        "author": {"name": "Blossom · Auto Merchant", "icon_url": BLOSSOM_FOOTER_ICON},
        "footer": {"text": "Blossom Macro"},
    }
    thumb = MERCHANT_THUMBNAILS.get(merchant_name)
    if thumb:
        embed["thumbnail"] = {"url": thumb}
    return embed
BLOSSOM_ACCENT = 0xE89BD0


def normalize_webhook_urls(raw: Any) -> list[str]:
    urls: list[str] = []
    if raw is None:
        return urls
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return urls
    for item in raw:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                urls.append(cleaned)
        elif isinstance(item, dict):
            candidate = item.get("url") or item.get("webhook_url") or item.get("webhook")
            if candidate:
                cleaned = str(candidate).strip()
                if cleaned:
                    urls.append(cleaned)
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _validate_url(url: str) -> None:
    if not DISCORD_WEBHOOK_RE.match(url):
        raise ValueError(f"Not a Discord webhook URL: {url[:48]}…")


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, str]:
    try:
        import requests

        response = requests.post(url, json=payload, timeout=timeout)
        return response.status_code, response.text
    except ImportError:
        data = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "BlossomMacro/1.0",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                return response.status, body
        except urlerror.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            return error.code, body


BLOSSOM_FOOTER_ICON = "https://maxstellar.github.io/biome_thumb/GLITCHED.png"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_color(color: Any) -> int | None:
    """Accept ints or hex strings like '0xbfff00' / '#bfff00' / 'bfff00'."""
    if color is None:
        return None
    if isinstance(color, int):
        return color & 0xFFFFFF
    text = str(color).strip().lower().lstrip("#")
    if text.startswith("0x"):
        text = text[2:]
    try:
        return int(text, 16) & 0xFFFFFF
    except ValueError:
        return None


def build_ping_mention(ping: Any) -> str:
    """Turn a {'id','type'} ping config into a Discord mention string ('' when unset)."""
    if not isinstance(ping, dict):
        if ping:
            return f"<@{str(ping).strip()}>"
        return ""
    pid = str(ping.get("id") or "").strip()
    if not pid:
        return ""
    kind = str(ping.get("type") or "userid").strip().lower()
    if kind in ("role", "roleid", "role_id"):
        return f"<@&{pid}>"
    if kind in ("everyone", "here"):
        return f"@{kind}"
    return f"<@{pid}>"


def send_discord_webhook(
    urls: list[str],
    *,
    message: str,
    color: int | None = 5814783,
    username: str | None = None,
    avatar_url: str | None = None,
    title: str | None = None,
    timeout: float = 15.0,
) -> int:
    """Send a polished embed to every webhook URL. Returns count sent. Raises on total failure."""
    if not urls:
        raise ValueError("No webhook URLs configured. Add one on the Webhook tab and save.")

    embed: dict[str, Any] = {
        "description": str(message),
        "timestamp": _now_iso(),
        "author": {"name": "Blossom", "icon_url": BLOSSOM_FOOTER_ICON},
        "footer": {"text": "Blossom Macro"},
    }
    embed["color"] = (_coerce_color(color) if color is not None else None) or BLOSSOM_ACCENT
    if title:
        embed["title"] = str(title)[:256]

    payload: dict[str, Any] = {"embeds": [embed]}
    if username:
        payload["username"] = str(username)[:80]
    if avatar_url:
        payload["avatar_url"] = str(avatar_url)

    sent = 0
    errors: list[str] = []
    for url in urls:
        try:
            _validate_url(url)
            status, body = _post_json(url, payload, timeout)
            if status >= 400:
                detail = body.strip().replace("\n", " ")[:240]
                errors.append(f"HTTP {status}: {detail or 'request failed'}")
                continue
            sent += 1
        except ValueError as error:
            errors.append(str(error))
        except (urlerror.URLError, OSError, TimeoutError) as error:
            errors.append(str(error))

    if sent == 0:
        raise RuntimeError(errors[0] if len(errors) == 1 else "; ".join(errors))
    if errors:
        print(f"[webhook] partial failure ({sent}/{len(urls)}): {'; '.join(errors)}")
    return sent


def _post_multipart(
    url: str, payload: dict[str, Any], image_path: str, timeout: float
) -> tuple[int, str]:
    """POST an embed + image attachment to a Discord webhook (payload_json + file)."""
    filename = os.path.basename(image_path)
    with open(image_path, "rb") as handle:
        file_bytes = handle.read()

    try:
        import requests

        response = requests.post(
            url,
            data={"payload_json": json.dumps(payload)},
            files={"file": (filename, file_bytes, "image/png")},
            timeout=timeout,
        )
        return response.status_code, response.text
    except ImportError:
        pass

    boundary = f"----BlossomBoundary{uuid.uuid4().hex}"
    crlf = b"\r\n"
    body = bytearray()
    body += f"--{boundary}".encode() + crlf
    body += b'Content-Disposition: form-data; name="payload_json"' + crlf
    body += b"Content-Type: application/json" + crlf + crlf
    body += json.dumps(payload).encode("utf-8") + crlf
    body += f"--{boundary}".encode() + crlf
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode() + crlf
    body += b"Content-Type: image/png" + crlf + crlf
    body += file_bytes + crlf
    body += f"--{boundary}--".encode() + crlf

    req = urlrequest.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "BlossomMacro/1.0",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urlerror.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def send_merchant_found_webhook(
    urls: list[str],
    *,
    merchant_name: str,
    ps_link: str | None = None,
    ping_id: str | None = None,
    timeout: float = 15.0,
) -> int:
    """Fast alert when OCR identifies Mari/Jester/Rin (before shop opens). Returns count sent."""
    urls = normalize_webhook_urls(urls)
    if not urls:
        return 0

    unix = int(datetime.now(timezone.utc).timestamp())
    embed: dict[str, Any] = {
        **_merchant_embed_base(merchant_name),
        "title": f"🛎️ {merchant_name} merchant appeared",
        "description": (
            f"**{merchant_name}** was detected on screen.\n"
            f"Spotted <t:{unix}:R> — opening shop next."
        ),
    }
    if ps_link:
        embed["fields"] = [
            {"name": "Rejoin", "value": f"[Private server]({ps_link})", "inline": False}
        ]

    payload: dict[str, Any] = {"embeds": [embed]}
    if ping_id:
        payload["content"] = f"<@{ping_id}>"
        payload["allowed_mentions"] = {"parse": ["everyone", "roles", "users"]}

    return _dispatch(urls, payload, screenshot_path=None, timeout=timeout, label="merchant-found")


def send_merchant_webhook(
    urls: list[str],
    *,
    merchant_name: str,
    screenshot_path: str | None = None,
    ps_link: str | None = None,
    ping_id: str | None = None,
    purchased: list[str] | None = None,
    timeout: float = 15.0,
) -> int:
    """Shop-open embed with optional full-screen screenshot (distinct from merchant-found alert)."""
    urls = normalize_webhook_urls(urls)
    if not urls:
        return 0

    unix = int(datetime.now(timezone.utc).timestamp())
    embed: dict[str, Any] = {
        **_merchant_embed_base(merchant_name),
        "title": f"🛒 {merchant_name} shop open",
        "description": f"**{merchant_name}** shop is open.\nCaptured <t:{unix}:R>",
    }
    if purchased:
        embed["fields"] = [
            {"name": "Auto-bought", "value": "\n".join(f"• {item}" for item in purchased), "inline": False}
        ]
    if ps_link:
        embed.setdefault("fields", []).append(
            {"name": "Rejoin", "value": f"[Private server]({ps_link})", "inline": False}
        )

    has_image = bool(screenshot_path) and os.path.isfile(str(screenshot_path))
    if has_image:
        embed["image"] = {"url": f"attachment://{os.path.basename(str(screenshot_path))}"}

    payload: dict[str, Any] = {"embeds": [embed]}
    if ping_id:
        payload["content"] = f"<@{ping_id}>"
        payload["allowed_mentions"] = {"parse": ["everyone", "roles", "users"]}

    return _dispatch(
        urls,
        payload,
        screenshot_path=str(screenshot_path) if has_image else None,
        timeout=timeout,
        label="merchant-shop",
    )


# Only these biomes get the louder "rare" presentation and optional @everyone.
RARE_BIOMES = frozenset({"GLITCHED", "DREAMSPACE", "CYBERSPACE"})
REMOVED_BIOMES = frozenset({"AURORA", "EGGLAND"})
RARE_MENTION_MODES = frozenset({"everyone", "users", "both"})
DEFAULT_RARE_MENTION_MODE = "both"


def is_rare_biome(biome_name: str) -> bool:
    """True for GLITCHED, DREAMSPACE, CYBERSPACE (case-insensitive exact match)."""
    upper = str(biome_name).strip().upper()
    return upper in RARE_BIOMES


def _parse_id_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = raw
    elif isinstance(raw, str):
        items = re.split(r"[\s,;]+", raw.strip())
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        pid = str(item).strip()
        if pid.isdigit() and pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def _coerce_rare_mention_mode(raw: Any, *, fallback: str = DEFAULT_RARE_MENTION_MODE) -> str:
    mode = str(raw or "").strip().lower()
    if mode in RARE_MENTION_MODES:
        return mode
    return fallback if fallback in RARE_MENTION_MODES else DEFAULT_RARE_MENTION_MODE


def normalize_biome_ping_entry(
    ping: Any,
    *,
    biome_name: str,
    global_rare_mode: str = DEFAULT_RARE_MENTION_MODE,
) -> dict[str, Any]:
    """Normalize biome_pings[BIOME] to users/roles lists + rare mention mode."""
    upper = str(biome_name).strip().upper()
    is_rare = is_rare_biome(upper)
    default_mode = _coerce_rare_mention_mode(global_rare_mode)

    if not isinstance(ping, dict):
        legacy_id = str(ping or "").strip()
        users = [legacy_id] if legacy_id.isdigit() else []
        return {
            "users": users,
            "roles": [],
            "mention_everyone": is_rare and default_mode in ("everyone", "both"),
            "rare_mention_mode": default_mode if is_rare else "users",
        }

    users = _parse_id_list(ping.get("users"))
    roles = _parse_id_list(ping.get("roles"))

    legacy_id = str(ping.get("id") or "").strip()
    if legacy_id:
        kind = str(ping.get("type") or "userid").strip().lower()
        if kind in ("role", "roleid", "role_id"):
            if legacy_id not in roles:
                roles.append(legacy_id)
        elif kind not in ("everyone", "here") and legacy_id.isdigit() and legacy_id not in users:
            users.append(legacy_id)

    rare_mode = _coerce_rare_mention_mode(
        ping.get("rare_mention_mode"),
        fallback=default_mode if is_rare else "users",
    )
    if not is_rare:
        rare_mode = "users"
    elif bool(ping.get("mention_everyone")) and rare_mode == "users" and users:
        rare_mode = "both"
    elif bool(ping.get("mention_everyone")) and rare_mode == "users":
        rare_mode = "everyone"

    return {
        "users": users,
        "roles": roles,
        "mention_everyone": is_rare and rare_mode in ("everyone", "both"),
        "rare_mention_mode": rare_mode,
    }


def migrate_biome_webhook_config(config: dict[str, Any]) -> dict[str, Any]:
    """In-place migration for biome_notifier / biome_pings (legacy id/type → users/roles)."""
    if not isinstance(config, dict):
        return config

    global_rare = _coerce_rare_mention_mode(
        config.get("rare_biome_mention_mode"),
        fallback=DEFAULT_RARE_MENTION_MODE,
    )
    config["rare_biome_mention_mode"] = global_rare

    notifier = config.get("biome_notifier")
    if isinstance(notifier, dict):
        for removed in REMOVED_BIOMES:
            notifier.pop(removed, None)

    pings = config.get("biome_pings")
    if not isinstance(pings, dict):
        pings = {}
    normalized: dict[str, Any] = {}
    for biome, entry in pings.items():
        if not str(biome).strip():
            continue
        upper = str(biome).strip().upper()
        if upper in REMOVED_BIOMES:
            continue
        normalized[upper] = normalize_biome_ping_entry(
            entry,
            biome_name=upper,
            global_rare_mode=global_rare,
        )
    config["biome_pings"] = normalized
    return config


def build_biome_webhook_mentions(
    ping: Any,
    *,
    biome_name: str,
    global_rare_mode: str = DEFAULT_RARE_MENTION_MODE,
) -> tuple[str, dict[str, Any]]:
    """Build Discord content + allowed_mentions for a biome alert."""
    cfg = normalize_biome_ping_entry(
        ping,
        biome_name=biome_name,
        global_rare_mode=global_rare_mode,
    )
    upper = str(biome_name).strip().upper()
    is_rare = is_rare_biome(upper)
    mode = cfg["rare_mention_mode"] if is_rare else "users"

    parts: list[str] = []
    if is_rare and mode in ("everyone", "both"):
        parts.append("@everyone")
    if not is_rare or mode in ("users", "both"):
        for rid in cfg["roles"]:
            parts.append(f"<@&{rid}>")
        for uid in cfg["users"]:
            parts.append(f"<@{uid}>")

    content = " ".join(parts).strip()
    allowed: dict[str, Any] = {"parse": [], "users": [], "roles": []}
    if is_rare and mode in ("everyone", "both"):
        allowed["parse"] = ["everyone"]
    if not is_rare or mode in ("users", "both"):
        allowed["users"] = list(cfg["users"])
        allowed["roles"] = list(cfg["roles"])
    return content, allowed


def _biome_webhook_content(ping: Any, *, force_everyone: bool) -> str:
    """Legacy helper — prefer build_biome_webhook_mentions."""
    content, _ = build_biome_webhook_mentions(
        ping,
        biome_name="GLITCHED" if force_everyone else "WINDY",
        global_rare_mode="everyone" if force_everyone else "users",
    )
    return content


def send_biome_webhook(
    urls: list[str],
    *,
    biome_name: str,
    color: Any = None,
    thumbnail_url: str | None = None,
    username: str | None = None,
    ps_link: str | None = None,
    ping: Any = None,
    rare_mention_mode: str | None = None,
    screenshot_path: str | None = None,
    timeout: float = 15.0,
) -> int:
    """Rich biome-detected embed (per-biome color/thumbnail/ping). Returns count sent."""
    urls = normalize_webhook_urls(urls)
    if not urls:
        return 0

    name = str(biome_name).strip()
    upper = name.upper()
    is_rare = is_rare_biome(upper)
    emoji = "🌟" if is_rare else "🌿"
    unix = int(datetime.now(timezone.utc).timestamp())

    description = f"Spotted <t:{unix}:R>"

    fields: list[dict[str, Any]] = []
    if username:
        fields.append({"name": "Player", "value": str(username), "inline": True})
    if ps_link:
        fields.append({"name": "Rejoin", "value": f"[Private server]({ps_link})", "inline": True})

    embed: dict[str, Any] = {
        "title": f"{emoji} {upper} Biome",
        "description": description,
        "color": _coerce_color(color) or BLOSSOM_ACCENT,
        "timestamp": _now_iso(),
        "author": {"name": "Blossom · Biome Notifier", "icon_url": BLOSSOM_FOOTER_ICON},
        "footer": {"text": "Blossom Macro"},
    }
    if fields:
        embed["fields"] = fields

    has_image = bool(screenshot_path) and os.path.isfile(str(screenshot_path))
    if has_image:
        embed["image"] = {"url": f"attachment://{os.path.basename(str(screenshot_path))}"}
    if thumbnail_url:
        embed["thumbnail"] = {"url": str(thumbnail_url)}

    payload: dict[str, Any] = {"embeds": [embed]}
    content, allowed = build_biome_webhook_mentions(
        ping,
        biome_name=upper,
        global_rare_mode=_coerce_rare_mention_mode(rare_mention_mode),
    )
    if content:
        payload["content"] = content
        payload["allowed_mentions"] = allowed

    return _dispatch(
        urls,
        payload,
        screenshot_path=str(screenshot_path) if has_image else None,
        timeout=timeout,
        label="biome",
    )


def _dispatch(
    urls: list[str],
    payload: dict[str, Any],
    *,
    screenshot_path: str | None,
    timeout: float,
    label: str,
) -> int:
    """Shared send loop (multipart when a screenshot is attached, else JSON)."""
    has_image = bool(screenshot_path) and os.path.isfile(str(screenshot_path))
    sent = 0
    errors: list[str] = []
    for url in urls:
        try:
            _validate_url(url)
            if has_image:
                status, body = _post_multipart(url, payload, str(screenshot_path), timeout)
            else:
                status, body = _post_json(url, payload, timeout)
            if status >= 400:
                errors.append(f"HTTP {status}: {body.strip().replace(chr(10), ' ')[:200]}")
                continue
            sent += 1
        except (ValueError, urlerror.URLError, OSError, TimeoutError) as error:
            errors.append(str(error))
    if errors:
        print(f"[webhook] {label} partial failure ({sent}/{len(urls)}): {'; '.join(errors)}")
    return sent


# Macro lifecycle / status events → title, emoji, accent color.
STATUS_EVENTS: dict[str, tuple[str, str, int]] = {
    "started": ("Macro started", "▶️", 0x57F287),
    "stopped": ("Macro stopped", "⏹️", 0xED4245),
    "paused": ("Macro paused", "⏸️", 0xFEE75C),
    "resumed": ("Macro resumed", "▶️", 0x57F287),
    "reconnect": ("Reconnecting to Roblox", "🔄", 0xFEE75C),
    "error": ("Macro error", "⚠️", 0xED4245),
}


def send_status_webhook(
    urls: list[str],
    *,
    event: str,
    detail: str | None = None,
    version: str | None = None,
    username: str | None = None,
    ping_id: str | None = None,
    timeout: float = 15.0,
) -> int:
    """Macro lifecycle notification (started / stopped / etc.). Returns count sent."""
    urls = normalize_webhook_urls(urls)
    if not urls:
        return 0

    title, emoji, color = STATUS_EVENTS.get(
        str(event).lower(), (str(event).title(), "🔔", BLOSSOM_ACCENT)
    )
    unix = int(datetime.now(timezone.utc).timestamp())
    lines = [f"<t:{unix}:F>"]
    if detail:
        lines.append(str(detail))

    embed: dict[str, Any] = {
        "title": f"{emoji} {title}",
        "description": "\n".join(lines),
        "color": color,
        "timestamp": _now_iso(),
        "author": {"name": "Blossom · Status", "icon_url": BLOSSOM_FOOTER_ICON},
        "footer": {"text": "Blossom Macro" + (f" · v{version}" if version else "")},
    }
    fields: list[dict[str, Any]] = []
    if username:
        fields.append({"name": "Player", "value": str(username), "inline": True})
    if fields:
        embed["fields"] = fields

    payload: dict[str, Any] = {"embeds": [embed]}
    if ping_id:
        payload["content"] = f"<@{str(ping_id).strip()}>"
        payload["allowed_mentions"] = {"parse": ["everyone", "roles", "users"]}

    return _dispatch(urls, payload, screenshot_path=None, timeout=timeout, label="status")


def send_currency_webhook(
    urls: list[str],
    *,
    screenshot_path: str,
    username: str | None = None,
    ps_link: str | None = None,
    ping_id: str | None = None,
    title: str = "Currency update",
    timeout: float = 15.0,
) -> int:
    """Periodic currency-region screenshot embed. Returns count sent."""
    urls = normalize_webhook_urls(urls)
    if not urls:
        return 0
    if not (screenshot_path and os.path.isfile(str(screenshot_path))):
        return 0

    unix = int(datetime.now(timezone.utc).timestamp())
    fields: list[dict[str, Any]] = []
    if username:
        fields.append({"name": "Player", "value": str(username), "inline": True})
    if ps_link:
        fields.append({"name": "Rejoin", "value": f"[Private server]({ps_link})", "inline": True})

    embed: dict[str, Any] = {
        "title": f"💰 {title}",
        "description": f"Captured <t:{unix}:R>",
        "color": 0xF1C40F,
        "timestamp": _now_iso(),
        "author": {"name": "Blossom · Currency", "icon_url": BLOSSOM_FOOTER_ICON},
        "footer": {"text": "Blossom Macro"},
        "image": {"url": f"attachment://{os.path.basename(str(screenshot_path))}"},
    }
    if fields:
        embed["fields"] = fields

    payload: dict[str, Any] = {"embeds": [embed]}
    if ping_id:
        payload["content"] = f"<@{str(ping_id).strip()}>"
        payload["allowed_mentions"] = {"parse": ["everyone", "roles", "users"]}

    return _dispatch(urls, payload, screenshot_path=str(screenshot_path), timeout=timeout, label="currency")


def send_aura_webhook(
    urls: list[str],
    *,
    aura_name: str,
    username: str | None = None,
    ps_link: str | None = None,
    ping: Any = None,
    rarity: int | None = None,
    screenshot_path: str | None = None,
    timeout: float = 15.0,
) -> int:
    """Equipped-aura alert (original rarity rules, Blossom embed style). Returns count sent.

    ps_link is accepted for caller compatibility but is not included in aura embeds.
    """
    urls = normalize_webhook_urls(urls)
    if not urls:
        return 0

    name = str(aura_name).strip()
    unix = int(datetime.now(timezone.utc).timestamp())
    description = f"Equipped <t:{unix}:R>"

    fields: list[dict[str, Any]] = []
    if rarity:
        fields.append({"name": "Rarity", "value": f"1 in {rarity:,}", "inline": True})
    if username:
        fields.append({"name": "Player", "value": str(username), "inline": True})

    embed: dict[str, Any] = {
        "title": f"✨ {name}",
        "description": description,
        "color": 0xB37FEB,
        "timestamp": _now_iso(),
        "author": {"name": "Blossom · Aura Notifier", "icon_url": BLOSSOM_FOOTER_ICON},
        "footer": {"text": "Blossom Macro"},
    }
    if fields:
        embed["fields"] = fields

    has_image = bool(screenshot_path) and os.path.isfile(str(screenshot_path))
    if has_image:
        embed["image"] = {"url": f"attachment://{os.path.basename(str(screenshot_path))}"}

    payload: dict[str, Any] = {"embeds": [embed]}
    mention = build_ping_mention(ping)
    if mention:
        payload["content"] = mention
        allowed: dict[str, Any] = {"parse": [], "users": [], "roles": []}
        if isinstance(ping, dict):
            pid = str(ping.get("id") or "").strip()
            kind = str(ping.get("type") or "userid").strip().lower()
            if pid.isdigit():
                if kind in ("role", "roleid", "role_id"):
                    allowed["roles"] = [pid]
                else:
                    allowed["users"] = [pid]
        payload["allowed_mentions"] = allowed

    return _dispatch(
        urls,
        payload,
        screenshot_path=str(screenshot_path) if has_image else None,
        timeout=timeout,
        label="aura",
    )


def send_eden_webhook(
    urls: list[str],
    *,
    ping: Any = None,
    screenshot_path: str | None = None,
    timeout: float = 15.0,
) -> int:
    """Eden-spawn detection alert (port of the original Noteab eden OCR ping)."""
    urls = normalize_webhook_urls(urls)
    if not urls:
        return 0

    unix = int(datetime.now(timezone.utc).timestamp())
    embed: dict[str, Any] = {
        "title": "Eden has appeared!",
        "description": f"Devourer of the Void, **Eden** has appeared <t:{unix}:R>.",
        "color": 0x9B59B6,
        "timestamp": _now_iso(),
        "author": {"name": "Blossom · Eden Notifier", "icon_url": BLOSSOM_FOOTER_ICON},
        "footer": {"text": "Blossom Macro"},
    }
    if screenshot_path and os.path.isfile(str(screenshot_path)):
        embed["image"] = {"url": f"attachment://{os.path.basename(str(screenshot_path))}"}

    payload: dict[str, Any] = {"embeds": [embed]}
    mention = build_ping_mention(ping)
    if mention:
        payload["content"] = mention
        payload["allowed_mentions"] = {"parse": ["everyone", "roles", "users"]}

    return _dispatch(urls, payload, screenshot_path=screenshot_path, timeout=timeout, label="eden")
