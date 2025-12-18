"""
Módulo para envío de notificaciones por email y Slack.
Utilizado para notificar eventos en la confirmación de envíos.
"""
import asyncio
import aiohttp
import aiosmtplib
import os
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Configurar logging para este módulo
logger = logging.getLogger("ConfirmationShipmentLogger")


class NotificationManager:
    """Gestor de notificaciones para email y Slack."""

    def __init__(self):
        """Inicializar el gestor con configuración desde variables de entorno."""
        load_dotenv()

        # Configuración de email
        self.email_config = {
            "smtp_server": os.getenv("SMTP_SERVER", "smtp.office365.com"),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "sender_email": os.getenv("SENDER_EMAIL"),
            "sender_password": os.getenv("SENDER_PASSWORD"),
            "notification_emails": self._parse_email_list(os.getenv("NOTIFICATION_EMAILS", "")),
            "enabled": os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "true").lower() == "true"
        }

        # Configuración de Slack
        self.slack_config = {
            "webhook_url": os.getenv("SLACK_WEBHOOK_URL", ""),
            "enabled": os.getenv("SLACK_NOTIFICATIONS_ENABLED", "true").lower() == "true",
            "channel": os.getenv("SLACK_CHANNEL", "#confirmation-shipment"),
            "username": os.getenv("SLACK_USERNAME", "ConfirmationShipment-Bot")
        }

        # Validar configuración
        self._validate_config()

    def _parse_email_list(self, email_string: str) -> List[str]:
        """Parsea una cadena de emails separados por coma."""
        if not email_string:
            return []
        return [email.strip() for email in email_string.split(",") if email.strip()]

    def _validate_config(self):
        """Valida la configuración de notificaciones."""
        if self.email_config["enabled"]:
            if not all([
                self.email_config["sender_email"],
                self.email_config["sender_password"],
                self.email_config["notification_emails"]
            ]):
                logger.warning(
                    "Email notifications enabled but missing configuration. Disabling email notifications.")
                self.email_config["enabled"] = False

        if self.slack_config["enabled"]:
            if not self.slack_config["webhook_url"]:
                logger.warning(
                    "Slack notifications enabled but webhook URL missing. Disabling Slack notifications.")
                self.slack_config["enabled"] = False

    async def send_email_notification(self, subject: str, message: str, error_details: Optional[Dict[str, Any]] = None, is_critical: bool = False):
        """
        Envía notificación por email.

        Args:
            subject: Asunto del email
            message: Mensaje principal
            error_details: Detalles adicionales del error
            is_critical: Si es un error crítico (afecta el formato del mensaje)
        """
        if not self.email_config["enabled"]:
            logger.info("Email notifications are disabled")
            return False

        try:
            # Crear el mensaje de email
            email_msg = MIMEMultipart("alternative")
            email_msg["From"] = self.email_config["sender_email"]
            email_msg["To"] = ", ".join(
                self.email_config["notification_emails"])

            # Añadir prefijo según criticidad
            priority_prefix = "[ERROR CRÍTICO]" if is_critical else "[ADVERTENCIA]"
            email_msg["Subject"] = f"{priority_prefix} - Confirmación de Envíos: {subject}"

            # Crear contenido HTML y texto plano
            html_content = self._create_html_email_content(
                subject, message, error_details, is_critical)
            plain_content = self._create_plain_email_content(
                subject, message, error_details, is_critical)

            # Adjuntar ambos formatos
            email_msg.attach(MIMEText(plain_content, "plain", "utf-8"))
            email_msg.attach(MIMEText(html_content, "html", "utf-8"))

            # Enviar email usando aiosmtplib
            await aiosmtplib.send(
                email_msg,
                hostname=self.email_config["smtp_server"],
                port=self.email_config["smtp_port"],
                start_tls=True,
                username=self.email_config["sender_email"],
                password=self.email_config["sender_password"],
                timeout=30
            )

            logger.info(
                f"Email notification sent successfully to {len(self.email_config['notification_emails'])} recipients")
            return True

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False

    async def send_slack_notification(self, message: str, error_details: Optional[Dict[str, Any]] = None, is_critical: bool = False, type: str = "info"):
        """
        Envía notificación por Slack.

        Args:
            message: Mensaje principal
            error_details: Detalles adicionales del error
            is_critical: Si es un error crítico
            type: Tipo de notificación (info, warning, error)
        """
        if not self.slack_config["enabled"]:
            logger.info("Slack notifications are disabled")
            return False

        try:
            # Crear el payload para Slack
            slack_payload = self._create_slack_payload(
                message, error_details, is_critical, type=type)

            # Enviar usando aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.slack_config["webhook_url"],
                    json=slack_payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info("Slack notification sent successfully")
                        return True
                    else:
                        logger.error(f"Slack API returned status {response.status}: {await response.text()}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False

    async def send_critical_notification(self, title: str, message: str, error_details: Optional[Dict[str, Any]] = None):
        """
        Envía notificación crítica por todos los canales disponibles.

        Args:
            title: Título/asunto de la notificación
            message: Mensaje descriptivo del problema
            error_details: Detalles técnicos del error
        """
        logger.info(f"Sending critical notification: {title}")

        # Enviar por ambos canales simultáneamente
        email_task = self.send_email_notification(
            title, message, error_details, is_critical=True)
        slack_task = self.send_slack_notification(
            f"{title}: {message}", error_details, is_critical=True, type="error")

        # Ejecutar ambas tareas
        email_result, slack_result = await asyncio.gather(email_task, slack_task, return_exceptions=True)

        # Log results
        if isinstance(email_result, Exception):
            logger.error(f"Email notification failed: {email_result}")
            email_result = False

        if isinstance(slack_result, Exception):
            logger.error(f"Slack notification failed: {slack_result}")
            slack_result = False

        success = email_result or slack_result
        if success:
            logger.info(
                "At least one critical notification was sent successfully")
        else:
            logger.error("All critical notification channels failed")

        return success

    async def send_info_notification(self, title: str, message: str, type: str = "info"):
        """
        Envía notificación informativa (no crítica).

        Args:
            title: Título de la notificación
            message: Mensaje informativo
            type: Tipo de notificación (info, success)
        """
        logger.info(f"Sending info notification: {title}")

        # Para notificaciones informativas, preferimos Slack
        slack_result = await self.send_slack_notification(f"{title}: {message}", is_critical=False, type=type)

        if not slack_result:
            # Si Slack falla, enviar por email como respaldo
            email_result = await self.send_email_notification(title, message, is_critical=False)
            return email_result

        return slack_result

    def _create_html_email_content(self, subject: str, message: str, error_details: Optional[Dict[str, Any]], is_critical: bool) -> str:
        """Crea contenido HTML para el email."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Rojo para crítico, amarillo para advertencia
        color = "#dc3545" if is_critical else "#ffc107"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f8f9fa; padding: 20px; border: 1px solid #dee2e6; }}
                .footer {{ background-color: #e9ecef; padding: 10px; border-radius: 0 0 5px 5px; font-size: 12px; color: #6c757d; }}
                .details {{ background-color: #ffffff; padding: 15px; margin: 15px 0; border-left: 4px solid {color}; }}
                .timestamp {{ font-weight: bold; }}
                pre {{ background-color: #f1f1f1; padding: 10px; border-radius: 3px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{'🚨 Error' if is_critical else '⚠️ Advertencia'} - Confirmación de Envíos</h2>
            </div>
            <div class="content">
                <p><strong>Problema detectado:</strong> {subject}</p>
                <p><strong>Descripción:</strong> {message}</p>
                <p class="timestamp"><strong>Fecha y hora:</strong> {timestamp}</p>

                {self._format_error_details_html(error_details) if error_details else ""}

                <div style="margin-top: 20px; padding: 15px; background-color: {'#f8d7da' if is_critical else '#fff3cd'}; border-radius: 5px;">
                    <strong>{'Acción requerida:' if is_critical else 'Recomendación:'}</strong>
                    <ul>
                        <li>Revisar los logs del sistema</li>
                        <li>{'Intervención inmediata requerida' if is_critical else 'Monitorear la situación'}</li>
                        <li>Contactar al equipo técnico si el problema persiste</li>
                    </ul>
                </div>
            </div>
            <div class="footer">
                Confirmación de Envíos - Sistema Automatizado - Generado automáticamente
            </div>
        </body>
        </html>
        """
        return html

    def _create_plain_email_content(self, subject: str, message: str, error_details: Optional[Dict[str, Any]], is_critical: bool) -> str:
        """Crea contenido de texto plano para el email."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        priority = "CRÍTICO" if is_critical else "ADVERTENCIA"

        content = f"""
{priority} - Confirmación de Envíos

Problema detectado: {subject}
Descripción: {message}
Fecha y hora: {timestamp}

{self._format_error_details_plain(error_details) if error_details else ""}

{'Acción requerida:' if is_critical else 'Recomendación:'}
- Revisar los logs del sistema
- {'Intervención inmediata requerida' if is_critical else 'Monitorear la situación'}
- Contactar al equipo técnico si el problema persiste

---
Confirmación de Envíos - Sistema Automatizado - Generado automáticamente
        """
        return content.strip()

    def _create_slack_payload(self, message: str, error_details: Optional[Dict[str, Any]], is_critical: bool, type: str = "info") -> Dict[str, Any]:
        """Crea el payload para Slack webhook usando el formato moderno de blocks."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Emoji y color según criticidad
        emoji = "ℹ️" if type == "info" else "✅" if type == "success" else "🚨" if is_critical else "⚠️"
        status_text = "INFO" if type == "info" else "ÉXITO" if type == "success" else "ERROR CRÍTICO" if is_critical else "ADVERTENCIA"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {status_text} - Confirmación de Envíos",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Descripción*\n```{message}```"
                }
            }
        ]

        # Añadir detalles del error si están disponibles
        if error_details:
            details_text = self._format_error_details_slack(error_details)
            # Limitar la longitud del texto para evitar errores de Slack
            if len(details_text) > 2000:
                details_text = details_text[:1997] + "..."

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Detalles técnicos:*\n```{details_text}```"
                }
            })

        # Añadir acciones recomendadas
        if is_critical:
            action_text = "Intervención inmediata requerida"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Acción recomendada:* {action_text}"
                }
            })

        # Añadir contexto en el footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Confirmación de Envíos - Sistema Automatizado | `Timestamp: {timestamp}`"
                }
            ]
        })

        # Payload simplificado usando solo blocks
        payload = {
            "username": self.slack_config["username"],
            "blocks": blocks
        }

        # Solo añadir canal si está especificado y es diferente al por defecto
        if self.slack_config["channel"] and self.slack_config["channel"] != "#general":
            payload["channel"] = self.slack_config["channel"]

        return payload

    def _format_error_details_html(self, error_details: Dict[str, Any]) -> str:
        """Formatea detalles del error para HTML."""
        html = '<div class="details"><h4>Detalles técnicos:</h4>'

        for key, value in error_details.items():
            html += f'<p><strong>{key.replace("_", " ").title()}:</strong></p>'
            if isinstance(value, (dict, list)):
                html += f'<pre>{str(value)}</pre>'
            else:
                html += f'<p style="margin-left: 20px;">{value}</p>'

        html += '</div>'
        return html

    def _format_error_details_plain(self, error_details: Dict[str, Any]) -> str:
        """Formatea detalles del error para texto plano."""
        details = "Detalles técnicos:\n"

        for key, value in error_details.items():
            details += f"\n{key.replace('_', ' ').title()}:\n{value}\n"

        return details

    def _format_error_details_slack(self, error_details: Dict[str, Any]) -> str:
        """Formatea detalles del error para Slack."""
        details = []

        for key, value in error_details.items():
            details.append(f"{key.replace('_', ' ').title()}: {value}")

        return "\n".join(details)

    async def notify_critical_error(self, title: str, message: str, error_details: Optional[Dict[str, Any]] = None):
        """Función de conveniencia para notificar errores críticos."""
        return await self.send_critical_notification(title, message, error_details)

    async def notify_warning(self, title: str, message: str, error_details: Optional[Dict[str, Any]] = None):
        """Función de conveniencia para notificar advertencias."""
        email_result = await self.send_email_notification(title, message, error_details, is_critical=False)
        slack_result = await self.send_slack_notification(f"{title}: {message}", error_details, is_critical=False, type="warning")
        return email_result or slack_result

    async def notify_info(self, title: str, message: str):
        """Función de conveniencia para notificar información."""
        return await self.send_info_notification(title, message, "info")

    async def notify_success(self, title: str, message: str):
        """Función de conveniencia para notificar éxito."""
        return await self.send_info_notification(title, message, "success")


def run_notification_sync(coro):
    """Helper para ejecutar notificaciones desde código síncrono."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Si ya hay un loop corriendo, crear una tarea
            task = asyncio.create_task(coro)
            return task
        else:
            # Si no hay loop, usar run
            return loop.run_until_complete(coro)
    except RuntimeError:
        # Si no hay loop, crear uno nuevo
        return asyncio.run(coro)
