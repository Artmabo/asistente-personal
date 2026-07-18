#!/usr/bin/env python
"""
Ejemplos de uso del sistema de reintentos con backoff exponencial.
Muestra cómo limpiar_correos() reintenta automáticamente ante 429/5xx.
"""

from limpiar_correos import limpiar_correos
from asistente_personal import get_gmail_service


def ejemplo_1_modo_conservador():
    """Modo por defecto - dry_run=True, no borra nada de verdad."""
    print("\n" + "="*60)
    print("EJEMPLO 1: Vista previa (dry-run)")
    print("="*60)
    print("✅ Reintenta automáticamente con backoff exponencial en 429/500/503")
    print("✅ dry_run=True: solo cuenta, no mueve nada a la papelera")

    resultado = limpiar_correos(
        meses=6,
        solo_no_leidos=True,
        dry_run=True,
    )

    print(f"\n✓ Resultado: {resultado['exitos']} correos encontrados (dry-run)")


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
    
    # Vista previa de TODOS los correos (leídos y no leídos) de más de 1 año.
    # Pasa dry_run=False explícitamente para borrar de verdad.
    resultado = limpiar_correos(
        meses=12,              # Más de 1 año
        solo_no_leidos=False,  # Incluir leídos
        dry_run=True,
    )

    print(f"\n✓ Se encontraron {resultado['exitos']} correos (dry-run)")


def ejemplo_4_reintentos():
    """Cómo funciona el backoff exponencial ante errores de la API."""
    print("\n" + "="*60)
    print("EJEMPLO 4: Reintentos con backoff exponencial")
    print("="*60)

    print("\n📊 Ante un 429 (rate limit) o 500/503 (error del servidor):")
    print("   - Reintenta hasta 3 veces")
    print("   - Espera 1s, luego 2s, luego 4s entre intentos")
    print("   - Si se agotan los reintentos, se registra el error y continúa")

    print("\n✅ Esto se aplica automáticamente en limpiar_bandeja() —")
    print("   no requiere ninguna configuración adicional.")



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
                "3. Ejecutar en horarios menos concurridos"
            ]
        },
        "429 Too Many Requests": {
            "causa": "Rate limit de Gmail API",
            "solucion": [
                "1. limpiar_correos.py reintenta automáticamente con backoff exponencial",
                "2. Si persiste tras 3 intentos, espera unos minutos y reintenta",
                "3. Ejecuta en horarios menos concurridos"
            ]
        },
        "401 Unauthorized": {
            "causa": "Token expirado o inválido",
            "solucion": [
                "1. Elimina token.json",
                "2. Ejecuta: python asistente-personal.py",
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
    # ejemplo_4_reintentos()
    # ejemplo_6_errores_comunes()
    
    print("\n✅ Fin de ejemplos")
