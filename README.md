# Sistema de Confirmación de Envíos - Toolstock

Sistema automatizado para enviar notificaciones de confirmación de envío a clientes de Toolstock cuando sus pedidos son despachados.

## Descripción

Este sistema:

1. Consulta la API de PrestaShop para obtener pedidos en estado 3 (Preparación en curso)
2. Filtra solo los pedidos que tengan número de seguimiento asignado
3. Obtiene información del cliente y dirección de entrega
4. Genera un email personalizado usando una API de plantillas
5. Envía el email al cliente con el número de seguimiento
6. Actualiza el estado del pedido a 4 (Enviado)
7. Envía notificaciones internas de éxito o error vía Slack y Email

## Requisitos

- Python 3.8+
- Acceso a la API de PrestaShop (Toolstock)
- Credenciales SMTP de Office 365
- Credenciales para notificaciones internas
- Webhook de Slack para notificaciones

## Instalación

### 1. Crear entorno virtual

```powershell
python -m venv venv
```

### 2. Activar entorno virtual

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Editar el archivo `.env` con las credenciales correspondientes:

```env
# Entorno (development/production)
ENVIRONMENT=development

# PrestaShop API
PRESTASHOP_API_URL=url_de_tu_prestashop_api
PRESTASHOP_API_USERNAME=tu_usuario
PRESTASHOP_API_PASSWORD=tu_contraseña

# SMTP para emails a clientes
ORDERS_SMTP_SERVER=servidor_smtp.office365.com
ORDERS_SMTP_PORT=puerto_smtp
ORDERS_SENDER_EMAIL=sender_email
ORDERS_SENDER_PASSWORD=tu_contraseña

# Notificaciones internas
SMTP_SERVER=servidor_smtp.office365.com
SENDER_EMAIL=sernder_email_internal
SENDER_PASSWORD=tu_contraseña
NOTIFICATION_EMAILS=admin@ejemplo.com

# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL=#channel_name
```

## Uso

### Ejecución Manual

Para ejecutar el script manualmente una sola vez:

```powershell
.\run.ps1
```

Este script:

- Crea el entorno virtual si no existe
- Instala las dependencias automáticamente
- Ejecuta el proceso de confirmación de envíos
- Genera logs en el directorio `logs/`

### Ejecución Directa (con entorno virtual activado)

```powershell
python main.py
```

### Programar Ejecución Automática

El flujo original de n8n estaba configurado para ejecutarse:

- De lunes a sábado
- A las 19:00 horas

Para replicar esto, puedes usar el Programador de Tareas de Windows:

1. Abrir "Programador de tareas"
2. Crear tarea básica
3. Trigger: Diario a las 19:00
4. Acción: Ejecutar programa
   - Programa: `powershell.exe`
   - Argumentos: `-ExecutionPolicy Bypass -File "ruta_completa_a_run.ps1"`
5. En "Condiciones", configurar:
   - Ejecutar solo si el usuario ha iniciado sesión: No
   - Días de la semana: Lunes a Sábado

## Estructura del Proyecto

```
confirmation-shipment/
├── main.py                 # Punto de entrada principal
├── requirements.txt        # Dependencias Python
├── run.ps1                 # Script de ejecución automática
├── .env                    # Variables de entorno
├── README.md               # Este archivo
├── logs/                   # Directorio de logs
│   ├── confirmation_shipment.log
│   ├── scheduler.log
│   ├── scheduler_error.log
│   └── scheduler_output.log
└── services/               # Módulos de servicios
    ├── __init__.py
    ├── prestashop_service.py    # Interacción con PrestaShop API
    ├── email_service.py         # Envío de emails a clientes
    ├── notifications.py         # Notificaciones internas (Slack/Email)
    └── order_processor.py       # Lógica de procesamiento de pedidos
```

## Modos de Operación

### Modo Development

En modo development (`ENVIRONMENT=development`):

- Los emails se envían SOLO al email de prueba configurado en `DEV_TEST_EMAIL`
- No se envían emails a clientes reales
- Se registra en el log el email del cliente original

Esto permite probar sin afectar a clientes reales.

### Modo Production

En modo production (`ENVIRONMENT=production`):

- Los emails se envían a los clientes reales
- Se envía copia oculta (BCC) al email de administración
- Las notificaciones internas se envían normalmente

## Sistema de Notificaciones

El sistema envía notificaciones internas automáticamente en los siguientes casos:

### Notificaciones de Éxito ✅

- Cuando se completa la ejecución sin errores
- Se envía por Slack (preferentemente) o Email

### Notificaciones de Advertencia ⚠️

- Cuando hay algunos pedidos que fallaron pero otros tuvieron éxito
- Incluye detalles de los errores
- Se envía por Email y Slack

### Notificaciones Críticas 🚨

- Cuando hay un error al conectar con la API de PrestaShop
- Errores fatales en el proceso principal
- Se envía por Email y Slack con alta prioridad

## Logs

Los logs se almacenan en el directorio `logs/`:

- `confirmation_shipment.log`: Log principal del proceso
- `scheduler.log`: Log del script PowerShell
- `scheduler_error.log`: Errores del script PowerShell
- `scheduler_output.log`: Output del script PowerShell

### Nivel de Logs

Puedes ajustar el nivel de detalle en `.env`:

```env
LOG_LEVEL=DEBUG    # Máximo detalle
LOG_LEVEL=INFO     # Normal (recomendado)
LOG_LEVEL=WARNING  # Solo advertencias y errores
LOG_LEVEL=ERROR    # Solo errores
```

## Resolución de Problemas

### Error: "No se encontró el entorno virtual"

Ejecutar `.\run.ps1` que lo creará automáticamente.

### Error: "Failed to send email notification"

Verificar las credenciales SMTP en `.env`.

### Error: "Error al consultar PrestaShop API"

Verificar:

- URL de la API
- Credenciales de autenticación
- Conectividad de red

### No se encuentran pedidos

Verificar que hay pedidos con:

- Estado 3 (Preparación en curso)
- Número de seguimiento asignado
- Métodos de pago: PayPal, Redsys, PayPal with fee, o Transferencia bancaria

## Mantenimiento

### Actualizar Dependencias

```powershell
pip install --upgrade -r requirements.txt
```

### Verificar Configuración

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Environment:', os.getenv('ENVIRONMENT'))"
```

### Limpiar Logs Antiguos

Los logs se acumulan con el tiempo. Puedes limpiarlos manualmente o crear un script de limpieza:

```powershell
Remove-Item .\logs\*.log
```

## Seguridad

- El archivo `.env` contiene información sensible y NO debe ser commiteado a Git
- Las credenciales SMTP deben rotar periódicamente
- Los webhooks de Slack deben mantenerse privados
- Revisar logs regularmente para detectar intentos de acceso no autorizado

## Soporte

Para problemas o preguntas, contactar al equipo de desarrollo:

- Crear un issue en el repositorio

## Licencia

Uso interno de Toolstock - Todos los derechos reservados
