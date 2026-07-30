#!/usr/bin/env python
"""
Ejemplos de uso del manejo de rate limits de Gmail API.

gmail_processor.utils.with_backoff() protege las llamadas de lectura
(listar, obtener mensajes) y GmailActions._call() protege las de
escritura (trash, modify, labels): ambas reintentan automáticamente
ante 429/500/502/503/504 con backoff exponencial + jitter, y
propagan de inmediato cualquier otro error (403 de permisos, 404, etc.).
No hay parámetros de modo "agresivo/conservador" que configurar — el
backoff es automático en todas las llamadas a la API.
"""

from limpiar_correos import limpiar_correos
from asistente_personal import get_gmail_service


def ejemplo_1_limpieza_basica():
    """Limpieza estándar: los reintentos ante rate limit son automáticos."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Limpieza con reintentos automáticos")
    print("="*60)
    print("✅ Reintenta automáticamente ante 429/5xx (backoff exponencial)")
    print("✅ Propaga de inmediato errores no recuperables (403 de permisos, 404)")

    resultado = limpiar_correos(meses=6, solo_no_leidos=True)

    print(f"\n✓ Resultado: {resultado['exitos']} correos eliminados")


def ejemplo_2_listar_sin_borrar():
    """Solo verificar cuántos correos se encontrarían sin borrar."""
    print("\n" + "="*60)
    print("EJEMPLO 2: Verificación Previa (Dry Run)")
    print("="*60)

    service = get_gmail_service()

    # Buscar sin eliminar (seguro para previsualizacion)
    from datetime import datetime, timedelta
    fecha_limite = (datetime.now() - timedelta(days=6 * 30)).strftime("%Y/%m/%d")
    query = f"before:{fecha_limite} is:unread"

    resultados = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=100  # Pequeño límite para ver
    ).execute()

    mensajes = resultados.get("messages", [])
    print(f"\n📊 Se encontraron {len(mensajes)} correos que cumplen criterio")
    print(f"📅 Criterio: {query}")
    print(f"\nℹ️  Para eliminarlos, ejecuta:")
    print("    python limpiar_correos.py")


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
    """Referencia de errores comunes y soluciones."""
    print("\n" + "="*60)
    print("EJEMPLO 4: Solución de Problemas")
    print("="*60)

    errores = {
        "403 Forbidden (permisos)": {
            "causa": "Faltan scopes de OAuth o el token no tiene acceso a Gmail",
            "solucion": [
                "1. No se reintenta automáticamente — es un error de permisos, no de cuota",
                "2. Elimina token.json y vuelve a autorizar",
            ]
        },
        "429 Too Many Requests / 5xx": {
            "causa": "Rate limit o error transitorio de Gmail API",
            "solucion": [
                "1. Se reintenta automáticamente con backoff exponencial + jitter",
                "2. Si falla tras varios intentos, ejecuta en un horario menos concurrido",
            ]
        },
        "401 Unauthorized": {
            "causa": "Token expirado o inválido",
            "solucion": [
                "1. Elimina token.json",
                "2. Ejecuta: python asistente_personal.py",
                "3. Autoriza de nuevo en navegador",
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
    print("EJEMPLOS: Manejo de rate limits de Gmail API")
    print("="*60)

    # Descomenta el ejemplo que quieras ejecutar:

    # ejemplo_1_limpieza_basica()
    ejemplo_2_listar_sin_borrar()
    # ejemplo_3_limpieza_personalizada()
    # ejemplo_4_errores_comunes()

    print("\n✅ Fin de ejemplos")
