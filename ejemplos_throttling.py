#!/usr/bin/env python
"""
Ejemplos de uso de limpiar_correos() y de la Gmail API para casos que no
cubre el menú interactivo (procesar_correos.py).

Nota sobre límites de la API: limpiar_bandeja() mueve mensajes a la papelera
en lotes (batchModify, hasta 1000 IDs por llamada) y no expone parámetros de
"modo agresivo" ni delays configurables — no hay nada que ajustar para ir
más rápido o más lento. Si Gmail responde 429/403 por cuota, la solución es
esperar y reintentar (ver ejemplo_6_errores_comunes), no cambiar un ritmo
de envío.
"""

from limpiar_correos import limpiar_correos
from asistente_personal import get_gmail_service


def ejemplo_1_limpieza_basica():
    """Elimina correos no leídos más antiguos de 6 meses (comportamiento por defecto)."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Limpieza básica")
    print("="*60)

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


def ejemplo_4_procesador_con_reintentos():
    """
    Si necesitas reintentos automáticos ante 429/500/503 (backoff exponencial),
    usa el procesador de reglas en vez de limpiar_correos(): sus acciones
    (gmail_processor.actions.GmailActions) sí implementan retry con backoff.
    limpiar_correos() es intencionalmente simple y no reintenta — un error
    de Gmail API detiene solo la página en curso.
    """
    print("\n" + "="*60)
    print("EJEMPLO 4: Reintentos automáticos con el procesador de reglas")
    print("="*60)
    print("Ejecuta en su lugar:")
    print("    python procesar_correos.py --cleanup --live")
    print("(ver gmail_processor/actions.py::GmailActions._call para el detalle del retry)")


def ejemplo_6_errores_comunes():
    """Referencia de errores comunes y soluciones."""
    print("\n" + "="*60)
    print("EJEMPLO 6: Solución de Problemas")
    print("="*60)
    
    errores = {
        "403 Forbidden": {
            "causa": "Cuota de usuario excedida o permisos insuficientes",
            "solucion": [
                "1. Esperar 24h (se resetea la cuota diaria)",
                "2. Verificar que el OAuth se autorizó con el scope mail.google.com",
                "3. Para reintentos automáticos, usa procesar_correos.py --cleanup "
                "(ver ejemplo_4_procesador_con_reintentos)",
            ]
        },
        "429 Too Many Requests": {
            "causa": "Rate limit de Gmail API",
            "solucion": [
                "1. limpiar_correos() no reintenta — vuelve a ejecutarlo en unos minutos",
                "2. Para backoff exponencial automático, usa "
                "procesar_correos.py --cleanup (GmailActions sí reintenta)",
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
    print("EJEMPLOS: limpiar_correos() y manejo de errores de la Gmail API")
    print("="*60)

    # Descomenta el ejemplo que quieras ejecutar:

    # ejemplo_1_limpieza_basica()
    ejemplo_2_listar_sin_borrar()
    # ejemplo_3_limpieza_personalizada()
    # ejemplo_4_procesador_con_reintentos()
    # ejemplo_6_errores_comunes()

    print("\n✅ Fin de ejemplos")
