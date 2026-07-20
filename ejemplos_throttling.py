#!/usr/bin/env python
"""
Ejemplos de uso de limpiar_correos con distintos parámetros.

`limpiar_bandeja` ya usa `batchModify` (hasta 1000 IDs por llamada) para
mover correos a la papelera, lo que evita las llamadas 1-por-mensaje que
antes disparaban 403/429 con volúmenes grandes.
"""

from limpiar_correos import limpiar_correos
from asistente_personal import get_gmail_service


def ejemplo_1_modo_por_defecto():
    """Elimina no leídos de más de 6 meses (valores por defecto)."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Modo por defecto")
    print("="*60)

    resultado = limpiar_correos(
        meses=6,
        solo_no_leidos=True,
    )

    print(f"\n✓ Resultado: {resultado['exitos']} correos enviados a papelera"
          f" ({resultado['errores']} errores)")


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
          f" ({resultado['errores']} errores)")


def ejemplo_4_limpiar_por_categoria():
    """Limpia una categoría específica usando limpiar_bandeja directamente."""
    print("\n" + "="*60)
    print("EJEMPLO 4: Limpieza por categoría")
    print("="*60)

    from limpiar_correos import limpiar_bandeja

    service = get_gmail_service()
    resultado = limpiar_bandeja(service, categorias=["promociones"])
    print(f"\n✓ Promociones: {resultado['exitos']}/{resultado['procesados']}"
          f" enviados a papelera")



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
                "2. Revisar que el token tenga los scopes necesarios",
            ]
        },
        "429 Too Many Requests": {
            "causa": "Rate limit de Gmail API",
            "solucion": [
                "1. GmailActions reintenta automáticamente con backoff"
                " exponencial (ver gmail_processor/actions.py)",
                "2. Si persiste, ejecuta en horarios menos concurridos",
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
    print("EJEMPLOS: limpiar_correos")
    print("="*60)

    # Descomenta el ejemplo que quieras ejecutar:

    # ejemplo_1_modo_por_defecto()
    ejemplo_2_listar_sin_borrar()
    # ejemplo_3_limpieza_personalizada()
    # ejemplo_4_limpiar_por_categoria()
    # ejemplo_6_errores_comunes()

    print("\n✅ Fin de ejemplos")
