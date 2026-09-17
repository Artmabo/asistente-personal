import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_processor import rules as cfg
from gmail_processor.utils import (
    build_protected_domains,
    extract_email_address,
    get_header,
    protection_reason,
)

_LAST_BATCH_PATH = Path("last_trash_batch.json")

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


def mover_lote_a_papelera(service, ids: list) -> list:
    """Move up to 1000 IDs to trash via batchModify. Returns the IDs successfully sent."""
    if not ids:
        return []
    enviados = []
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
            enviados.extend(chunk)
        except HttpError as e:
            print(f"  Error en lote ({len(chunk)} mensajes): {e}")
    return enviados


def _fetch_metadata_batch(service, ids: list) -> dict:
    """Fetches the From header + labelIds for each id in ONE batched HTTP
    request instead of one messages().get() call per id — the same pattern
    already used by storage_analyzer.py for sampling message sizes."""
    results: dict = {}

    def _on_response(request_id, response, exception):
        if exception is None and response is not None:
            results[request_id] = response

    batch = service.new_batch_http_request(callback=_on_response)
    for msg_id in ids:
        batch.add(
            service.users().messages().get(
                userId='me', id=msg_id, format='metadata', metadataHeaders=['From'],
            ),
            request_id=msg_id,
        )
    try:
        batch.execute()
    except HttpError as e:
        print(f"  Error al verificar protección de {len(ids)} mensajes: {e}")
    return results


def _filtrar_protegidos(service, ids: list) -> tuple:
    """Splits `ids` into (ids_seguros, cantidad_protegidos).

    Gmail's category/spam classification is not aware of CONTACT_RULES or
    DOMAIN_RULES, so a protected contact's mail can still land in Promotions,
    Social, etc. This check is what processor.py and cleanup_storage.py
    already do before trashing anything — limpiar_bandeja() used to skip it
    entirely, so its one-click "clean category" actions (used directly by
    both the web UI and the CLI menu) could trash mail from a protected
    contact, bank, or government domain with no way to tell in advance.
    """
    if not ids:
        return [], 0

    protected_domains = build_protected_domains(cfg.DOMAIN_RULES)
    metadata = _fetch_metadata_batch(service, ids)

    ids_seguros = []
    protegidos  = 0
    for msg_id in ids:
        msg = metadata.get(msg_id)
        if msg is None:
            # Could not verify (batch sub-request failed) — err on the side
            # of caution and don't trash it.
            protegidos += 1
            continue
        headers   = msg.get("payload", {}).get("headers", [])
        label_ids = msg.get("labelIds", [])
        email     = extract_email_address(get_header(headers, "From"))
        domain    = email.split("@")[-1] if "@" in email else ""
        if protection_reason(email, domain, label_ids, cfg.CONTACT_RULES, protected_domains):
            protegidos += 1
        else:
            ids_seguros.append(msg_id)
    return ids_seguros, protegidos


# ── Deshacer última limpieza ───────────────────────────────────────────────────

def _registrar_lote_papelera(ids: list, contexto: str) -> None:
    """Persists the IDs just trashed so they can be restored with --restore-last."""
    if not ids:
        return
    data = {
        "ts":       datetime.now().isoformat(timespec="seconds"),
        "contexto": contexto,
        "ids":      ids,
    }
    tmp = _LAST_BATCH_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_LAST_BATCH_PATH)
    except OSError as e:
        print(f"  No se pudo guardar el registro para deshacer: {e}")


def restaurar_ultimo_lote(service) -> dict:
    """Moves the most recently trashed batch back to the inbox.

    Safety net for the bulk "clean category" actions: since Gmail keeps
    trashed mail for 30 days anyway, this just makes recovering from an
    unwanted bulk cleanup a single command instead of a manual search in
    Gmail's trash.
    """
    if not _LAST_BATCH_PATH.exists():
        return {"error": "No hay ningún lote reciente registrado para restaurar."}

    try:
        data = json.loads(_LAST_BATCH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"No se pudo leer el registro del último lote: {e}"}

    ids = data.get("ids", [])
    if not ids:
        return {"error": "El registro del último lote está vacío."}

    restaurados = 0
    for i in range(0, len(ids), 1000):
        chunk = ids[i:i + 1000]
        try:
            service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': chunk,
                    'addLabelIds': ['INBOX'],
                    'removeLabelIds': ['TRASH'],
                }
            ).execute()
            restaurados += len(chunk)
        except HttpError as e:
            print(f"  Error al restaurar lote ({len(chunk)} mensajes): {e}")

    _LAST_BATCH_PATH.unlink(missing_ok=True)
    return {
        "ts":          data.get("ts", ""),
        "contexto":    data.get("contexto", ""),
        "total":       len(ids),
        "restaurados": restaurados,
    }


def limpiar_bandeja(service, query_custom=None, categorias=None, dry_run=False, registrar_lote=True):
    """
    Mueve a la papelera los correos que coincidan con la query o categorías.

    Args:
        service:        servicio Gmail autenticado
        query_custom:   query Gmail directa (se ignora si se pasan categorias)
        categorias:     lista de claves de CATEGORIAS (spam, promociones, etc.)
        dry_run:        si True, sólo cuenta mensajes sin moverlos
        registrar_lote: si True (default), guarda los IDs movidos para poder
                        deshacerlos con --restore-last. limpiar_todo_basura()
                        pasa False aquí y registra un único lote combinado al
                        final, para que "deshacer" cubra todas las categorías.

    Returns:
        {'procesados': int, 'exitos': int, 'protegidos': int, 'errores': int, '_ids': list[str]}
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
    total_exitos     = 0
    total_protegidos = 0
    trashed_ids: list = []

    for nombre, query in queries.items():
        print(f"\n  Buscando: {query}")
        page_token = None
        page_num = 0
        cat_total = 0
        cat_exitos = 0
        cat_protegidos = 0

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
                print(f"  Página {page_num}: {protegidos} protegidos (contacto/dominio importante) — omitidos.")

            if dry_run:
                print(f"  Página {page_num}: {len(ids_seguros)} correos encontrados (no se mueven).")
                exitos = len(ids_seguros)
            else:
                print(f"  Página {page_num}: {len(ids_seguros)} correos → enviando a papelera...", end="", flush=True)
                enviados = mover_lote_a_papelera(service, ids_seguros)
                exitos = len(enviados)
                trashed_ids.extend(enviados)
                print(f" {exitos} movidos.")
            cat_total += len(ids)
            cat_exitos += exitos
            cat_protegidos += protegidos

            page_token = result.get('nextPageToken')
            if not page_token:
                break

        if len(queries) > 1:
            nombre_es = _NOMBRES_ES.get(nombre, nombre)
            label = "encontrados" if dry_run else "enviados a papelera"
            print(f"  [{nombre_es}] {cat_exitos}/{cat_total} {label}")

        total_procesados += cat_total
        total_exitos     += cat_exitos
        total_protegidos += cat_protegidos

    if not dry_run and trashed_ids and registrar_lote:
        contexto = ", ".join(categorias) if categorias else (query_custom or "personalizado")
        _registrar_lote_papelera(trashed_ids, contexto)

    return {
        "procesados": total_procesados,
        "exitos":     total_exitos,
        "protegidos": total_protegidos,
        "errores":    total_procesados - total_exitos - total_protegidos,
        "_ids":       trashed_ids,
    }


def limpiar_todo_basura(service) -> dict:
    """Limpia spam + promociones + social + actualizaciones + foros en secuencia."""
    resultados = {}
    total_p = 0
    total_e = 0
    todos_los_ids: list = []

    for cat in CATEGORIAS:
        print(f"\n  {'─'*44}")
        print(f"  {_NOMBRES_ES[cat].upper()}")
        r = limpiar_bandeja(service, categorias=[cat], registrar_lote=False)
        resultados[cat] = r
        total_p += r['procesados']
        total_e += r['exitos']
        todos_los_ids.extend(r.get('_ids', []))

    if todos_los_ids:
        _registrar_lote_papelera(todos_los_ids, "todas las categorías")

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

def limpiar_correos(service=None, meses=6, solo_no_leidos=True, aggressive=False):
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
        "--restore-last", action="store_true",
        help="Deshace el último lote enviado a la papelera por este script "
             "(devuelve los correos a la bandeja de entrada)",
    )
    args = parser.parse_args()

    svc = obtener_servicio()

    if args.restore_last:
        r = restaurar_ultimo_lote(svc)
        if "error" in r:
            print(f"\n{r['error']}")
        else:
            print(
                f"\nLote del {r['ts']} ({r['contexto']}): "
                f"{r['restaurados']}/{r['total']} correos restaurados a la bandeja de entrada."
            )
        sys.exit(0)

    categorias = [args.categoria] if args.categoria else None
    resultado = limpiar_bandeja(svc, categorias=categorias, dry_run=args.dry_run)
    if resultado:
        accion = "encontrados" if args.dry_run else "enviados a papelera"
        print(f"\nTotal {accion}: {resultado['exitos']} / {resultado['procesados']}")
        if resultado.get("protegidos"):
            print(f"Protegidos (omitidos): {resultado['protegidos']}")
