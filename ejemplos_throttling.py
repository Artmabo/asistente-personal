#!/usr/bin/env python
"""
Ejemplos de uso de limpiar_correos con distintos parámetros.
Muestra cómo acotar el alcance de la limpieza para evitar mover
demasiados correos de golpe.
"""

from limpiar_correos import limpiar_correos
from asistente_personal import get_gmail_service


def ejemplo_1_modo_conservador():
    """Solo correos no leídos de más de 6 meses — el alcance más acotado."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Modo Conservador (RECOMENDADO)")
    print("="*60)
    print("✅ Solo correos no leídos")
    print("✅ Más de 6 meses de antigüedad")
    print("❌ No incluye correos ya leídos")

    resultado = limpiar_correos(
        meses=6,
        solo_no_leidos=True,
    )

    print(f"\n✓ Resultado: {resultado['exitos']} de {resultado['procesados']} correos enviados a papelera")


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

    print(f"\n✓ Se enviaron a papelera {resultado['exitos']} de {resultado['procesados']} correos")


def ejemplo_4_comparacion_modos():
    """Comparar el alcance de una limpieza acotada vs. una amplia."""
    print("\n" + "="*60)
    print("EJEMPLO 4: Comparación de alcances")
    print("="*60)

    print("\n📊 Alcance AMPLIO (meses bajo, solo_no_leidos=False):")
    print("   - Incluye correos leídos y no leídos")
    print("   - Mueve muchos más mensajes por ejecución")
    print("   - RECOMENDADO: revisar antes con --dry-run")

    print("\n📊 Alcance ACOTADO (solo_no_leidos=True):")
    print("   - Solo correos que nunca abriste")
    print("   - Menor riesgo de borrar algo que sí te interesaba")

    print("\n✅ RECOMENDACIÓN: empezar siempre con --dry-run o solo_no_leidos=True")



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
                "2. Verificar que el scope de OAuth incluya acceso de escritura",
                "3. Ejecutar con --dry-run para confirmar antes de reintentar",
            ]
        },
        "429 Too Many Requests": {
            "causa": "Rate limit de Gmail API",
            "solucion": [
                "1. El procesador (gmail_processor.actions) reintenta automáticamente "
                "con backoff exponencial",
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
    print("EJEMPLOS: Sistema de Throttling Adaptativo")
    print("="*60)
    
    # Descomenta el ejemplo que quieras ejecutar:
    
    # ejemplo_1_modo_conservador()
    ejemplo_2_listar_sin_borrar()
    # ejemplo_3_limpieza_personalizada()
    # ejemplo_4_comparacion_modos()
    # ejemplo_5_monitorear_throttle()
    # ejemplo_6_errores_comunes()
    
    print("\n✅ Fin de ejemplos")
