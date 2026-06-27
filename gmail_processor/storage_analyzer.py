"""
StorageAnalyzer: estimación de uso de almacenamiento de Gmail y tamaño de limpieza.

get_storage_summary() usa el perfil de Gmail para mensajes totales y,
si las credenciales tienen acceso a Drive, también devuelve cuota en GB.

estimate_cleanup_size() lista todos los mensajes de cada categoría,
muestrea sizeEstimate de hasta 50 mensajes y extrapola para el total.
"""
import time
from googleapiclient.errors import HttpError

_CATEGORY_QUERIES: dict[str, str] = {
    "spam":            "in:spam",
    "promociones":     "category:promotions",
    "social":          "category:social",
    "actualizaciones": "category:updates",
    "foros":           "category:forums",
}

_SAMPLE_PER_CAT = 50
_AVG_BYTES_FALLBACK = 25_000   # 25 KB si no hay muestra


class StorageAnalyzer:
    def __init__(self, service):
        self.svc = service

    def get_storage_summary(self) -> dict:
        """
        Devuelve uso de Gmail. La cuota en GB requiere acceso a Drive API;
        degrada sin error si no está disponible.
        """
        result: dict = {}

        try:
            profile = self.svc.users().getProfile(userId="me").execute()
            result["messages_total"] = profile.get("messagesTotal", 0)
            result["threads_total"]  = profile.get("threadsTotal",  0)
        except HttpError as e:
            result["messages_total"] = 0
            result["threads_total"]  = 0
            result["error_profile"]  = str(e)

        # Cuota de almacenamiento vía Drive API (scope opcional)
        try:
            from googleapiclient.discovery import build as _build
            creds = getattr(self.svc._http, "credentials", None)
            if creds is None:
                raise RuntimeError("no credentials")
            drive = _build("drive", "v3", credentials=creds)
            about = drive.about().get(fields="storageQuota").execute()
            quota = about.get("storageQuota", {})
            used_bytes  = int(quota.get("usage", 0))
            total_bytes = int(quota.get("limit", 0))
            result["used_gb"]      = round(used_bytes  / 1e9, 2)
            result["total_gb"]     = round(total_bytes / 1e9, 1)
            result["percent_used"] = int(100 * used_bytes / total_bytes) if total_bytes else 0
        except Exception:
            result["used_gb"]      = None
            result["total_gb"]     = None
            result["percent_used"] = None

        return result

    def estimate_cleanup_size(self, categories: list[str] | None = None) -> dict:
        """
        Estima el espacio que se liberaría limpiando las categorías dadas.
        Lista todos los mensajes, toma muestra para sizeEstimate, extrapola.
        Devuelve {cat: {count, size_mb}, ..., total_mb, total_gb}.
        """
        if categories is None:
            categories = list(_CATEGORY_QUERIES.keys())

        result: dict = {}
        total_mb = 0

        for cat in categories:
            query = _CATEGORY_QUERIES.get(cat)
            if not query:
                continue

            all_ids, count = self._list_all_ids(query)
            if count == 0:
                result[cat] = {"count": 0, "size_mb": 0}
                continue

            # Muestrear sizeEstimate
            sample_ids  = all_ids[:_SAMPLE_PER_CAT]
            total_bytes = 0
            sampled     = 0
            for msg_id in sample_ids:
                try:
                    msg = self.svc.users().messages().get(
                        userId="me", id=msg_id, format="minimal"
                    ).execute()
                    total_bytes += msg.get("sizeEstimate", 0)
                    sampled     += 1
                    time.sleep(0.02)
                except HttpError:
                    continue

            avg_bytes = total_bytes / sampled if sampled else _AVG_BYTES_FALLBACK
            size_mb   = int(count * avg_bytes / 1e6)

            result[cat] = {"count": count, "size_mb": size_mb}
            total_mb   += size_mb

        result["total_mb"] = total_mb
        result["total_gb"] = round(total_mb / 1000, 2)
        return result

    def get_category_counts(self, categories: list[str] | None = None) -> dict[str, int]:
        """Returns approximate message counts per category without fetching all IDs.

        Uses Gmail's resultSizeEstimate for a fast, single-API-call-per-category
        count. Suitable for dashboard stats where exact counts are not critical.
        """
        if categories is None:
            categories = list(_CATEGORY_QUERIES.keys())
        result: dict[str, int] = {}
        for cat in categories:
            query = _CATEGORY_QUERIES.get(cat)
            if not query:
                continue
            try:
                resp = self.svc.users().messages().list(
                    userId="me", q=query, maxResults=1,
                ).execute()
                result[cat] = resp.get("resultSizeEstimate", 0)
            except HttpError:
                result[cat] = 0
        return result

    def _list_all_ids(self, query: str, max_ids: int = 5_000) -> tuple[list[str], int]:
        """Lista los IDs de mensajes que coinciden con la query, hasta max_ids."""
        ids: list[str] = []
        page_token     = None

        while len(ids) < max_ids:
            try:
                resp = self.svc.users().messages().list(
                    userId="me", q=query, maxResults=500, pageToken=page_token,
                ).execute()
            except HttpError:
                break

            msgs = resp.get("messages", [])
            if not msgs:
                break

            ids.extend(m["id"] for m in msgs)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
            time.sleep(0.1)

        return ids[:max_ids], len(ids[:max_ids])
