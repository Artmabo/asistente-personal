#!/usr/bin/env python
"""
Ejemplos de uso del asistente de Gmail.
Muestra cómo usar las funciones de autenticación y limpieza.
"""

from asistente_personal import get_gmail_service
from limpiar_correos import limpiar_correos


def ejemplo_1_limpieza_basica():
    """Elimina correos no leídos más antiguos de 6 meses (default)."""
    print(\"\\n=== Ejemplo 1: Limpieza básica ===\")
    resumen = limpiar_correos()
    print(f\"Resultado: {resumen}\\n\")\n\n\ndef ejemplo_2_limpieza_personalizada():
    \"\"\"Elimina correos más antiguos de 3 meses (leídos y no leídos).\"\"\"\n    print(\"\\n=== Ejemplo 2: Limpieza personalizada ===\")\n    service = get_gmail_service()\n    resumen = limpiar_correos(service=service, meses=3, solo_no_leidos=False)\n    print(f\"Resultado: {resumen}\\n\")\n\n\ndef ejemplo_3_listar_etiquetas():\n    \"\"\"Lista todas las etiquetas de Gmail.\"\"\"\n    print(\"\\n=== Ejemplo 3: Listar etiquetas ===\")\n    service = get_gmail_service()\n    results = service.users().labels().list(userId=\"me\").execute()\n    labels = results.get(\"labels\", [])\n    print(f\"Total de etiquetas: {len(labels)}\")\n    for label in labels[:10]:  # Mostrar primeras 10\n        print(f\"  - {label['name']}\")\n    print()\n\n\ndef ejemplo_4_contar_no_leidos():\n    \"\"\"Cuenta cuántos correos no leídos hay.\"\"\"\n    print(\"\\n=== Ejemplo 4: Contar correos no leídos ===\")\n    service = get_gmail_service()\n    try:\n        results = service.users().messages().list(userId=\"me\", q=\"is:unread\").execute()\n        count = len(results.get(\"messages\", []))\n        print(f\"Correos no leídos: {count}\\n\")\n    except Exception as e:\n        print(f\"Error: {e}\\n\")\n\n\ndef ejemplo_5_limpieza_agresiva():\n    \"\"\"Elimina todos los correos más antiguos de 1 año.\"\"\"\n    print(\"\\n=== Ejemplo 5: Limpieza agresiva (1 año) ===\")\n    service = get_gmail_service()\n    resumen = limpiar_correos(service=service, meses=12, solo_no_leidos=False)\n    print(f\"Resultado: {resumen}\\n\")\n\n\nif __name__ == \"__main__\":\n    print(\"Ejemplos de uso del asistente de Gmail\")\n    print(\"=\" * 50)\n\n    # Descomenta el ejemplo que quieras ejecutar:\n    \n    # ejemplo_1_limpieza_basica()\n    # ejemplo_2_limpieza_personalizada()\n    ejemplo_3_listar_etiquetas()\n    # ejemplo_4_contar_no_leidos()\n    # ejemplo_5_limpieza_agresiva()\n