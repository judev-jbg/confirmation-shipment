"""
Servicio para interactuar con la API de PrestaShop.
Maneja consultas de pedidos, clientes, direcciones y actualización de estados.
Específico para confirmación de envíos (estado 3).
"""

import logging
import requests
import xmltodict
from typing import Dict, List, Any, Optional
from requests.auth import HTTPBasicAuth

logger = logging.getLogger("ConfirmationShipmentLogger")


class PrestaShopService:
    """Servicio para interactuar con PrestaShop API."""

    def __init__(self, api_url: str, username: str, password: str):
        """
        Inicializa el servicio de PrestaShop.

        Args:
            api_url: URL base de la API de PrestaShop
            username: Usuario para autenticación
            password: Contraseña para autenticación
        """
        self.api_url = api_url
        self.auth = HTTPBasicAuth(username, password)

    def fetch_pending_shipment_orders(self) -> Optional[List[Dict[str, Any]]]:
        """
        Consulta la API de PrestaShop para obtener pedidos pendientes de envío.

        Filtros:
        - Métodos de pago: PayPal, Redsys, PayPal with fee, Pagos por transferencia bancaria
        - Estados: 3 (Preparación en curso - listos para enviar)

        Returns:
            Lista de pedidos o None si hay error
        """
        try:
            url = f"{self.api_url}/orders"
            params = {
                "filter[payment]": "[PayPal|Redsys|PayPal with fee|Pagos por transferencia bancaria]",
                "filter[current_state]": "[3]",
                "display": "full"
            }

            logger.info(f"Consultando pedidos pendientes de envío: {url}")
            response = requests.get(url, params=params, auth=self.auth, timeout=30)
            response.raise_for_status()

            # Verificar que hay contenido en la respuesta
            if not response.text or response.text.strip() == "":
                logger.warning("La API devolvió una respuesta vacía")
                return []

            # Parsear XML a diccionario
            try:
                data = xmltodict.parse(response.text)
            except Exception as parse_error:
                logger.error(f"Error al parsear XML: {parse_error}")
                logger.debug(f"Respuesta recibida (primeros 500 chars): {response.text[:500]}")
                return None

            # Normalizar estructura de órdenes
            orders = self._normalize_orders(data)

            # Filtrar solo pedidos con número de seguimiento
            orders_with_tracking = self._filter_orders_with_tracking(orders)

            logger.info(f"Se encontraron {len(orders)} pedidos en estado 3, {len(orders_with_tracking)} con número de seguimiento")
            return orders_with_tracking

        except requests.exceptions.RequestException as e:
            logger.error(f"Error al consultar pedidos: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Código de estado HTTP: {e.response.status_code}")
                logger.debug(f"Respuesta del servidor: {e.response.text[:500]}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al procesar respuesta: {e}", exc_info=True)
            return None

    def _normalize_orders(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Normaliza la estructura de órdenes desde el XML de PrestaShop.

        Args:
            data: Datos parseados del XML

        Returns:
            Lista normalizada de órdenes
        """
        try:
            if not data:
                logger.warning("Datos de entrada vacíos en _normalize_orders")
                return []

            prestashop = data.get("prestashop")
            if not prestashop:
                logger.warning("No se encontró nodo 'prestashop' en la respuesta XML")
                logger.debug(f"Estructura recibida: {list(data.keys())}")
                return []

            orders_data = prestashop.get("orders")
            if not orders_data:
                logger.info("No se encontró nodo 'orders' en la respuesta - no hay pedidos pendientes")
                return []

            order_data = orders_data.get("order", [])

            # Si es un solo pedido, convertir a lista
            if isinstance(order_data, dict):
                logger.debug("Se encontró un solo pedido, convirtiéndolo a lista")
                return [order_data]
            elif isinstance(order_data, list):
                logger.debug(f"Se encontraron {len(order_data)} pedidos")
                return order_data
            else:
                logger.warning(f"Tipo de dato inesperado para 'order': {type(order_data)}")
                return []

        except Exception as e:
            logger.error(f"Error al normalizar órdenes: {e}", exc_info=True)
            return []

    def _filter_orders_with_tracking(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filtra pedidos que tengan número de seguimiento.

        Args:
            orders: Lista de pedidos

        Returns:
            Lista de pedidos con número de seguimiento
        """
        filtered_orders = []

        for order in orders:
            # Asegurar que el campo shipping_number existe
            shipping_number = order.get("shipping_number", {})

            # Si shipping_number no es un diccionario, convertirlo
            if not isinstance(shipping_number, dict):
                shipping_number = {"_": str(shipping_number) if shipping_number else ""}
                order["shipping_number"] = shipping_number

            # Si no tiene la clave "_", añadirla
            if "_" not in shipping_number:
                shipping_number["_"] = ""
                order["shipping_number"] = shipping_number

            # Verificar si tiene número de seguimiento
            tracking_value = shipping_number.get("_", "").strip()

            if tracking_value:
                logger.debug(f"Pedido {order.get('id')} tiene número de seguimiento: {tracking_value}")
                filtered_orders.append(order)
            else:
                logger.debug(f"Pedido {order.get('id')} no tiene número de seguimiento, se omite")

        return filtered_orders

    def fetch_customer_data(self, customer_url: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos del cliente desde PrestaShop.

        Args:
            customer_url: URL del recurso de cliente

        Returns:
            Diccionario con datos del cliente o None si hay error
        """
        try:
            logger.debug(f"Consultando datos del cliente: {customer_url}")
            response = requests.get(customer_url, auth=self.auth, timeout=30)
            response.raise_for_status()

            data = xmltodict.parse(response.text)
            customer = data.get("prestashop", {}).get("customer", {})

            # Extraer campos relevantes
            return {
                "id": customer.get("id"),
                "firstname": customer.get("firstname"),
                "lastname": customer.get("lastname"),
                "email": customer.get("email")
            }

        except Exception as e:
            logger.error(f"Error al obtener datos del cliente: {e}")
            return None

    def fetch_address_data(self, address_url: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos de la dirección desde PrestaShop.

        Args:
            address_url: URL del recurso de dirección

        Returns:
            Diccionario con datos de la dirección o None si hay error
        """
        try:
            logger.debug(f"Consultando dirección: {address_url}")
            response = requests.get(address_url, auth=self.auth, timeout=30)
            response.raise_for_status()

            data = xmltodict.parse(response.text)
            address = data.get("prestashop", {}).get("address", {})

            # Extraer campos relevantes
            id_customer = address.get("id_customer")
            if isinstance(id_customer, dict):
                id_customer = id_customer.get("_")

            return {
                "id": address.get("id"),
                "id_customer": id_customer,
                "address1": address.get("address1"),
                "address2": address.get("address2"),
                "postcode": address.get("postcode"),
                "city": address.get("city")
            }

        except Exception as e:
            logger.error(f"Error al obtener dirección: {e}")
            return None

    def update_order_state(self, order_id: str, new_state: int = 4) -> bool:
        """
        Actualiza el estado del pedido en PrestaShop.

        Args:
            order_id: ID del pedido
            new_state: Nuevo estado (por defecto 4 = "Enviado")

        Returns:
            True si se actualizó correctamente, False en caso contrario
        """
        try:
            logger.info(f"Actualizando estado del pedido {order_id} a estado {new_state}")

            # Crear XML para order_history
            xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<prestashop xmlns:xlink="http://www.w3.org/1999/xlink">
    <order_history>
        <id_order>{order_id}</id_order>
        <id_employee>5</id_employee>
        <id_order_state>{new_state}</id_order_state>
    </order_history>
</prestashop>"""

            url = f"{self.api_url}/order_histories"
            headers = {"Content-Type": "application/xml"}

            response = requests.post(
                url,
                data=xml_payload,
                headers=headers,
                auth=self.auth,
                timeout=30
            )
            response.raise_for_status()

            logger.info(f"Estado del pedido {order_id} actualizado correctamente")
            return True

        except Exception as e:
            logger.error(f"Error al actualizar estado del pedido {order_id}: {e}")
            return False
