"""
Servicio para envío de emails de confirmación de envíos.
Incluye generación de plantillas y envío mediante SMTP.
Soporta dos modos: development (envía a email de prueba) y production (envía a clientes).
"""

import logging
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional

logger = logging.getLogger("ConfirmationShipmentLogger")


class EmailService:
    """Servicio para manejo de emails de confirmación de envíos."""

    def __init__(self, smtp_server: str, smtp_port: int, sender_email: str,
                 sender_password: str, template_api_url: str, bcc_email: str = None,
                 environment: str = "production", dev_test_email: str = None):
        """
        Inicializa el servicio de email.

        Args:
            smtp_server: Servidor SMTP
            smtp_port: Puerto SMTP
            sender_email: Email del remitente (orders@toolstock.info)
            sender_password: Contraseña del remitente
            template_api_url: URL de la API de plantillas
            bcc_email: Email para copia oculta (opcional)
            environment: Entorno (development/production)
            dev_test_email: Email de prueba para desarrollo
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.template_api_url = template_api_url
        self.bcc_email = bcc_email
        self.environment = environment.lower()
        self.dev_test_email = dev_test_email

        if self.environment == "development":
            logger.info(f"EmailService iniciado en modo DEVELOPMENT - Los emails se enviarán a: {self.dev_test_email}")
        else:
            logger.info("EmailService iniciado en modo PRODUCTION - Los emails se enviarán a los clientes")

    def generate_email_template(self, order: Dict[str, Any], customer: Dict[str, Any],
                                address: Dict[str, Any]) -> Optional[str]:
        """
        Genera el HTML del email usando la API de plantillas.

        Args:
            order: Datos del pedido
            customer: Datos del cliente
            address: Datos de la dirección

        Returns:
            HTML del email o None si hay error
        """
        try:
            logger.debug(
                f"Generando plantilla de email para pedido {order.get('id')}")

            payload = {
                "order": order,
                "customer": customer,
                "address": address
            }

            response = requests.post(
                self.template_api_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            # La API devuelve el HTML en body.html
            result = response.json()
            html_content = result.get("body", {}).get("html")

            if not html_content:
                logger.error("La API no devolvió contenido HTML")
                return None

            return html_content

        except Exception as e:
            logger.error(f"Error al generar plantilla de email: {e}")
            return None

    def send_shipment_confirmation_email(self, customer_email: str, order_reference: str,
                                         html_content: str) -> bool:
        """
        Envía el email de confirmación de envío al cliente.

        En modo development: envía a dev_test_email
        En modo production: envía a customer_email con BCC a bcc_email

        Args:
            customer_email: Email del cliente
            order_reference: Referencia del pedido
            html_content: Contenido HTML del email

        Returns:
            True si se envió correctamente, False en caso contrario
        """
        try:
            # Determinar el destinatario según el entorno
            if self.environment == "development":
                if not self.dev_test_email:
                    logger.error("Modo development activo pero dev_test_email no configurado")
                    return False

                recipient_email = self.dev_test_email
                logger.info(f"[DEVELOPMENT] Enviando email de confirmación de envío del pedido {order_reference}")
                logger.info(f"[DEVELOPMENT] Email del cliente real: {customer_email}")
                logger.info(f"[DEVELOPMENT] Email de prueba: {recipient_email}")
            else:
                recipient_email = customer_email
                logger.info(f"[PRODUCTION] Enviando email de confirmación de envío a {customer_email}")

            # Crear mensaje
            msg = MIMEMultipart("alternative")
            msg["From"] = self.sender_email
            msg["To"] = recipient_email

            # Agregar BCC solo en producción
            if self.environment == "production" and self.bcc_email:
                msg["Bcc"] = self.bcc_email

            msg["Subject"] = f"Confirmación de envío de tu pedido {order_reference}"

            # Adjuntar HTML
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            # Enviar email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)

                # Preparar lista de destinatarios
                recipients = [recipient_email]

                # Agregar BCC a la lista de destinatarios solo en producción
                if self.environment == "production" and self.bcc_email:
                    recipients.append(self.bcc_email)

                server.sendmail(self.sender_email, recipients, msg.as_string())

            logger.info(f"Email de confirmación de envío enviado correctamente desde {self.sender_email}")
            return True

        except Exception as e:
            logger.error(f"Error al enviar email: {e}")
            return False
