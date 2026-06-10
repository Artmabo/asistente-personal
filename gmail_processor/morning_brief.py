"""
MorningBrief: resumen diario instantáneo desde archivos JSON locales.
Sin llamadas a Gmail ni a Anthropic — solo lectura de estado local.
Resultado cacheado por 1 hora para no recalcular en cada recarga.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

_CACHE_PATH = Path("morning_brief_cache.json")
_TTL_HOURS  = 1


class MorningBrief:

    def generate(self, service=None) -> dict:
        """
        Devuelve el resumen del día. Usa caché si tiene menos de 1 hora.
        El parámetro service se acepta por compatibilidad pero no se usa.
        """
        cached = self._load_cache()
        if cached:
            return cached
        brief = self._build()
        self._save_cache(brief)
        return brief

    # ── Construcción ─────────────────────────────────────────────────────────

    def _build(self) -> dict:
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Buenos días"
        elif hour < 19:
            greeting = "Buenas tardes"
        else:
            greeting = "Buenas noches"

        profiles_raw = self._read_json("contact_profiles.json", {})
        state        = self._read_json("analysis_state.json",   {})

        profiles      = profiles_raw.get("profiles", {})
        pending_list  = state.get("pending", [])
        pending_count = len(pending_list)
        stats         = state.get("stats", {})
        personal      = stats.get("personal", 0)
        spam          = stats.get("spam",     0)

        # Alertas de los perfiles
        alerts: list[str] = []
        for p in profiles.values():
            for al in p.get("alerts", [])[:1]:
                alerts.append(al)

        # Correos nuevos de contactos importantes: leemos reviewed con fecha reciente
        new_from_important: list[dict] = []
        today = datetime.now()
        reviewed = state.get("reviewed", {})
        for addr, entry in reviewed.items():
            if entry.get("decision") != "personal":
                continue
            profile = profiles.get(addr, {})
            last_c  = profile.get("last_contact", "")
            if not last_c:
                continue
            try:
                d = datetime.strptime(last_c, "%Y-%m-%d")
                if (today - d).days <= 7:
                    new_from_important.append({
                        "name":  profile.get("name", addr) or addr,
                        "email": addr,
                        "date":  last_c,
                    })
            except Exception:
                continue

        # Texto del resumen
        parts: list[str] = []
        if personal > 0:
            parts.append(f"{personal} contacto{'s' if personal > 1 else ''} importante{'s' if personal > 1 else ''} registrado{'s' if personal > 1 else ''}")
        if pending_count > 0:
            parts.append(f"{pending_count} contacto{'s' if pending_count > 1 else ''} pendiente{'s' if pending_count > 1 else ''} de revisión")
        if alerts:
            parts.append(f"{len(alerts)} aviso{'s' if len(alerts) > 1 else ''} de tus contactos")

        summary_text = ("Hoy " + ", ".join(parts) + ".") if parts else "Todo está en orden. Tu correo está al día."

        return {
            "greeting":            greeting,
            "summary_text":        summary_text,
            "new_from_important":  new_from_important[:5],
            "pending_decisions":   pending_count,
            "alerts":              alerts[:5],
            "storage_percent":     None,
            "personal_count":      personal,
            "spam_count":          spam,
            "generated_at":        datetime.now().isoformat(timespec="seconds"),
        }

    # ── Caché y persistencia ──────────────────────────────────────────────────

    def _load_cache(self) -> dict | None:
        if not _CACHE_PATH.exists():
            return None
        try:
            data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            dt   = datetime.fromisoformat(data.get("generated_at", ""))
            if (datetime.now() - dt) < timedelta(hours=_TTL_HOURS):
                return data
        except Exception:
            pass
        return None

    def _save_cache(self, brief: dict):
        _CACHE_PATH.write_text(
            json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _read_json(self, path: str, default: dict) -> dict:
        p = Path(path)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return default
