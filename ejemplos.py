#!/usr/bin/env python
"""
Ejemplos de uso del asistente de Gmail.
Muestra cómo usar las funciones de autenticación y limpieza.
"""

from asistente_personal import get_gmail_service
from limpiar_correos import limpiar_correos


def ejemplo_1_limpieza_basica():
    """Elimina correos no leídos más antiguos de 6 meses (default)."""
    print("\n=== Ejemplo 1: Limpieza básica ===")
    resumen = limpiar_correos()
    print(f"Resultado: {resumen}\n")


def ejemplo_2_limpieza_personalizada():
    """Elimina correos más antiguos de 3 meses (leídos y no leídos)."""
    print("\n=== Ejemplo 2: Limpieza personalizada ===")
    service = get_gmail_service()
    resumen = limpiar_correos(service=service, meses=3, solo_no_leidos=False)
    print(f"Resultado: {resumen}\n")


def ejemplo_3_listar_etiquetas():
    """Lista todas las etiquetas de Gmail."""
    print("\n=== Ejemplo 3: Listar etiquetas ===")
    service = get_gmail_service()
    results = service.users().labels().list(userId="me").execute()
    labels = results.get("labels", [])
    print(f"Total de etiquetas: {len(labels)}")
    for label in labels[:10]:  # Mostrar primeras 10
        print(f"  - {label['name']}")
    print()


def ejemplo_4_contar_no_leidos():
    """Cuenta cuántos correos no leídos hay."""
    print("\n=== Ejemplo 4: Contar correos no leídos ===")
    service = get_gmail_service()
    try:
        results = service.users().messages().list(userId="me", q="is:unread").execute()
        count = len(results.get("messages", []))
        print(f"Correos no leídos: {count}\n")
    except Exception as e:
        print(f"Error: {e}\n")


def ejemplo_5_limpieza_agresiva():
    """Elimina todos los correos más antiguos de 1 año."""
    print("\n=== Ejemplo 5: Limpieza agresiva (1 año) ===")
    service = get_gmail_service()
    resumen = limpiar_correos(service=service, meses=12, solo_no_leidos=False)
    print(f"Resultado: {resumen}\n")


if __name__ == "__main__":
    print("Ejemplos de uso del asistente de Gmail")
    print("=" * 50)

    # Descomenta el ejemplo que quieras ejecutar:

    # ejemplo_1_limpieza_basica()
    # ejemplo_2_limpieza_personalizada()
    ejemplo_3_listar_etiquetas()
    # ejemplo_4_contar_no_leidos()
    # ejemplo_5_limpieza_agresiva()
