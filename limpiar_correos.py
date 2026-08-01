import os
import sys
import time
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_MAX_RETRIES = 3
_BASE_DELAY  = 1.0   # seconds before first retry (doubles each attempt)
_BATCH_SLEEP = 0.2   # seconds between list-pagination calls (rate-limit headroom)


def _con_reintentos(fn, descripcion=""):
    """Ejecuta fn() con reintentos y backoff exponencial ante rate limits/errores transitorios."""
    delay = _BASE_DELAY
    for intento in range(1, _MAX_RETRIES + 1):
        try:
            return fn()
        except HttpError as e:
            status = int(e.resp.status)
            if status in (403, 429, 500, 503) and intento < _MAX_RETRIES:
                print(f"  {descripcion}: error {status}, reintento {intento}/{_MAX_RETRIES} en {delay:.0f}s")
                time.sleep(delay)
                delay *= 2
                continue
            raise

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
            _con_reintentos(
                lambda: service.users().messages().batchModify(
                    userId='me',
                    body={
                        'ids': chunk,
                        'addLabelIds': ['TRASH'],
                        'removeLabelIds': ['INBOX'],
                    }
                ).execute(),
                descripcion=f"lote de {len(chunk)} mensajes",
            )
            total += len(chunk)
        except HttpError as e:
            print(f"  Error en lote ({len(chunk)} mensajes): {e}")
        if i + 1000 < len(ids):
            time.sleep(_BATCH_SLEEP)
    return total


def _muestra_ejemplos(service, ids: list, n: int = 3) -> list:
    """Obtiene De/Asunto de hasta n mensajes en una sola llamada batch — usado
    en dry-run para que el usuario vea QUÉ se eliminaría, no solo cuántos."""
    sample_ids = ids[:n]
    if not sample_ids:
        return []

    ejemplos = []

    def _cb(request_id, response, exception):
        if exception is not None or response is None:
            return
        headers = {h["name"]: h["value"] for h in response.get("payload", {}).get("headers", [])}
        ejemplos.append({
            "de":      headers.get("From", "?"),
            "asunto":  headers.get("Subject", "(sin asunto)"),
        })

    batch = service.new_batch_http_request(callback=_cb)
    for mid in sample_ids:
        batch.add(
            service.users().messages().get(
                userId="me", id=mid, format="metadata",
                metadataHeaders=["From", "Subject"],
            ),
            request_id=mid,
        )
    try:
        _con_reintentos(batch.execute, descripcion="obtener muestra")
    except HttpError:
        return []
    return ejemplos


def limpiar_bandeja(service, query_custom=None, categorias=None, dry_run=False):
    """
    Mueve a la papelera los correos que coincidan con la query o categorías.

    Args:
        service:      servicio Gmail autenticado
        query_custom: query Gmail directa (se ignora si se pasan categorias)
        categorias:   lista de claves de CATEGORIAS (spam, promociones, etc.)
        dry_run:      si True, sólo cuenta mensajes sin moverlos (muestra una
                      pequeña muestra de remitente/asunto para verificar antes
                      de ejecutar en modo real)

    Returns:
        {'procesados': int, 'exitos': int, 'errores': int, 'muestra': list}
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
    incompleto = False
    muestra = []

    for nombre, query in queries.items():
        print(f"\n  Buscando: {query}")
        page_token = None
        page_num = 0
        cat_total = 0
        cat_exitos = 0

        while True:
            page_num += 1
            if page_num > 1:
                time.sleep(_BATCH_SLEEP)
            try:
                result = _con_reintentos(
                    lambda: service.users().messages().list(
                        userId='me',
                        q=query,
                        maxResults=500,
                        pageToken=page_token,
                    ).execute(),
                    descripcion=f"listar página {page_num}",
                )
            except HttpError as e:
                print(f"  Error al listar página {page_num}: {e}")
                print(f"  ⚠ Puede haber más correos sin procesar para '{nombre}' — quedó incompleto.")
                incompleto = True
                break

            messages = result.get('messages', [])
            if not messages:
                if page_num == 1:
                    print("  No se encontraron correos.")
                break

            ids = [m['id'] for m in messages]
            if dry_run:
                print(f"  Página {page_num}: {len(ids)} correos encontrados (no se mueven).")
                if page_num == 1:
                    ejemplos = _muestra_ejemplos(service, ids)
                    muestra.extend(ejemplos)
                    for ej in ejemplos:
                        print(f"    · {ej['de']} — {ej['asunto']}")
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
        "procesados":  total_procesados,
        "exitos":      total_exitos,
        "errores":     total_procesados - total_exitos,
        "incompleto":  incompleto,
        "muestra":     muestra,
    }


def limpiar_todo_basura(service) -> dict:
    """Limpia spam + promociones + social + actualizaciones + foros en secuencia."""
    resultados = {}
    total_p = 0
    total_e = 0

    incompleto = False
    for cat in CATEGORIAS:
        print(f"\n  {'─'*44}")
        print(f"  {_NOMBRES_ES[cat].upper()}")
        r = limpiar_bandeja(service, categorias=[cat])
        resultados[cat] = r
        total_p += r['procesados']
        total_e += r['exitos']
        incompleto = incompleto or r.get('incompleto', False)

    print(f"\n  {'═'*44}")
    print("  RESUMEN FINAL")
    print(f"  {'═'*44}")
    for cat, r in resultados.items():
        barra = f"{r['exitos']}/{r['procesados']}"
        marca = "  ⚠ incompleto" if r.get('incompleto') else ""
        print(f"  {_NOMBRES_ES[cat]:<18} {barra:>12}  enviados a papelera{marca}")
    print(f"  {'─'*44}")
    total_barra = f"{total_e}/{total_p}"
    print(f"  {'TOTAL':<18} {total_barra:>12}")
    if incompleto:
        print("  ⚠ Uno o más targets quedaron incompletos por errores de red/API.")

    return {"procesados": total_p, "exitos": total_e, "incompleto": incompleto}


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
    args = parser.parse_args()

    svc = obtener_servicio()
    categorias = [args.categoria] if args.categoria else None
    resultado = limpiar_bandeja(svc, categorias=categorias, dry_run=args.dry_run)
    if resultado:
        accion = "encontrados" if args.dry_run else "enviados a papelera"
        print(f"\nTotal {accion}: {resultado['exitos']} / {resultado['procesados']}")
        if resultado.get('incompleto'):
            print("⚠ El proceso quedó incompleto por errores de red/API — vuelve a ejecutarlo.")
