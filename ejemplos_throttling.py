#!/usr/bin/env python
"""
Ejemplos de uso de limpiar_correos.py y de cómo se manejan los errores
403/429 de la API de Gmail.

Nota: limpiar_correos.py reintenta automáticamente con backoff exponencial
(_execute_with_retry, hasta 3 intentos) ante errores 403/429/500/503, y
omite correos de remitentes/dominios protegidos antes de enviarlos a la
papelera (_filtrar_protegidos). No hay parámetros de "modo agresivo",
PAGE_DELAY/REQUEST_DELAY/BATCH_SIZE ni un circuit breaker configurables:
ese comportamiento no existe en este proyecto — este archivo antes lo
describía por error.
"""

from googleapiclient.errors import HttpError

from limpiar_correos import limpiar_correos
from asistente_personal import get_gmail_service


def ejemplo_1_limpieza_por_defecto():
    """Limpieza estándar: no leídos con más de 6 meses de antigüedad."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Limpieza por defecto")
    print("="*60)
    print("✅ Reintenta automáticamente ante 403/429/500/503 (backoff exponencial)")
    print("✅ Omite remitentes/dominios protegidos (CONTACT_RULES, DOMAIN_RULES)")

    resultado = limpiar_correos(meses=6, solo_no_leidos=True)

    print(f"\n✓ Resultado: {resultado['exitos']} correos eliminados")


def ejemplo_2_listar_sin_borrar():
    """Solo verificar cuántos correos se encontrarían sin borrar."""
    print("\n" + "="*60)
    print("EJEMPLO 2: Verificación Previa (Dry Run)")
    print("="*60)

    service = get_gmail_service()

    # Buscar sin eliminar (seguro para previsualización)
    from datetime import datetime, timedelta
    fecha_limite = (datetime.now() - timedelta(days=6 * 30)).strftime("%Y/%m/%d")
    query = f"before:{fecha_limite} is:unread"

    try:
        resultados = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=100,  # Solo una página — ver ejemplo con paginación en limpiar_correos.py
        ).execute()
    except HttpError as e:
        print(f"\n✗ Error al consultar Gmail: {e}")
        return

    mensajes = resultados.get("messages", [])
    total_estimado = resultados.get("resultSizeEstimate", len(mensajes))
    print(f"\n📊 Primeros {len(mensajes)} correos de esta página (estimado total: {total_estimado})")
    print(f"📅 Criterio: {query}")
    print(f"\nℹ️  Para eliminarlos, ejecuta:")
    print("    python limpiar_correos.py --dry-run   # para contar primero")
    print("    python limpiar_correos.py             # para eliminar")


def ejemplo_3_limpieza_personalizada():
    """Eliminar con parámetros personalizados."""
    print("\n" + "="*60)
    print("EJEMPLO 3: Limpieza Personalizada")
    print("="*60)

    # Eliminar TODOS los correos (leídos y no leídos) de más de 1 año
    resultado = limpiar_correos(
        meses=12,              # Más de 1 año
        solo_no_leidos=False,  # Incluir leídos
    )

    print(f"\n✓ Se eliminaron {resultado['exitos']} correos")


def ejemplo_4_errores_comunes():
    """Referencia de errores comunes y soluciones reales."""
    print("\n" + "="*60)
    print("EJEMPLO 4: Solución de Problemas")
    print("="*60)

    errores = {
        "403 Forbidden": {
            "causa": "Cuota de usuario excedida o permisos insuficientes",
            "solucion": [
                "1. Si es cuota: espera a que se resetee (24h) — ya se reintenta "
                "automáticamente 3 veces con backoff antes de fallar",
                "2. Si es permisos insuficientes, revisa los scopes en "
                "gmail_processor/auth.py y vuelve a autorizar (borra token.json)",
            ]
        },
        "429 Too Many Requests": {
            "causa": "Rate limit de Gmail API",
            "solucion": [
                "1. limpiar_correos.py ya reintenta con backoff exponencial "
                "(1s, 2s, 4s) hasta 3 veces — normalmente no requiere acción",
                "2. Si persiste tras los reintentos, ejecuta en un horario "
                "con menos actividad en la cuenta",
            ]
        },
        "401 Unauthorized": {
            "causa": "Token expirado o inválido",
            "solucion": [
                "1. Elimina token.json",
                "2. Ejecuta: python asistente_personal.py",
                "3. Autoriza de nuevo en el navegador",
            ]
        }
    }

    for error_code, info in errores.items():
        print(f"\n🔴 {error_code}")
        print(f"   Causa: {info['causa']}")
        print(f"   Solución:")
        for sol in info['solucion']:
            print(f"      {sol}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("EJEMPLOS: limpiar_correos.py")
    print("="*60)

    # Descomenta el ejemplo que quieras ejecutar:

    # ejemplo_1_limpieza_por_defecto()
    ejemplo_2_listar_sin_borrar()
    # ejemplo_3_limpieza_personalizada()
    # ejemplo_4_errores_comunes()

    print("\n✅ Fin de ejemplos")
