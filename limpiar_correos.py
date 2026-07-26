import os
import sys
import time
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

_MAX_RETRIES = 3
_BASE_DELAY  = 1.0   # seconds before first retry (doubles each attempt)


def obtener_servicio(creds_path="config/credentials.json", token_path="token.json"):
    """Builds an authenticated Gmail service. Delegates to gmail_processor.auth."""
    from gmail_processor.auth import get_service
    return get_service(creds_path=creds_path, token_path=token_path)


def _con_reintentos(func, descripcion: str):
    """Executes `func()` with exponential-backoff retry on rate-limit/transient
    errors (429/500/503), matching the retry policy GmailActions uses elsewhere
    in the app. Raises the last HttpError if all attempts are exhausted."""
    espera = _BASE_DELAY
    for intento in range(1, _MAX_RETRIES + 1):
        try:
            return func()
        except HttpError as e:
            status = int(e.resp.status)
            if status in (429, 500, 503) and intento < _MAX_RETRIES:
                print(f"  {descripcion}: error {status}, reintento {intento}/{_MAX_RETRIES} en {espera:.0f}s")
                time.sleep(espera)
                espera *= 2
                continue
            raise


def _filtrar_protegidos(service, ids: list) -> tuple:
    """Fetches each message's protection status and separates out anything
    hard-protected (STARRED, IMPORTANT, protected contact/domain — see
    gmail_processor/protection.py) so it's never sent to trash by this script.

    Returns (ids_seguros, cantidad_protegidos, cantidad_errores).
    """
    from gmail_processor.protection import protection_reason

    seguros    = []
    protegidos = 0
    errores    = 0
    for msg_id in ids:
        try:
            msg = _con_reintentos(
                lambda: service.users().messages().get(
                    userId="me", id=msg_id,
                    format="metadata", metadataHeaders=["From", "Subject"],
                ).execute(),
                f"Consultar mensaje {msg_id}",
            )
        except HttpError as e:
            # Can't confirm protection status — skip it rather than risk
            # trashing something protected; it'll be picked up on a future run.
            print(f"  No se pudo consultar {msg_id}, se omite por seguridad: {e}")
            errores += 1
            continue

        if protection_reason(msg):
            protegidos += 1
        else:
            seguros.append(msg_id)
        time.sleep(0.02)

    return seguros, protegidos, errores


def mover_lote_a_papelera(service, ids: list) -> int:
    """Move up to 1000 IDs to trash via batchModify. Returns count successfully sent."""
    if not ids:
        return 0
    total = 0
    for i in range(0, len(ids), 1000):
        chunk = ids[i:i + 1000]
        try:
            _con_reintentos(
                lambda: service.users().messages().batchModify(
                    userId='me',
                    body={
                        'ids': chunk,
                        'addLabelIds': ['TRASH'],
                        'removeLabelIds': ['INBOX'],
                    }
                ).execute(),
                f"Mover lote de {len(chunk)} mensajes",
            )
            total += len(chunk)
        except HttpError as e:
            print(f"  Error en lote ({len(chunk)} mensajes): {e}")
    return total


def limpiar_bandeja(service, query_custom=None, categorias=None, dry_run=False):
    """
    Mueve a la papelera los correos que coincidan con la query o categorías.
    Los mensajes protegidos (STARRED, IMPORTANT, contactos/dominios protegidos
    en rules.py) nunca se mueven, incluso en modo no-dry-run.

    Args:
        service:      servicio Gmail autenticado
        query_custom: query Gmail directa (se ignora si se pasan categorias)
        categorias:   lista de claves de CATEGORIAS (spam, promociones, etc.)
        dry_run:      si True, sólo cuenta mensajes sin moverlos

    Returns:
        {'procesados': int, 'exitos': int, 'protegidos': int, 'errores': int}
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
    total_protegidos = 0
    total_errores = 0

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
                result = _con_reintentos(
                    lambda: service.users().messages().list(
                        userId='me',
                        q=query,
                        maxResults=500,
                        pageToken=page_token,
                    ).execute(),
                    f"Listar página {page_num}",
                )
            except HttpError as e:
                print(f"  Error al listar página {page_num}: {e}")
                total_errores += 1
                break

            messages = result.get('messages', [])
            if not messages:
                if page_num == 1:
                    print("  No se encontraron correos.")
                break

            ids = [m['id'] for m in messages]
            ids_seguros, protegidos, errores_filtro = _filtrar_protegidos(service, ids)
            if protegidos:
                print(f"  {protegidos} protegidos (STARRED/IMPORTANT/contacto) — omitidos.")

            if dry_run:
                print(f"  Página {page_num}: {len(ids_seguros)} correos encontrados (no se mueven).")
                exitos = len(ids_seguros)
            else:
                print(f"  Página {page_num}: {len(ids_seguros)} correos → enviando a papelera...", end="", flush=True)
                exitos = mover_lote_a_papelera(service, ids_seguros)
                print(f" {exitos} movidos.")
            cat_total += len(ids)
            cat_exitos += exitos
            cat_protegidos += protegidos
            total_errores += errores_filtro

            page_token = result.get('nextPageToken')
            if not page_token:
                break

        if len(queries) > 1:
            nombre_es = _NOMBRES_ES.get(nombre, nombre)
            label = "encontrados" if dry_run else "enviados a papelera"
            print(f"  [{nombre_es}] {cat_exitos}/{cat_total} {label}  ({cat_protegidos} protegidos)")

        total_procesados += cat_total
        total_exitos += cat_exitos
        total_protegidos += cat_protegidos

    return {
        "procesados": total_procesados,
        "exitos":     total_exitos,
        "protegidos": total_protegidos,
        "errores":    max(0, total_procesados - total_exitos - total_protegidos) + total_errores,
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
        "--si", action="store_true",
        help="Omite la confirmación interactiva antes de una ejecución en vivo",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.si:
        respuesta = input(
            "\n  Esto moverá correos reales a la papelera (recuperables 30 días).\n"
            "  Escribe 'SI' para continuar en modo LIVE, o Enter para cancelar: "
        ).strip()
        if respuesta != "SI":
            print("  Cancelado. Usa --dry-run para previsualizar sin cambios.")
            sys.exit(0)

    svc = obtener_servicio()
    categorias = [args.categoria] if args.categoria else None
    resultado = limpiar_bandeja(svc, categorias=categorias, dry_run=args.dry_run)
    if resultado:
        accion = "encontrados" if args.dry_run else "enviados a papelera"
        print(f"\nTotal {accion}: {resultado['exitos']} / {resultado['procesados']}"
              f"  (protegidos: {resultado['protegidos']}, errores: {resultado['errores']})")
