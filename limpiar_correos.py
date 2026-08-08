import os
import sys
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_processor import rules as _cfg
from gmail_processor.utils import get_header, extract_email_address

CATEGORIAS = {
    "spam":            "in:spam",
    "promociones":     "category:promotions",
    "social":          "category:social",
    "actualizaciones": "category:updates",
    "foros":           "category:forums",
}

_NOMBRES_ES = {
    "spam":            "Spam",
    "promociones":     "Promociones",
    "social":          "Social",
    "actualizaciones": "Actualizaciones",
    "foros":           "Foros",
}


def obtener_servicio(creds_path="config/credentials.json", token_path="token.json"):
    """Builds an authenticated Gmail service. Delegates to gmail_processor.auth."""
    from gmail_processor.auth import get_service
    return get_service(creds_path=creds_path, token_path=token_path)


def _es_protegido(message: dict) -> bool:
    """Mirrors gmail_processor.cleanup_storage's hard-protection rules: never
    trash starred/important mail, protected contacts, or mark_important domains."""
    label_ids = message.get("labelIds", [])
    if "STARRED" in label_ids or "IMPORTANT" in label_ids:
        return True

    headers = message.get("payload", {}).get("headers", [])
    sender  = extract_email_address(get_header(headers, "From"))
    domain  = sender.split("@")[-1] if "@" in sender else ""

    if sender in _cfg.CONTACT_RULES or (domain and f"@{domain}" in _cfg.CONTACT_RULES):
        return True
    for rule in _cfg.DOMAIN_RULES:
        if rule.get("action") == "mark_important" and domain in rule.get("domains", []):
            return True
    if domain in set(_cfg.CLEANUP_RULES.get("safe_domains", [])):
        return True
    return False


def _filtrar_protegidos(service, ids: list) -> tuple:
    """Fetches metadata for `ids` and drops the ones that are hard-protected.

    Errs on the side of caution: any id whose metadata couldn't be confirmed
    (batch/API failure) is treated as protected and left out of the trash list.
    Returns (ids_seguros, cantidad_protegidos).
    """
    if not ids:
        return [], 0

    messages: dict = {}

    def _on_response(request_id, response, exception):
        if exception is None and response is not None:
            messages[request_id] = response

    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        batch = service.new_batch_http_request(callback=_on_response)
        for msg_id in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me", id=msg_id, format="metadata",
                    metadataHeaders=["From"],
                ),
                request_id=msg_id,
            )
        try:
            batch.execute()
        except HttpError as e:
            print(f"  Error al verificar protección de {len(chunk)} mensajes: {e}")

    seguros    = [mid for mid in ids if mid in messages and not _es_protegido(messages[mid])]
    protegidos = len(ids) - len(seguros)
    return seguros, protegidos


def mover_lote_a_papelera(service, ids: list) -> int:
    """Move up to 1000 IDs to trash via batchModify. Returns count successfully sent."""
    if not ids:
        return 0
    total = 0
    for i in range(0, len(ids), 1000):
        chunk = ids[i:i + 1000]
        try:
            service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': chunk,
                    'addLabelIds': ['TRASH'],
                    'removeLabelIds': ['INBOX'],
                }
            ).execute()
            total += len(chunk)
        except HttpError as e:
            print(f"  Error en lote ({len(chunk)} mensajes): {e}")
    return total


def limpiar_bandeja(service, query_custom=None, categorias=None, dry_run=False):
    """
    Mueve a la papelera los correos que coincidan con la query o categorías.

    Args:
        service:      servicio Gmail autenticado
        query_custom: query Gmail directa (se ignora si se pasan categorias)
        categorias:   lista de claves de CATEGORIAS (spam, promociones, etc.)
        dry_run:      si True, sólo cuenta mensajes sin moverlos

    Returns:
        {'procesados': int, 'exitos': int, 'errores': int}
    """
    if categorias:
        queries = {cat: CATEGORIAS[cat] for cat in categorias if cat in CATEGORIAS}
    elif query_custom:
        queries = {"consulta": query_custom}
    else:
        fecha = (datetime.now() - timedelta(days=180)).strftime("%Y/%m/%d")
        queries = {"consulta": f"before:{fecha} is:unread"}

    if dry_run:
        print("  [DRY RUN] Solo contando mensajes, no se moverá nada.")

    total_procesados = 0
    total_exitos = 0

    for nombre, query in queries.items():
        print(f"\n  Buscando: {query}")
        page_token = None
        page_num = 0
        cat_total = 0
        cat_exitos = 0

        while True:
            page_num += 1
            try:
                result = service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=500,
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                print(f"  Error al listar página {page_num}: {e}")
                break

            messages = result.get('messages', [])
            if not messages:
                if page_num == 1:
                    print("  No se encontraron correos.")
                break

            ids = [m['id'] for m in messages]
            ids_seguros, protegidos = _filtrar_protegidos(service, ids)
            if protegidos:
                print(f"  Página {page_num}: {protegidos} protegidos (destacado/importante/contacto) — se conservan.")

            if dry_run:
                print(f"  Página {page_num}: {len(ids_seguros)} correos encontrados (no se mueven).")
                exitos = len(ids_seguros)
            else:
                print(f"  Página {page_num}: {len(ids_seguros)} correos → enviando a papelera...", end="", flush=True)
                exitos = mover_lote_a_papelera(service, ids_seguros)
                print(f" {exitos} movidos.")
            cat_total += len(ids_seguros)
            cat_exitos += exitos

            page_token = result.get('nextPageToken')
            if not page_token:
                break

        if len(queries) > 1:
            nombre_es = _NOMBRES_ES.get(nombre, nombre)
            label = "encontrados" if dry_run else "enviados a papelera"
            print(f"  [{nombre_es}] {cat_exitos}/{cat_total} {label}")

        total_procesados += cat_total
        total_exitos += cat_exitos

    return {
        "procesados": total_procesados,
        "exitos":     total_exitos,
        "errores":    total_procesados - total_exitos,
    }


def limpiar_todo_basura(service) -> dict:
    """Limpia spam + promociones + social + actualizaciones + foros en secuencia."""
    resultados = {}
    total_p = 0
    total_e = 0

    for cat in CATEGORIAS:
        print(f"\n  {'─'*44}")
        print(f"  {_NOMBRES_ES[cat].upper()}")
        r = limpiar_bandeja(service, categorias=[cat])
        resultados[cat] = r
        total_p += r['procesados']
        total_e += r['exitos']

    print(f"\n  {'═'*44}")
    print("  RESUMEN FINAL")
    print(f"  {'═'*44}")
    for cat, r in resultados.items():
        barra = f"{r['exitos']}/{r['procesados']}"
        print(f"  {_NOMBRES_ES[cat]:<18} {barra:>12}  enviados a papelera")
    print(f"  {'─'*44}")
    total_barra = f"{total_e}/{total_p}"
    print(f"  {'TOTAL':<18} {total_barra:>12}")

    return {"procesados": total_p, "exitos": total_e}


# ── Compatibilidad con versiones anteriores ───────────────────────────────────

def limpiar_correos(service=None, meses=6, solo_no_leidos=True):
    if service is None:
        service = obtener_servicio()
    fecha = (datetime.now() - timedelta(days=meses * 30)).strftime("%Y/%m/%d")
    q = f"before:{fecha}"
    if solo_no_leidos:
        q += " is:unread"
    return limpiar_bandeja(service, query_custom=q)


def borrar_correos_antiguos(service=None):
    if service is None:
        service = obtener_servicio()
    return limpiar_correos(service=service)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Limpiar bandeja de Gmail")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo cuenta los mensajes que se eliminarían, sin moverlos",
    )
    parser.add_argument(
        "--categoria", choices=list(CATEGORIAS.keys()), default=None,
        help="Categoría específica a limpiar (por defecto: no leídos > 6 meses)",
    )
    args = parser.parse_args()

    svc = obtener_servicio()
    categorias = [args.categoria] if args.categoria else None
    resultado = limpiar_bandeja(svc, categorias=categorias, dry_run=args.dry_run)
    if resultado:
        accion = "encontrados" if args.dry_run else "enviados a papelera"
        print(f"\nTotal {accion}: {resultado['exitos']} / {resultado['procesados']}")
