"""
AssistantChat: chat conversacional con Claude usando contexto de correos locales.
Carga perfiles, estado de análisis, agenda y almacenamiento para dar respuestas
contextuales. Guarda historial en chat_history.json (máx. 20 pares).
"""
import json
import os
from datetime import datetime
from pathlib import Path

CHAT_HISTORY_PATH = Path("chat_history.json")
_MAX_HISTORY = 20   # máximo de pares usuario/asistente
_MODEL       = "claude-sonnet-4-6"


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _get_api_key() -> str | None:
    _load_env()
    return os.getenv("ANTHROPIC_API_KEY")


class AssistantChat:
    def __init__(self):
        self.context: dict = {}
        self.history: list[dict] = self._load_history()
        self.refresh_context()

    # ── API pública ───────────────────────────────────────────────────────────

    def refresh_context(self):
        """Recarga todos los archivos JSON locales para tener datos frescos."""
        profiles_raw = self._read_json("contact_profiles.json", {})
        state        = self._read_json("analysis_state.json",   {})
        schedule     = self._read_json("cleanup_schedule.json", {})
        patterns     = self._read_json("user_patterns.json",    {})

        self.context = {
            "profiles":  profiles_raw.get("profiles", {}),
            "state":     state,
            "schedule":  schedule,
            "patterns":  patterns,
        }

    def send_message(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Envía un mensaje a Claude y devuelve la respuesta en texto."""
        api_key = _get_api_key()
        if not api_key:
            return (
                "Para usar el asistente necesito que configures tu clave de API "
                "en el archivo .env (la línea ANTHROPIC_API_KEY=...)."
            )

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            return "No está instalado el módulo necesario. Ejecuta: pip install anthropic"

        self.refresh_context()
        system_prompt = self._build_system_prompt()

        # Historial para la API (sin timestamps, solo role/content)
        hist = conversation_history if conversation_history is not None else self.history
        api_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in hist[-(  _MAX_HISTORY * 2):]
        ]
        api_messages.append({"role": "user", "content": user_message})

        try:
            resp   = client.messages.create(
                model=_MODEL, max_tokens=1000,
                system=system_prompt, messages=api_messages,
            )
            answer = resp.content[0].text.strip()
        except Exception as exc:
            return f"Ocurrió un problema al contactar al asistente: {exc}"

        # Guardar en historial
        ts = datetime.now().isoformat(timespec="seconds")
        self.history.append({"role": "user",      "content": user_message, "ts": ts})
        self.history.append({"role": "assistant",  "content": answer,       "ts": ts})
        if len(self.history) > _MAX_HISTORY * 2:
            self.history = self.history[-(_MAX_HISTORY * 2):]
        self._save_history()
        return answer

    # ── Construcción del prompt de sistema ───────────────────────────────────

    def _build_system_prompt(self) -> str:
        profiles  = self.context.get("profiles",  {})
        state     = self.context.get("state",     {})
        schedule  = self.context.get("schedule",  {})

        pending_count   = len(state.get("pending", []))
        stats           = state.get("stats", {})
        personal_count  = stats.get("personal", 0)
        spam_count      = stats.get("spam",     0)

        # Resumen de perfiles
        profiles_block = ""
        if profiles:
            lines = [f"\nContactos importantes ({len(profiles)}):"]
            for addr, p in list(profiles.items())[:10]:
                name    = p.get("name", addr)
                rel     = p.get("relation_type", "otro")
                last    = p.get("last_contact", "")
                summary = p.get("summary", "")[:120]
                alerts  = p.get("alerts", [])
                lines.append(f"- {name} <{addr}> [{rel}], último contacto: {last}")
                if summary:
                    lines.append(f"  {summary}")
                for al in alerts[:1]:
                    lines.append(f"  ⚠️ {al}")
            profiles_block = "\n".join(lines)

        # Estado de limpiezas programadas
        sched_block = ""
        if schedule.get("enabled"):
            nxt = (schedule.get("next_run") or "")[:16].replace("T", " ")
            sched_block = f"\nLimpieza automática activada. Próxima: {nxt or 'no calculada aún'}"

        context_block = (
            f"\nEstado actual del correo:"
            f"\n- Contactos importantes: {personal_count}"
            f"\n- Contactos marcados como spam: {spam_count}"
            f"\n- Pendientes de clasificar: {pending_count}"
            f"{profiles_block}"
            f"{sched_block}"
        )

        return (
            "Eres el asistente personal de correo del usuario.\n"
            "Ayudas a personas mayores a manejar su correo electrónico de manera simple.\n"
            "Tienes acceso a toda la información de sus correos organizados.\n\n"
            "Cuando te pregunten algo:\n"
            "- Responde siempre en español, de forma corta y clara\n"
            "- Si la respuesta está en los perfiles de contactos, cítala directamente\n"
            "- Si necesitan hacer una acción (limpiar, proteger), diles exactamente\n"
            "  qué sección de la app usar y explícales el paso a paso\n"
            "- Si no sabes algo, dilo claramente y sugiere dónde pueden encontrarlo\n"
            "- Nunca uses términos técnicos como 'API', 'token', 'módulo', etc.\n"
            "- Sé cálido y paciente, como si hablaras con alguien de confianza\n"
            f"{context_block}"
        )

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _read_json(self, path: str, default: dict) -> dict:
        p = Path(path)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return default

    def _load_history(self) -> list[dict]:
        if CHAT_HISTORY_PATH.exists():
            try:
                return json.loads(CHAT_HISTORY_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_history(self):
        CHAT_HISTORY_PATH.write_text(
            json.dumps(self.history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
