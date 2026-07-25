#!/usr/bin/env python
"""
Ejemplos de uso de limpiar_correos.py y buenas prácticas para evitar 403/429
al hacer muchas llamadas a la Gmail API.

Nota: limpiar_correos() no implementa un modo "agresivo/conservador" con
parámetros de delay configurables — eso se controla llamando a la API con
prudencia (lotes vía batchModify, como ya hace mover_lote_a_papelera) y,
si Gmail devuelve 429/403, reintentando más tarde. Los ejemplos de abajo
muestran el uso real de la función y algunas recomendaciones generales.
"""

from limpiar_correos import limpiar_correos
from asistente_personal import get_gmail_service


def ejemplo_1_limpieza_basica():
    """Uso por defecto: correos no leídos de más de 6 meses."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Limpieza básica")
    print("="*60)

    resultado = limpiar_correos(meses=6, solo_no_leidos=True)

    print(f"\n✓ Resultado: {resultado['exitos']} correos enviados a papelera"
          f" (de {resultado['procesados']} encontrados)")


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

    print(f"\n✓ Se enviaron a papelera {resultado['exitos']} correos"
          f" (de {resultado['procesados']} encontrados)")


def ejemplo_4_buenas_practicas():
    """Recomendaciones generales para evitar 403/429 al usar la Gmail API."""
    print("\n" + "="*60)
    print("EJEMPLO 4: Buenas prácticas para evitar throttling")
    print("="*60)

    print("\n📊 Recomendaciones:")
    print("   - Usa batchModify (mover_lote_a_papelera) en vez de una llamada")
    print("     por mensaje — ya es lo que hace limpiar_bandeja().")
    print("   - Evita ejecutar varias limpiezas en paralelo sobre la misma cuenta.")
    print("   - Si ves 429/403 de forma persistente, espera y reintenta más tarde")
    print("     en vez de bajar el tamaño de página agresivamente.")
    print("   - Ejecuta limpiezas grandes en horarios de baja concurrencia.")


def ejemplo_5_errores_comunes():
    """Referencia de errores comunes y soluciones."""
    print("\n" + "="*60)
    print("EJEMPLO 5: Solución de Problemas")
    print("="*60)

    errores = {
        "403 Forbidden": {
            "causa": "Cuota de usuario excedida o permisos insuficientes",
            "solucion": [
                "1. Esperar 24h (se resetea la cuota diaria)",
                "2. Reducir la frecuencia de ejecución",
                "3. Revisar los scopes del token (config/README.md)",
            ]
        },
        "429 Too Many Requests": {
            "causa": "Rate limit de Gmail API",
            "solucion": [
                "1. Espera unos minutos y reintenta",
                "2. Evita ejecutar varias limpiezas en paralelo",
                "3. Ejecuta en horarios menos concurridos",
            ]
        },
        "401 Unauthorized": {
            "causa": "Token expirado o inválido",
            "solucion": [
                "1. Elimina token.json",
                "2. Ejecuta: python asistente_personal.py",
                "3. Autoriza de nuevo en navegador"
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
    print("EJEMPLOS: limpiar_correos.py y buenas prácticas de uso de la API")
    print("="*60)

    # Descomenta el ejemplo que quieras ejecutar:

    # ejemplo_1_limpieza_basica()
    ejemplo_2_listar_sin_borrar()
    # ejemplo_3_limpieza_personalizada()
    # ejemplo_4_buenas_practicas()
    # ejemplo_5_errores_comunes()

    print("\n✅ Fin de ejemplos")
