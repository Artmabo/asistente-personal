"""
ContactProfiler: perfiles de contactos importantes usando Anthropic Claude.
Analiza hasta 50 correos por contacto y genera un perfil persistente en JSON.
"""
import base64
import email.utils
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from googleapiclient.errors import HttpError

PROFILES_PATH = Path("contact_profiles.json")
_MAX_EMAILS   = 50
_MAX_BODY     = 500
_MODEL        = "claude-sonnet-4-20250514"


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _get_api_key() -> str | None:
    _load_env()
    return os.getenv("ANTHROPIC_API_KEY")


def _empty_profiles() -> dict:
    return {"profiles": {}, "last_build": None, "total_profiles": 0}


class ContactProfiler:
    def __init__(self):
        self.data = self._load()

    # ── API pública ───────────────────────────────────────────────────────────

    def build_profiles(
        self,
        service,
        important_contacts: list[str],
        progress_cb: Callable | None = None,
    ) -> dict:
        """
        Construye un perfil por cada email en important_contacts.
        Persiste después de cada contacto para tolerar interrupciones.
        """
        api_key = _get_api_key()
        if not api_key:
            return {"error": "no_api_key"}

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            return {"error": "anthropic_not_installed"}

        total  = len(important_contacts)
        built  = 0
        errors: list[str] = []

        for i, addr in enumerate(important_contacts):
            if progress_cb:
                progress_cb(i + 1, total, addr)
            try:
                profile = self._build_single(service, client, addr)
                self.data["profiles"][addr] = profile
                self.data["last_build"]     = datetime.now().isoformat(timespec="seconds")
                self.data["total_profiles"] = len(self.data["profiles"])
                self._save()
                built += 1
            except Exception as exc:
                errors.append(f"{addr}: {exc}")

        return {"built": built, "total": total, "errors": errors}

    def get_profiles(self) -> dict:
        return self.data.get("profiles", {})

    def get_profile(self, email: str) -> dict | None:
        return self.data["profiles"].get(email)

    def needs_rebuild(self, email: str) -> bool:
        profile = self.get_profile(email)
        if not profile:
            return True
        try:
            built_at = datetime.fromisoformat(profile.get("built_at", ""))
            return (datetime.now() - built_at).days > 7
        except Exception:
            return True

    # ── Construcción de un perfil ─────────────────────────────────────────────

    def _build_single(self, service, client, addr: str) -> dict:
        emails_data = self._fetch_emails(service, addr)

        name          = ""
        first_contact = None
        last_contact  = None
        bidirectional = False
        attachments: list[dict] = []

        try:
            sent = service.users().messages().list(
                userId="me", q=f"in:sent to:{addr}", maxResults=1,
            ).execute()
            bidirectional = bool(sent.get("messages"))
        except Exception:
            pass

        for em in emails_data:
            if em.get("from_name") and not name:
                name = em["from_name"]
            d = em.get("date_parsed")
            if d:
                if first_contact is None or d < first_contact:
                    first_contact = d
                if last_contact is None or d > last_contact:
                    last_contact = d
            for att in em.get("attachments", []):
                if len(attachments) < 20:
                    attachments.append(att)

        emails_for_prompt = [
            {
                "date":           em.get("date_str", ""),
                "subject":        em.get("subject",  ""),
                "snippet":        em.get("body_snippet", ""),
                "has_attachment": bool(em.get("attachments")),
            }
            for em in emails_data[:_MAX_EMAILS]
        ]

        claude_result = self._call_claude(client, {
            "email":        addr,
            "name":         name,
            "total_emails": len(emails_data),
            "bidirectional": bidirectional,
            "emails":       emails_for_prompt,
        })

        return {
            "email":         addr,
            "name":          name or claude_result.get("name", addr),
            "relation_type": claude_result.get("relation_type", "otro"),
            "summary":       claude_result.get("summary", ""),
            "first_contact": first_contact.strftime("%Y-%m-%d") if first_contact else "",
            "last_contact":  last_contact.strftime("%Y-%m-%d")  if last_contact  else "",
            "total_emails":  len(emails_data),
            "bidirectional": bidirectional,
            "tone":          claude_result.get("tone",     "formal"),
            "language":      claude_result.get("language", "español"),
            "attachments":   attachments,
            "timeline":      claude_result.get("timeline",   []),
            "alerts":        claude_result.get("alerts",     []),
            "key_topics":    claude_result.get("key_topics", []),
            "built_at":      datetime.now().isoformat(timespec="seconds"),
            "emails_analyzed": len(emails_data),
        }

    # ── Obtener correos ───────────────────────────────────────────────────────

    def _fetch_emails(self, service, addr: str) -> list[dict]:
        result = []
        try:
            resp = service.users().messages().list(
                userId="me", q=f"from:{addr}", maxResults=_MAX_EMAILS,
            ).execute()
            stubs = resp.get("messages", [])
        except HttpError:
            return []

        for stub in stubs:
            try:
                msg = service.users().messages().get(
                    userId="me", id=stub["id"], format="full",
                ).execute()
                result.append(self._parse_message(msg))
                time.sleep(0.05)
            except HttpError:
                continue

        return result

    def _parse_message(self, msg: dict) -> dict:
        payload  = msg.get("payload", {})
        headers  = payload.get("headers", [])

        def hdr(name: str) -> str:
            nl = name.lower()
            for h in headers:
                if h.get("name", "").lower() == nl:
                    return h.get("value", "")
            return ""

        from_raw   = hdr("From")
        from_name  = ""
        if "<" in from_raw:
            from_name = from_raw.split("<")[0].strip().strip('"').strip("'")

        date_str    = hdr("Date")
        date_parsed = None
        try:
            date_parsed = email.utils.parsedate_to_datetime(date_str).replace(tzinfo=None)
        except Exception:
            pass

        return {
            "from_name":    from_name,
            "subject":      hdr("Subject"),
            "date_str":     date_str,
            "date_parsed":  date_parsed,
            "body_snippet": self._extract_body(payload),
            "attachments":  self._extract_attachments(payload, date_str),
        }

    def _extract_body(self, payload: dict) -> str:
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                try:
                    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")[:_MAX_BODY].strip()
                except Exception:
                    pass
        for part in payload.get("parts", []):
            text = self._extract_body(part)
            if text:
                return text
        return ""

    def _extract_attachments(self, payload: dict, date_str: str) -> list[dict]:
        result: list[dict] = []
        for part in payload.get("parts", []):
            fname = part.get("filename", "")
            if fname:
                fl = fname.lower()
                if "factura" in fl or "invoice" in fl:
                    att_type = "factura"
                elif fl.endswith(".pdf"):
                    att_type = "PDF"
                elif fl.endswith((".jpg", ".jpeg", ".png", ".gif")):
                    att_type = "imagen"
                elif fl.endswith((".xlsx", ".xls", ".csv")):
                    att_type = "hoja de cálculo"
                elif fl.endswith((".docx", ".doc")):
                    att_type = "documento Word"
                else:
                    att_type = "documento"

                date_short = ""
                try:
                    d = email.utils.parsedate_to_datetime(date_str).replace(tzinfo=None)
                    date_short = d.strftime("%Y-%m-%d")
                except Exception:
                    pass

                result.append({"name": fname, "date": date_short, "type": att_type})

            if part.get("parts"):
                result.extend(self._extract_attachments(part, date_str))
        return result

    # ── Llamada a Claude ──────────────────────────────────────────────────────

    def _call_claude(self, client, data: dict) -> dict:
        emails_text = ""
        for em in data.get("emails", []):
            emails_text += (
                f"\n---\nFecha: {em['date']}\nAsunto: {em['subject']}\n"
            )
            if em.get("snippet"):
                emails_text += f"Fragmento: {em['snippet'][:300]}\n"
            if em.get("has_attachment"):
                emails_text += "(tiene adjunto)\n"

        user_prompt = (
            f"Analiza estos correos de {data['name'] or data['email']} "
            f"({data['email']}).\n"
            f"Total: {data['total_emails']} correos. "
            f"Conversación bidireccional: {'sí' if data['bidirectional'] else 'no'}.\n\n"
            f"Correos (más recientes primero):\n{emails_text}\n\n"
            "Responde SOLO con JSON válido con estos campos:\n"
            '{\n'
            '  "name": "nombre completo o apodo que usa",\n'
            '  "relation_type": "familiar|trabajo|servicio|gobierno|otro",\n'
            '  "summary": "descripción en 2-3 oraciones simples de quién es y sobre qué escribe",\n'
            '  "tone": "formal|informal|mixto",\n'
            '  "language": "español|inglés|mixto",\n'
            '  "timeline": [\n'
            '    {"year": 2023, "summary": "descripción breve de ese año"}\n'
            '  ],\n'
            '  "alerts": [\n'
            '    "alerta importante si hay algo que el usuario deba saber"\n'
            '  ],\n'
            '  "key_topics": ["tema1", "tema2", "tema3"]\n'
            '}'
        )

        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=1000,
                system=(
                    "Eres un asistente que analiza correos electrónicos para ayudar "
                    "a personas mayores a entender quién les escribe y qué les han "
                    "enviado. Responde siempre en español, con lenguaje simple y claro. "
                    "Nunca uses términos técnicos."
                ),
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except Exception as exc:
            return {
                "name": "", "relation_type": "otro",
                "summary": f"No se pudo generar el análisis: {exc}",
                "tone": "formal", "language": "español",
                "timeline": [], "alerts": [], "key_topics": [],
            }

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if PROFILES_PATH.exists():
            try:
                return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return _empty_profiles()

    def _save(self):
        PROFILES_PATH.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
