import csv
import os
import sys
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_processor.cleanup_storage import protection_reason, _build_protected_domains
from gmail_processor.utils import get_header

_PROTECTED_DOMAINS = _build_protected_domains()


def _filtrar_protegidos(service, ids: list) -> tuple[list, list]:
    """Fetches From/Subject + labelIds for `ids` (one batch HTTP call) and splits
    them using the same hard-protection rules as StorageCleaner (STARRED/IMPORTANT,
    protected contacts/domains), so this bulk-delete path can't trash something the
    "smart" cleanup pipeline would have skipped.

    Returns (ids seguros para borrar, filas) where `filas` has one dict per id in
    the original order: {id, from, subject, protegido, motivo}.
    """
    if not ids:
        return [], []

    messages: dict[str, dict] = {}

    def _on_response(request_id, response, exception):
        if exception is None and response is not None:
            messages[request_id] = response

    batch = service.new_batch_http_request(callback=_on_response)
    for msg_id in ids:
        batch.add(
            service.users().messages().get(
                userId="me", id=msg_id, format="metadata",
                metadataHeaders=["From", "Subject"],
            ),
            request_id=msg_id,
        )
    try:
        batch.execute()
    except HttpError as e:
        print(f"  Advertencia: no se pudo verificar protección de {len(ids)} correos ({e}); se omiten por seguridad.")
        return [], [
            {"id": i, "from": "", "subject": "", "protegido": True, "motivo": f"error al verificar: {e}"}
            for i in ids
        ]

    seguros = []
    filas = []
    for msg_id in ids:
        msg = messages.get(msg_id)
        if msg is None:
            # Couldn't fetch metadata (e.g. deleted between list and get) — skip it,
            # don't assume it's safe to trash.
            filas.append({"id": msg_id, "from": "", "subject": "", "protegido": True, "motivo": "no se pudo obtener metadata"})
            continue
        headers = msg.get("payload", {}).get("headers", [])
        remitente = get_header(headers, "From") or ""
        asunto    = get_header(headers, "Subject") or ""
        motivo    = protection_reason(msg, _PROTECTED_DOMAINS)
        filas.append({"id": msg_id, "from": remitente, "subject": asunto, "protegido": motivo is not None, "motivo": motivo or ""})
        if motivo is None:
            seguros.append(msg_id)

    return seguros, filas

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
        except Exception as e:
            print(f"  Error en lote ({len(chunk)} mensajes): {e}")
    return total


def limpiar_bandeja(service, query_custom=None, categorias=None, dry_run=False, csv_path=None):
    """
    Mueve a la papelera los correos que coincidan con la query o categorías.

    Args:
        service:      servicio Gmail autenticado
        query_custom: query Gmail directa (se ignora si se pasan categorias)
        categorias:   lista de claves de CATEGORIAS (spam, promociones, etc.)
        dry_run:      si True, sólo cuenta mensajes sin moverlos
        csv_path:     si se indica, escribe un registro (remitente, asunto,
                      protegido/movido) de cada correo examinado, útil para
                      revisar antes o después de una limpieza

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
    csv_rows = [] if csv_path else None

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
            except Exception as e:
                print(f"  Error al listar página {page_num}: {e}")
                break

            messages = result.get('messages', [])
            if not messages:
                if page_num == 1:
                    print("  No se encontraron correos.")
                break

            ids_encontrados = [m['id'] for m in messages]
            ids, filas = _filtrar_protegidos(service, ids_encontrados)
            protegidos = len(filas) - len(ids)
            if protegidos:
                print(f"  Página {page_num}: {protegidos} correo(s) protegidos omitidos (STARRED/IMPORTANT/contacto o dominio protegido).")
            if dry_run:
                print(f"  Página {page_num}: {len(ids)} correos encontrados (no se mueven).")
                exitos = len(ids)
                accion_segura = "encontrado (dry-run)"
            else:
                print(f"  Página {page_num}: {len(ids)} correos → enviando a papelera...", end="", flush=True)
                exitos = mover_lote_a_papelera(service, ids)
                print(f" {exitos} movidos.")
                # batchModify chunks at 1000 and this loop pages at 500, so a page
                # is always a single chunk: exitos is either 0 or len(ids) here.
                accion_segura = "movido a papelera" if exitos == len(ids) else "error al mover"
            if csv_rows is not None:
                for fila in filas:
                    fila["accion"] = "protegido" if fila["protegido"] else accion_segura
                    fila["categoria"] = nombre
                csv_rows.extend(filas)
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

    if csv_rows is not None:
        try:
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "categoria", "from", "subject", "protegido", "motivo", "accion"])
                writer.writeheader()
                writer.writerows(csv_rows)
            print(f"\n  Registro CSV escrito en: {csv_path} ({len(csv_rows)} correos)")
        except OSError as e:
            print(f"\n  Advertencia: no se pudo escribir el CSV en {csv_path}: {e}")

    return {
        "procesados": total_procesados,
        "exitos":     total_exitos,
        "errores":    total_procesados - total_exitos,
    }


def limpiar_todo_basura(service, dry_run: bool = False) -> dict:
    """Limpia spam + promociones + social + actualizaciones + foros en secuencia."""
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
    parser.add_argument(
        "--export-csv", default=None, metavar="PATH",
        help="Escribe un registro CSV de cada correo examinado (remitente, asunto, protegido/movido)",
    )
    args = parser.parse_args()

    svc = obtener_servicio()
    categorias = [args.categoria] if args.categoria else None
    resultado = limpiar_bandeja(svc, categorias=categorias, dry_run=args.dry_run, csv_path=args.export_csv)
    if resultado:
        accion = "encontrados" if args.dry_run else "enviados a papelera"
        print(f"\nTotal {accion}: {resultado['exitos']} / {resultado['procesados']}")
