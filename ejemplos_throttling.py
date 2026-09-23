#!/usr/bin/env python
"""
Ejemplos de uso de limpiar_correos.py.

Nota: versiones anteriores de este archivo documentaban un sistema de
throttling adaptativo configurable (REQUEST_DELAY, BATCH_SIZE, circuit
breaker, aggressive=True/False) que ya no existe en limpiar_correos.py —
la limpieza actual usa messages().batchModify() (hasta 1000 IDs por
llamada) sin parámetros de throttling ajustables. Los ejemplos de abajo
reflejan el comportamiento real actual.
"""

from limpiar_correos import limpiar_correos
from asistente_personal import get_gmail_service


def ejemplo_1_modo_conservador():
    """Limpieza con los parámetros por defecto."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Limpieza estándar")
    print("="*60)
    print("✅ Usa batchModify (hasta 1000 mensajes por llamada)")
    print("✅ Reintenta por página; una página fallida no aborta las demás")

    try:
        resultado = limpiar_correos(meses=6, solo_no_leidos=True)
    except Exception as e:
        print(f"Error: {e}\n")
        return

    print(f"\n✓ Resultado: {resultado['exitos']} correos eliminados")


def ejemplo_2_listar_sin_borrar():
    """Solo verificar cuántos correos se encontrarían sin borrar."""
    print("\n" + "="*60)
    print("EJEMPLO 2: Verificación Previa (Dry Run)")
    print("="*60)

    try:
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
    except Exception as e:
        print(f"Error: {e}\n")
        return

    print(f"\n📊 Se encontraron {len(mensajes)} correos que cumplen criterio")
    print(f"📅 Criterio: {query}")
    print(f"\nℹ️  Para eliminarlos, ejecuta:")
    print("    python limpiar_correos.py")


def ejemplo_3_limpieza_personalizada():
    """Eliminar con parámetros personalizados."""
    print("\n" + "="*60)
    print("EJEMPLO 3: Limpieza Personalizada")
    print("="*60)

    try:
        # Eliminar TODOS los correos (leídos y no leídos) de más de 1 año
        resultado = limpiar_correos(
            meses=12,              # Más de 1 año
            solo_no_leidos=False,  # Incluir leídos
        )
    except Exception as e:
        print(f"Error: {e}\n")
        return

    print(f"\n✓ Se eliminaron {resultado['exitos']} correos")



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
                "2. Verificar que el scope de Gmail concedido sea suficiente",
                "3. Ejecuta en horarios menos concurridos",
            ]
        },
        "429 Too Many Requests": {
            "causa": "Rate limit de Gmail API",
            "solucion": [
                "1. gmail_processor.actions.GmailActions reintenta automáticamente"
                "   con backoff exponencial (hasta 3 intentos)",
                "2. Ejecuta en horarios menos concurridos",
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
    print("EJEMPLOS: limpiar_correos.py")
    print("="*60)

    # Descomenta el ejemplo que quieras ejecutar:

    # ejemplo_1_modo_conservador()
    ejemplo_2_listar_sin_borrar()
    # ejemplo_3_limpieza_personalizada()
    # ejemplo_6_errores_comunes()

    print("\n✅ Fin de ejemplos")
