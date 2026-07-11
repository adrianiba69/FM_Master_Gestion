from datetime import datetime, timedelta, timezone
import time
import xml.etree.ElementTree as ET


class WSAAService:

	@staticmethod
	def generar_tra(servicio="wsfe", duracion_segundos=3600):
		servicio_normalizado = str(servicio or "").strip()
		if not servicio_normalizado:
			raise ValueError("El servicio no puede estar vacio.")

		try:
			duracion = int(duracion_segundos)
		except (TypeError, ValueError) as error:
			raise ValueError("La duracion debe ser un numero mayor a cero.") from error

		if duracion <= 0:
			raise ValueError("La duracion debe ser mayor a cero.")

		ahora_utc = datetime.now(timezone.utc)
		generation_time = ahora_utc - timedelta(minutes=5)
		expiration_time = ahora_utc + timedelta(seconds=duracion)
		unique_id = str(int(time.time() * 1000))

		login_ticket_request = ET.Element("loginTicketRequest", attrib={"version": "1.0"})
		header = ET.SubElement(login_ticket_request, "header")
		ET.SubElement(header, "uniqueId").text = unique_id
		ET.SubElement(header, "generationTime").text = generation_time.replace(microsecond=0).isoformat().replace(
			"+00:00", "Z"
		)
		ET.SubElement(header, "expirationTime").text = expiration_time.replace(microsecond=0).isoformat().replace(
			"+00:00", "Z"
		)
		ET.SubElement(login_ticket_request, "service").text = servicio_normalizado

		xml_bytes = ET.tostring(login_ticket_request, encoding="utf-8", xml_declaration=True)
		return xml_bytes.decode("utf-8")

