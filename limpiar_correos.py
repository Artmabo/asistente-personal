import os
import time
import sys
import random
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scope correcto para acceso completo a Gmail
SCOPES = ['https://mail.google.com/']

# Configuración ULTRA RÁPIDA - sin barreras (40k correos)
REQUEST_DELAY = 0             # SIN pausa entre requests
MIN_DELAY = 0                 # SIN delay mínimo
MAX_DELAY = 0.5               # Máximo muy bajo
BATCH_SIZE = 500              # Máximo tamaño de lotes (API permite 500)
PAGE_DELAY = 0                # SIN pausa entre páginas
MAX_RETRIES = 3               # Reintentos rápidos


def obtener_servicio(creds_path="config/credentials.json", token_path="token.json"):
    """Obtiene servicio de Gmail con autenticación OAuth."""
    creds = None
    
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


class ThrottleManager:
    """Gestor de throttling adaptativo."""
    
    def __init__(self, initial_delay=REQUEST_DELAY):
        self.current_delay = initial_delay
        self.error_count = 0
        self.success_count = 0
    
    def record_success(self):
        """Registra éxito y reduce delay ligeramente."""
        self.success_count += 1
        self.error_count = max(0, self.error_count - 1)
        if self.success_count % 5 == 0:
            self.current_delay = max(MIN_DELAY, self.current_delay * 0.99)
    
    def record_error(self):
        """Registra error e incrementa delay."""
        self.error_count += 1
        self.success_count = 0
        self.current_delay = min(MAX_DELAY, self.current_delay * 1.5)
    
    def get_wait_time(self):
        """Devuelve delay con jitter."""
        jitter = random.uniform(0, 0.2 * self.current_delay)
        return self.current_delay + jitter



def mover_a_papelera_con_reintentos(service, msg_id, throttle_manager, max_retries=MAX_RETRIES):
    """Envía correo a papelera con reintentos y backoff exponencial."""
    delay = 0.1
    
    for retry in range(1, max_retries + 1):
        try:
            service.users().messages().trash(userId='me', id=msg_id).execute()
            throttle_manager.record_success()
            # Sleep solo si REQUEST_DELAY > 0
            if REQUEST_DELAY > 0:
                time.sleep(throttle_manager.get_wait_time())
            return True
            
        except HttpError as error:
            status = None
            try:
                status = int(error.resp.status)
            except Exception:
                pass
            
            # Error crítico de permisos
            if status == 403 and "insufficient" in str(error).lower():
                print(f"\n❌ Error crítico de permisos [id={msg_id}]: {error}")
                print("El token no tiene permisos suficientes. Deteniendo script.")
                return False
            
            # Rate limits (403 quota o 429)
            if status in (403, 429) and retry < max_retries:
                throttle_manager.record_error()
                print(f"  ⏱️  Rate limit ({status}). Reintentando en {delay:.1f}s... (retry {retry}/{max_retries})")
                time.sleep(delay)
                delay = min(MAX_DELAY, delay * 2)  # Exponencial backoff
                continue
            
            # Otros errores
            print(f"  ❌ Error {status} en id {msg_id}: {error}")
            throttle_manager.record_error()
            return False
    
    return False



def limpiar_bandeja(meses=6, solo_no_leidos=True, query_custom=None):
    """Limpia correos antiguos con throttling adaptativo.
    
    Args:
        meses: antigüedad en meses
        solo_no_leidos: si True, solo elimina no leídos
        query_custom: query personalizada (sobrescribe meses y solo_no_leidos)
    """
    print(f"📧 Scope cargado: {SCOPES}")
    print("⚡⚡⚡ MODO ULTRA RÁPIDO (40k+ correos) - SIN PAUSAS ⚡⚡⚡\n")
    
    # Inicializar throttle manager
    throttle = ThrottleManager(initial_delay=REQUEST_DELAY)
    
    try:
        service = obtener_servicio()
        
        # Construir query
        if query_custom:
            query = query_custom
        else:
            fecha_limite = (datetime.now() - timedelta(days=meses * 30)).strftime("%Y/%m/%d")
            query = f"before:{fecha_limite}"
            if solo_no_leidos:
                query += " is:unread"
        
        print(f"🔍 Buscando correos: {query}\n")
        
        total_procesados = 0
        total_exitos = 0
        page_num = 0
        page_token = None
        
        # Paginación
        while True:
            page_num += 1
            print(f"📄 Página {page_num}:")
            
            try:
                result = service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=500,
                    pageToken=page_token
                ).execute()
                
                messages = result.get('messages', [])
                
                if not messages:
                    print("  ✓ No hay más correos\n")
                    break
                
                print(f"  📧 Encontrados {len(messages)} correos")
                
                # Procesar por lotes
                for batch_start in range(0, len(messages), BATCH_SIZE):
                    batch_end = min(batch_start + BATCH_SIZE, len(messages))
                    batch = messages[batch_start:batch_end]
                    
                    print(f"    Procesando lote {batch_start//BATCH_SIZE + 1} ({len(batch)} mensajes)...")
                    
                    for msg in batch:
                        if mover_a_papelera_con_reintentos(service, msg['id'], throttle):
                            total_exitos += 1
                        total_procesados += 1
                
                # Sin pausa entre lotes (modo rápido)
                
                # Siguiente página
                page_token = result.get('nextPageToken')
                if not page_token:
                    break
                
                # Sin pausa (modo ultra rápido)
                
            except HttpError as error:
                if "403" in str(error):
                    print(f"  ⚠️  Error 403. Circuit breaker activado.")
                    break
                raise
        
        print("\n" + "="*60)
        print("--- RESUMEN FINAL ---")
        print(f"✅ Correos enviados a papelera: {total_exitos}/{total_procesados}")
        print(f"⏱️  Delay final: {throttle.current_delay:.2f}s")
        print(f"📊 Éxitos: {throttle.success_count} | Errores: {throttle.error_count}")
        print("="*60)
        
        return {
            "procesados": total_procesados,
            "exitos": total_exitos,
            "errores": total_procesados - total_exitos
        }
        
    except HttpError as error:
        print(f"\n❌ Error en la API: {error}")
        return None


def limpiar_correos(service=None, meses=6, solo_no_leidos=True, aggressive=False):
    """Función compatible con interfaz anterior."""
    return limpiar_bandeja(meses=meses, solo_no_leidos=solo_no_leidos)


def borrar_correos_antiguos(service=None):
    """Función legacy para compatibilidad."""
    return limpiar_bandeja(meses=6, solo_no_leidos=True)



if __name__ == '__main__':
    # Ejecutar limpieza con modo conservador (default)
    resultado = limpiar_bandeja()
    if resultado:
        print(f"\nResultado final: {resultado}")
