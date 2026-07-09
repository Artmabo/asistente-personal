#!/usr/bin/env python
"""
Ejemplos de uso avanzado del sistema de throttling adaptativo.
Muestra cómo usar diferentes modos y parámetros para evitar 403/429.
"""

from limpiar_correos import limpiar_correos, limpiar_bandeja
from asistente_personal import get_gmail_service


def ejemplo_1_modo_conservador():
    """Modo por defecto - el más seguro, respeita límites de Gmail API."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Modo Conservador (RECOMENDADO)")
    print("="*60)
    print("✅ Usa delays adaptativos")
    print("✅ Circuit breaker automático")
    print("✅ Respeita límites de Gmail API")
    print("❌ Más lento pero confiable")
    
    resultado = limpiar_correos(
        meses=6,
        solo_no_leidos=True,
    )

    print(f"\n✓ Resultado: {resultado['exitos']} correos eliminados")


def ejemplo_2_listar_sin_borrar():
    """Solo verificar cuántos correos se encontrarían sin borrar."""
    print("\n" + "="*60)
    print("EJEMPLO 2: Verificación Previa (Dry Run)")
    print("="*60)
    
    service = get_gmail_service()

    # dry_run=True reutiliza la misma lógica de query que el borrado real,
    # así este ejemplo nunca se desincroniza de limpiar_bandeja().
    resultado = limpiar_bandeja(service, dry_run=True)

    print(f"\n📊 Se encontraron {resultado['procesados']} correos que cumplen criterio")
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


def ejemplo_4_comparacion_modos():
    """Comparar comportamiento en modo agresivo vs conservador."""
    print("\n" + "="*60)
    print("EJEMPLO 4: Comparación de Modes")
    print("="*60)
    
    print("\n📊 Modo AGRESIVO:")
    print("   - REQUEST_DELAY: 0.1s (muy rápido)")
    print("   - BATCH_SIZE: 30")
    print("   - RIESGO: Alto para 403/429")
    print("   - VELOCIDAD: Rápida")
    
    print("\n📊 Modo CONSERVADOR:")
    print("   - REQUEST_DELAY: 0.5s (seguro)")
    print("   - BATCH_SIZE: 15")
    print("   - RIESGO: Bajo o nulo")
    print("   - VELOCIDAD: Moderada")
    
    print("\n✅ RECOMENDACIÓN: Usar modo CONSERVADOR siempre")



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
                "2. Aumentar PAGE_DELAY y REQUEST_DELAY",
                "3. Reducir BATCH_SIZE",
                "4. Usar aggressive=False"
            ]
        },
        "429 Too Many Requests": {
            "causa": "Rate limit de Gmail API",
            "solucion": [
                "1. Circuit breaker se activa automáticamente",
                "2. Espera exponencial con backoff",
                "3. Aumenta PAGE_DELAY a 5.0+",
                "4. Ejecuta en horarios menos concurridos"
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
    # ejemplo_6_errores_comunes()
    
    print("\n✅ Fin de ejemplos")
