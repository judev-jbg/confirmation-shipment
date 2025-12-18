"""
Procesador de pedidos para confirmación de envíos.
Orquesta el flujo completo de procesamiento de pedidos con número de seguimiento.
"""

import logging
from datetime import datetime
from typing import Dict, Any

from .prestashop_service import PrestaShopService
from .email_service import EmailService
from .notifications import NotificationManager

logger = logging.getLogger("ConfirmationShipmentLogger")


class OrderProcessor:
    """Procesador de pedidos de confirmación de envíos."""

    def __init__(self, prestashop_service: PrestaShopService,
                 email_service: EmailService,
                 notification_manager: NotificationManager):
        """
        Inicializa el procesador de pedidos.

        Args:
            prestashop_service: Servicio de PrestaShop
            email_service: Servicio de email
            notification_manager: Gestor de notificaciones
        """
        self.prestashop_service = prestashop_service
        self.email_service = email_service
        self.notification_manager = notification_manager

        # Estadísticas de la ejecución
        self.stats = {
            "orders_processed": 0,
            "orders_success": 0,
            "orders_failed": 0,
            "errors": []
        }

    def process_single_order(self, order: Dict[str, Any]) -> bool:
        """
        Procesa un único pedido: obtiene datos, genera email, envía y actualiza estado.

        Args:
            order: Datos del pedido

        Returns:
            True si se procesó correctamente, False en caso contrario
        """
        try:
            order_id = order.get("id")
            order_reference = order.get("reference")
            tracking_number = order.get("shipping_number", {}).get("_", "")

            logger.info(f"Procesando pedido {order_reference} (ID: {order_id}) - Seguimiento: {tracking_number}")

            # Obtener URLs de recursos relacionados
            customer_url = self._extract_xlink_href(order.get("id_customer"))
            address_url = self._extract_xlink_href(order.get("id_address_delivery"))

            if not customer_url or not address_url:
                logger.error(f"Pedido {order_id} no tiene URLs de cliente o dirección")
                return False

            # Obtener datos del cliente
            customer = self.prestashop_service.fetch_customer_data(customer_url)
            if not customer:
                logger.error(f"No se pudo obtener datos del cliente para pedido {order_id}")
                return False

            # Obtener datos de la dirección
            address = self.prestashop_service.fetch_address_data(address_url)
            if not address:
                logger.error(f"No se pudo obtener dirección para pedido {order_id}")
                return False

            # Generar plantilla de email
            html_content = self.email_service.generate_email_template(order, customer, address)
            if not html_content:
                logger.error(f"No se pudo generar plantilla para pedido {order_id}")
                return False

            # Enviar email de confirmación de envío
            email_sent = self.email_service.send_shipment_confirmation_email(
                customer["email"],
                order_reference,
                html_content
            )

            if not email_sent:
                logger.error(f"No se pudo enviar email para pedido {order_id}")
                return False

            # Actualizar estado del pedido a 4 (Enviado)
            state_updated = self.prestashop_service.update_order_state(order_id, new_state=4)

            if not state_updated:
                logger.warning(f"Email enviado pero no se pudo actualizar estado del pedido {order_id}")
                # Consideramos éxito parcial, ya que el email se envió

            logger.info(f"Pedido {order_reference} procesado correctamente")
            return True

        except Exception as e:
            logger.error(f"Error al procesar pedido: {e}")
            self.stats["errors"].append({
                "order_id": order.get("id"),
                "error": str(e)
            })
            return False

    def _extract_xlink_href(self, field: Any) -> str:
        """
        Extrae la URL de un campo con xlink:href.

        Args:
            field: Campo que puede contener @xlink:href

        Returns:
            URL extraída o None
        """
        if isinstance(field, dict):
            return field.get("@xlink:href")
        return None

    async def send_execution_summary(self):
        """Envía un resumen de la ejecución vía notificaciones."""
        try:
            if self.stats["orders_processed"] == 0:
                # No hay nada que reportar
                return

            success_rate = (self.stats["orders_success"] / self.stats["orders_processed"]) * 100 if self.stats["orders_processed"] > 0 else 0

            message = f"""
Procesamiento de envíos completado:
- Total de pedidos: {self.stats['orders_processed']}
- Exitosos: {self.stats['orders_success']}
- Fallidos: {self.stats['orders_failed']}
- Tasa de éxito: {success_rate:.1f}%
"""

            if self.stats["orders_failed"] > 0:
                # Hay errores, enviar como advertencia
                error_details = {
                    "total_orders": self.stats["orders_processed"],
                    "successful": self.stats["orders_success"],
                    "failed": self.stats["orders_failed"],
                    "errors": self.stats["errors"][:5]  # Primeros 5 errores
                }

                await self.notification_manager.notify_warning(
                    "Ejecución de envíos completada con errores",
                    message,
                    error_details
                )
            else:
                # Todo OK, enviar como éxito
                await self.notification_manager.notify_success(
                    "Ejecución de envíos completada exitosamente",
                    message
                )

        except Exception as e:
            logger.error(f"Error al enviar resumen de ejecución: {e}")

    async def process_all_orders_async(self):
        """Procesa todos los pedidos pendientes de envío de forma asíncrona."""
        try:
            logger.info("=" * 80)
            logger.info("Iniciando proceso de confirmación de envíos")
            logger.info("=" * 80)

            # Consultar pedidos pendientes de envío (estado 3 con número de seguimiento)
            orders = self.prestashop_service.fetch_pending_shipment_orders()

            if orders is None:
                logger.error("Error al consultar pedidos")
                await self.notification_manager.notify_critical_error(
                    "Error al consultar PrestaShop API",
                    "No se pudo conectar con la API de PrestaShop para obtener pedidos pendientes de envío",
                    {"timestamp": datetime.now().isoformat()}
                )
                return

            if len(orders) == 0:
                logger.info("No hay pedidos pendientes de envío para procesar")
                return

            # Procesar cada pedido
            for order in orders:
                self.stats["orders_processed"] += 1

                success = self.process_single_order(order)

                if success:
                    self.stats["orders_success"] += 1
                else:
                    self.stats["orders_failed"] += 1

            # Enviar resumen
            await self.send_execution_summary()

            logger.info("=" * 80)
            logger.info(f"Proceso completado - Procesados: {self.stats['orders_processed']}, "
                       f"Exitosos: {self.stats['orders_success']}, "
                       f"Fallidos: {self.stats['orders_failed']}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Error crítico en el proceso principal: {e}", exc_info=True)
            await self.notification_manager.notify_critical_error(
                "Error crítico en proceso de confirmación de envíos",
                str(e),
                {"timestamp": datetime.now().isoformat(), "traceback": str(e)}
            )
