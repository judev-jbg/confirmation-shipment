"""
Sistema de Confirmación de Envíos para Toolstock
Migrado desde n8n a Python

Este script:
1. Consulta la API de PrestaShop para obtener pedidos con estado 3 (Preparación en curso)
2. Filtra solo los pedidos que tengan número de seguimiento
3. Procesa cada pedido individualmente
4. Obtiene información del cliente y dirección de entrega
5. Genera un email de confirmación de envío usando la API de plantillas
6. Envía el email al cliente con copia a administración
7. Actualiza el estado del pedido en PrestaShop a 4 (Enviado)
8. Envía notificaciones internas de éxito o error
"""

import os
import sys
import logging
import asyncio
from dotenv import load_dotenv

# Importar servicios
from services.prestashop_service import PrestaShopService
from services.email_service import EmailService
from services.notifications import NotificationManager
from services.order_processor import OrderProcessor

# Cargar variables de entorno
load_dotenv()

# Configurar logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/confirmation_shipment.log")

# Crear directorio de logs si no existe
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Configurar logger
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("ConfirmationShipmentLogger")


def main():
    """Función principal."""
    try:
        # Obtener el entorno
        environment = os.getenv("ENVIRONMENT", "production")
        logger.info(f"Iniciando en modo: {environment.upper()}")

        # Inicializar servicios
        prestashop_service = PrestaShopService(
            api_url=os.getenv("PRESTASHOP_API_URL", "https://www.toolstock.info/api"),
            username=os.getenv("PRESTASHOP_API_USERNAME", ""),
            password=os.getenv("PRESTASHOP_API_PASSWORD", "")
        )

        # Servicio de email para pedidos (usa orders@toolstock.info)
        email_service = EmailService(
            smtp_server=os.getenv("ORDERS_SMTP_SERVER", "smtp.office365.com"),
            smtp_port=int(os.getenv("ORDERS_SMTP_PORT", "587")),
            sender_email=os.getenv("ORDERS_SENDER_EMAIL"),
            sender_password=os.getenv("ORDERS_SENDER_PASSWORD"),
            template_api_url=os.getenv("EMAIL_TEMPLATE_API_URL", "https://postlyapi.vercel.app/api/confirmationShip"),
            bcc_email=os.getenv("BCC_EMAIL", "junior.marketing@selk.es"),
            environment=environment,
            dev_test_email=os.getenv("DEV_TEST_EMAIL", "junior.marketing@selk.es")
        )

        # Servicio de notificaciones internas (usa noreply@toolstock.info)
        notification_manager = NotificationManager()

        # Crear procesador de pedidos
        processor = OrderProcessor(
            prestashop_service=prestashop_service,
            email_service=email_service,
            notification_manager=notification_manager
        )

        # Ejecutar proceso
        asyncio.run(processor.process_all_orders_async())

    except KeyboardInterrupt:
        logger.info("Proceso interrumpido por el usuario")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
