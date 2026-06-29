"""
CleanupScheduler: limpieza automática de Gmail con APScheduler BackgroundScheduler.

Configuración persistente en cleanup_schedule.json. El scheduler corre en un
hilo de fondo mientras la aplicación Streamlit está abierta; se reinicia
automáticamente al recargar la página si enabled=true.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("gmail_processor.scheduler")

_CONFIG_PATH = Path("cleanup_schedule.json")

_DAYS_ES = {
    "monday":    "lunes",
    "tuesday":   "martes",
    "wednesday": "miércoles",
    "thursday":  "jueves",
    "friday":    "viernes",
    "saturday":  "sábado",
    "sunday":    "domingo",
}


def _empty_config() -> dict:
    return {
        "enabled":         False,
        "frequency":       "weekly",
        "day_of_week":     "sunday",
        "hour":            3,
        "categories":      ["spam", "promociones"],
        "last_run":        None,
        "last_run_result": None,
        "next_run":        None,
    }


try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _APSCHEDULER_OK = True
except ImportError:
    _APSCHEDULER_OK = False


class CleanupScheduler:
    """
    Encapsula un BackgroundScheduler de APScheduler con configuración persistente.
    Usar como singleton (via st.cache_resource en app.py) para evitar múltiples instancias.
    """

    def __init__(self, config_path: str | Path = _CONFIG_PATH):
        self.config_path = Path(config_path)
        self.config      = self._load()
        self._scheduler  = None
        self._job        = None

        if _APSCHEDULER_OK:
            self._scheduler = BackgroundScheduler(daemon=True)

    # ── API pública ───────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return _APSCHEDULER_OK

    def configure(
        self,
        frequency:   str,
        categories:  list[str],
        hour:        int,
        day_of_week: str = "sunday",
        enabled:     bool = True,
    ) -> None:
        """Guarda configuración y reprograma si el scheduler está corriendo."""
        self.config.update({
            "frequency":   frequency,
            "categories":  categories,
            "hour":        hour,
            "day_of_week": day_of_week,
            "enabled":     enabled,
        })
        self._save()

        if enabled and self._scheduler and self._scheduler.running:
            self._reschedule()

    def start(self) -> bool:
        """Inicia el scheduler y programa la limpieza. Devuelve True si OK."""
        if not _APSCHEDULER_OK or self._scheduler is None:
            return False
        try:
            if not self._scheduler.running:
                self._scheduler.start()
            self._reschedule()
            self.config["enabled"] = True
            self._save()
            logger.info("Scheduler iniciado")
            return True
        except Exception as exc:
            logger.error(f"Error al iniciar scheduler: {exc}")
            return False

    def stop(self) -> None:
        """Pausa la limpieza programada sin borrar la configuración."""
        if self._job:
            try:
                self._job.remove()
            except Exception:
                pass
            self._job = None
        self.config["enabled"]  = False
        self.config["next_run"] = None
        self._save()
        logger.info("Scheduler detenido")

    def get_status(self) -> dict:
        """Devuelve config actualizada + next_run del job activo."""
        next_run = None
        if self._job:
            try:
                nrt = self._job.next_run_time
                next_run = nrt.isoformat() if nrt else None
            except Exception:
                pass
        return {**self.config, "next_run": next_run, "scheduler_available": _APSCHEDULER_OK}

    # ── Ejecución de limpieza ─────────────────────────────────────────────────

    def _run_cleanup(self) -> None:
        """Ejecuta la limpieza programada con todas las protecciones activas."""
        logger.info("Limpieza automática iniciada")
        try:
            from .auth import get_service
            from .actions import GmailActions
            from .cleanup_storage import StorageCleaner
            from .learning_engine import LearningEngine
            from .audit_log import AuditLogger

            service = get_service()
            actions = GmailActions(service, dry_run=False)
            engine  = LearningEngine()
            audit   = AuditLogger()
            cleaner = StorageCleaner(service, actions, engine=engine, audit=audit)
            result  = cleaner.run()
        except Exception as exc:
            result = {"error": str(exc)}
            logger.error(f"Error en limpieza automática: {exc}")

        self.config["last_run"]        = datetime.now().isoformat(timespec="seconds")
        self.config["last_run_result"] = result
        self._update_next_run()
        self._save()
        logger.info(f"Limpieza automática completada: {result}")

    # ── Internos ──────────────────────────────────────────────────────────────

    def _reschedule(self) -> None:
        if not self._scheduler:
            return
        if self._job:
            try:
                self._job.remove()
            except Exception:
                pass

        freq = self.config.get("frequency", "weekly")
        hour = int(self.config.get("hour", 3))
        dow  = self.config.get("day_of_week", "sunday")

        if freq == "daily":
            trigger = CronTrigger(hour=hour)
        elif freq == "weekly":
            trigger = CronTrigger(day_of_week=dow, hour=hour)
        else:   # monthly
            trigger = CronTrigger(day=1, hour=hour)

        self._job = self._scheduler.add_job(self._run_cleanup, trigger, misfire_grace_time=3600)
        self._update_next_run()
        self._save()

    def _update_next_run(self) -> None:
        if self._job:
            try:
                nrt = self._job.next_run_time
                self.config["next_run"] = nrt.isoformat() if nrt else None
            except Exception:
                self.config["next_run"] = None
        else:
            self.config["next_run"] = None

    def _load(self) -> dict:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return _empty_config()

    def _save(self) -> None:
        tmp = self.config_path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.config_path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise


def format_next_run(iso: str | None) -> str:
    """Convierte timestamp ISO a texto en español legible."""
    if not iso:
        return "No programada"
    try:
        dt    = datetime.fromisoformat(iso)
        now   = datetime.now()
        delta = dt - now
        if delta.total_seconds() < 0:
            return f"atrasada — {dt.strftime('%d/%m/%Y a las %H:%M')}"
        days  = delta.days
        if days == 0:
            h = delta.seconds // 3600
            if h == 0:
                m = delta.seconds // 60
                return f"en {m} minutos"
            return f"hoy a las {dt.strftime('%H:%M')}"
        elif days == 1:
            return f"mañana a las {dt.strftime('%H:%M')}"
        elif days < 7:
            dia = _DAYS_ES.get(dt.strftime("%A").lower(), dt.strftime("%A"))
            return f"el {dia} a las {dt.strftime('%H:%M')}"
        else:
            return dt.strftime("%d/%m/%Y a las %H:%M")
    except Exception:
        return iso[:16].replace("T", " ") if iso else "—"
