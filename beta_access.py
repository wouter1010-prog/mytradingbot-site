"""Private-beta access registry for MyTradingBot v8.

The owner keeps using MYTRADINGBOT_API_TOKEN. Friends/testers redeem a single-use
invite code and receive a revocable, hashed access token tied to an isolated
workspace. Raw invite/session tokens are never stored server-side.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
REGISTRY_FILE = DATA_DIR / "beta_access_v8.json"
MASTER_SECRET = (
    os.environ.get("MYTRADINGBOT_MASTER_KEY")
    or os.environ.get("DOOPIECASH_MASTER_KEY")
    or os.environ.get("MYTRADINGBOT_API_TOKEN")
    or os.environ.get("DOOPIECASH_API_TOKEN")
    or ""
).encode("utf-8")
LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> Dict[str, Any]:
    try:
        value = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            value.setdefault("version", 1)
            value.setdefault("invites", {})
            value.setdefault("sessions", {})
            return value
    except Exception:
        pass
    return {"version": 1, "invites": {}, "sessions": {}}


def _save(value: Dict[str, Any]) -> None:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=REGISTRY_FILE.name + ".", suffix=".tmp", dir=str(REGISTRY_FILE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, REGISTRY_FILE)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _digest(value: str) -> str:
    if not MASTER_SECRET:
        raise RuntimeError("MYTRADINGBOT_MASTER_KEY of MYTRADINGBOT_API_TOKEN ontbreekt")
    return hmac.new(MASTER_SECRET, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", str(value or "tester").strip().lower()).strip("-")
    return (clean or "tester")[:28]


def _expired(value: Any) -> bool:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp < datetime.now(timezone.utc)
    except Exception:
        return True


def create_invite(
    label: str,
    *,
    expires_minutes: Optional[int] = None,
    expires_hours: Optional[int] = None,
    expires_days: Optional[int] = None,
    max_uses: int = 1,
    mode: str = "tester",
) -> Dict[str, Any]:
    """Create a single-use beta invitation with an exact UTC expiry.

    Duration precedence is minutes, then hours, then days. When nothing is
    provided the legacy-safe default remains 14 days. The accepted range is
    one minute through ninety days.
    """
    code = "DCB-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:22].upper()
    invite_id = secrets.token_hex(8)

    duration_source = "days"
    duration_value = 14
    if expires_minutes is not None:
        duration_source = "minutes"
        duration_value = max(1, min(90 * 24 * 60, int(expires_minutes)))
        delta = timedelta(minutes=duration_value)
    elif expires_hours is not None:
        duration_source = "hours"
        duration_value = max(1, min(90 * 24, int(expires_hours)))
        delta = timedelta(hours=duration_value)
    else:
        raw_days = 14 if expires_days is None else int(expires_days)
        duration_value = max(1, min(90, raw_days))
        delta = timedelta(days=duration_value)

    max_uses = max(1, min(20, int(max_uses or 1)))
    mode = mode if mode in {"tester", "paper"} else "tester"
    created_at = datetime.now(timezone.utc)
    record = {
        "id": invite_id,
        "label": str(label or "Beta tester")[:80],
        "mode": mode,
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + delta).isoformat(),
        "expires_value": duration_value,
        "expires_unit": duration_source,
        "max_uses": max_uses,
        "uses": 0,
        "revoked": False,
    }
    with LOCK:
        registry = _load()
        registry["invites"][_digest(code)] = record
        _save(registry)
    return {**record, "code": code}


def list_invites() -> list[Dict[str, Any]]:
    with LOCK:
        registry = _load()
    rows = []
    for record in registry.get("invites", {}).values():
        if isinstance(record, dict):
            rows.append({**record, "expired": _expired(record.get("expires_at")), "remaining": max(0, int(record.get("max_uses", 1)) - int(record.get("uses", 0)))})
    return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)


def revoke_invite(invite_id: str) -> bool:
    """Revoke an unused or still-valid invite by its public id."""
    changed = False
    with LOCK:
        registry = _load()
        for invite_hash, record in list(registry.get("invites", {}).items()):
            if isinstance(record, dict) and record.get("id") == invite_id:
                if not record.get("revoked"):
                    record["revoked"] = True
                    record["revoked_at"] = now_iso()
                    registry["invites"][invite_hash] = record
                    changed = True
                break
        if changed:
            _save(registry)
    return changed


def redeem_invite(code: str, display_name: str, *, consent: bool) -> Dict[str, Any]:
    if not consent:
        raise ValueError("Bevestig eerst de privacy- en beta-afspraken")
    if len(str(display_name or "").strip()) < 2:
        raise ValueError("Vul je naam in")
    code = str(code or "").strip()
    if len(code) < 12:
        raise ValueError("Ongeldige uitnodigingscode")
    invite_hash = _digest(code)
    with LOCK:
        registry = _load()
        invite = registry.get("invites", {}).get(invite_hash)
        if not isinstance(invite, dict) or invite.get("revoked"):
            raise ValueError("Uitnodigingscode is ongeldig of ingetrokken")
        if _expired(invite.get("expires_at")):
            raise ValueError("Uitnodigingscode is verlopen")
        if int(invite.get("uses", 0)) >= int(invite.get("max_uses", 1)):
            raise ValueError("Uitnodigingscode is al gebruikt")
        workspace_id = f"{_slug(display_name)}-{secrets.token_hex(4)}"
        token = "dcb_" + secrets.token_urlsafe(40)
        token_hash = _digest(token)
        session = {
            "id": secrets.token_hex(8),
            "workspace_id": workspace_id,
            "display_name": str(display_name).strip()[:80],
            "role": "tester",
            "mode": invite.get("mode") or "tester",
            "created_at": now_iso(),
            "last_seen_at": now_iso(),
            "revoked": False,
            "invite_id": invite.get("id"),
            "consent_at": now_iso(),
            "capabilities": ["chart_sync", "review", "paper_journal", "feedback", "data_export", "data_delete"],
        }
        registry["sessions"][token_hash] = session
        invite["uses"] = int(invite.get("uses", 0)) + 1
        registry["invites"][invite_hash] = invite
        _save(registry)
    workspace = DATA_DIR / "workspaces" / workspace_id
    workspace.mkdir(parents=True, exist_ok=True)
    profile = {
        "workspace_id": workspace_id,
        "display_name": session["display_name"],
        "mode": session["mode"],
        "manual_equity": 10000.0,
        "created_at": session["created_at"],
        "privacy_consent_at": session["consent_at"],
    }
    (workspace / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"token": token, "principal": public_principal(session)}


def public_principal(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": record.get("id"),
        "workspace_id": record.get("workspace_id"),
        "display_name": record.get("display_name"),
        "role": record.get("role"),
        "mode": record.get("mode"),
        "capabilities": list(record.get("capabilities") or []),
        "created_at": record.get("created_at"),
        "last_seen_at": record.get("last_seen_at"),
        "revoked": bool(record.get("revoked")),
    }


def resolve_token(token: str, owner_token: str) -> Optional[Dict[str, Any]]:
    token = str(token or "").strip()
    if owner_token and len(token) >= 32 and hmac.compare_digest(token.encode("utf-8"), owner_token.encode("utf-8")):
        return {
            "id": "owner",
            "workspace_id": "owner",
            "display_name": os.environ.get("MYTRADINGBOT_OWNER_NAME", "Eigenaar"),
            "role": "owner",
            "mode": "live",
            "capabilities": ["*"],
            "created_at": None,
            "last_seen_at": now_iso(),
            "revoked": False,
        }
    if len(token) < 32:
        return None
    token_hash = _digest(token)
    with LOCK:
        registry = _load()
        record = registry.get("sessions", {}).get(token_hash)
        if not isinstance(record, dict) or record.get("revoked"):
            return None
        record["last_seen_at"] = now_iso()
        registry["sessions"][token_hash] = record
        _save(registry)
        return public_principal(record)


def list_testers() -> list[Dict[str, Any]]:
    with LOCK:
        registry = _load()
    rows = [public_principal(record) for record in registry.get("sessions", {}).values() if isinstance(record, dict)]
    return sorted(rows, key=lambda row: row.get("created_at") or "", reverse=True)


def revoke_tester(session_id: str) -> bool:
    changed = False
    with LOCK:
        registry = _load()
        for token_hash, record in list(registry.get("sessions", {}).items()):
            if isinstance(record, dict) and record.get("id") == session_id:
                record["revoked"] = True
                record["revoked_at"] = now_iso()
                registry["sessions"][token_hash] = record
                changed = True
        if changed:
            _save(registry)
    return changed


def revoke_current_token(token: str) -> bool:
    token_hash = _digest(str(token or "").strip())
    with LOCK:
        registry = _load()
        record = registry.get("sessions", {}).get(token_hash)
        if not isinstance(record, dict):
            return False
        record["revoked"] = True
        record["revoked_at"] = now_iso()
        registry["sessions"][token_hash] = record
        _save(registry)
    return True
