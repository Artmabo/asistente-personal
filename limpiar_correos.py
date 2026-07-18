import os
import sys
import time
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_MAX_RETRIES = 3
_BASE_DELAY  = 1.0  # seconds before first retry (doubles each attempt)


def _with_retry(fn, *, on_error_return):
    """Runs `fn()` with exponential-backoff retry on rate-limit/transient errors.

    Mirrors gmail_processor.actions.GmailActions._call so this standalone
    script doesn't hammer the Gmail API without backoff on 429/5xx responses.
    """
    delay = _BASE_DELAY
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn()
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status in (429, 500, 503) and attempt < _MAX_RETRIES:
                print(f"  Límite de tasa/error del servidor ({status}), "
                      f"reintento {attempt}/{_MAX_RETRIES} en {delay:.1f}s...")
                time.sleep(delay)
                delay *= 2
                continue
            print(f"  Error de API ({status}): {e}")
            return on_error_return
    return on_error_return

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


def mover_lote_a_papelera(service, ids: list) -> int:
    """Move up to 1000 IDs to trash via batchModify. Returns count successfully sent."""
    if not ids:
        return 0
    total = 0
    for i in range(0, len(ids), 1000):
        chunk = ids[i:i + 1000]
        ok = _with_retry(
            lambda: service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': chunk,
                    'addLabelIds': ['TRASH'],
                    'removeLabelIds': ['INBOX'],
                }
            ).execute() or True,
            on_error_return=False,
        )
        if ok:
            total += len(chunk)
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
            result = _with_retry(
                lambda: service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=500,
                    pageToken=page_token,
                ).execute(),
                on_error_return=None,
            )
            if result is None:
                print(f"  No se pudo listar la página {page_num}, deteniendo esta categoría.")
                break

            messages = result.get('messages', [])
            if not messages:
                if page_num == 1:
                    print("  No se encontraron correos.")
                break

            ids = [m['id'] for m in messages]
            if dry_run:
                print(f"  Página {page_num}: {len(ids)} correos encontrados (no se mueven).")
                exitos = len(ids)
            else:
                print(f"  Página {page_num}: {len(ids)} correos → enviando a papelera...", end="", flush=True)
                exitos = mover_lote_a_papelera(service, ids)
                print(f" {exitos} movidos.")
            cat_total += len(ids)
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


def limpiar_todo_basura(service, dry_run=False) -> dict:
    """Limpia spam + promociones + social + actualizaciones + foros en secuencia.

    Estas queries de categoría no tienen filtro de fecha/lectura — cubren
    TODO lo que Gmail haya clasificado en esa categoría. Usa dry_run=True
    primero para ver cuántos mensajes se verían afectados.
    """
    resultados = {}
    total_p = 0
    total_e = 0

    for cat in CATEGORIAS:
        print(f"\n  {'─'*44}")
        print(f"  {_NOMBRES_ES[cat].upper()}")
        r = limpiar_bandeja(service, categorias=[cat], dry_run=dry_run)
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

def limpiar_correos(service=None, meses=6, solo_no_leidos=True, dry_run=True):
    if service is None:
        service = obtener_servicio()
    fecha = (datetime.now() - timedelta(days=meses * 30)).strftime("%Y/%m/%d")
    q = f"before:{fecha}"
    if solo_no_leidos:
        q += " is:unread"
    return limpiar_bandeja(service, query_custom=q, dry_run=dry_run)


def borrar_correos_antiguos(service=None, dry_run=True):
    if service is None:
        service = obtener_servicio()
    return limpiar_correos(service=service, dry_run=dry_run)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Limpiar bandeja de Gmail")
    parser.add_argument(
        "--live", action="store_true",
        help="Ejecuta el borrado real. Sin esta bandera se corre en modo "
             "dry-run (solo cuenta, no mueve nada a la papelera).",
    )
    parser.add_argument(
        "--categoria", choices=list(CATEGORIAS.keys()), default=None,
        help="Categoría específica a limpiar (por defecto: no leídos > 6 meses)",
    )
    args = parser.parse_args()

    dry_run = not args.live
    if not dry_run:
        confirm = input(
            "Esto moverá correos reales a la papelera (no es una simulación). "
            "Escribe 'si' para continuar: "
        )
        if confirm.strip().lower() not in ("si", "sí", "yes", "y"):
            print("Cancelado.")
            sys.exit(0)

    svc = obtener_servicio()
    categorias = [args.categoria] if args.categoria else None
    resultado = limpiar_bandeja(svc, categorias=categorias, dry_run=dry_run)
    if resultado:
        accion = "encontrados" if dry_run else "enviados a papelera"
        print(f"\nTotal {accion}: {resultado['exitos']} / {resultado['procesados']}")
