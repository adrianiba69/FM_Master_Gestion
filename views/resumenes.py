import os
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from models.factura_arca import FacturaArca
from pdf.nombre_archivos import nombre_factura_pdf
from pdf.resumen_pdf import ResumenPDF
from runtime_paths import PDF_DIR
from services.arca.homologacion_service import HomologacionService
from services.arca.pdf_fiscal_service import PDFFiscalService
from services.cliente_service import ClienteService
from services.emisor_fiscal_service import EmisorFiscalService
from services.emisor_service import EmisorService
from services.factura_arca_service import FacturaArcaService
from services.resumen_service import ResumenService
from services.whatsapp_service import WhatsAppService


class ResumenesFrame(ctk.CTkFrame):
    # Criterio fiscal explícito para Factura A: los importes de servicios/resumen se
    # interpretan como NETOS gravados y se adiciona IVA en la emisión.
    FACTURA_A_SERVICIOS_IMPORTE_ES_NETO = True
    FACTURA_A_ALICUOTA_PORCENTAJE = 21.0

    def __init__(self, master, cliente_id=None, on_cambio=None, contexto_facturacion=None):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.clientes_por_nombre = {}
        self.cliente_inicial = cliente_id
        self.on_cambio = on_cambio
        self.contexto_facturacion_cliente = {}
        self.contexto_facturacion_pendiente = {}
        self.ultimo_contexto_facturacion = None
        if isinstance(contexto_facturacion, dict):
            cliente_ctx_id = contexto_facturacion.get("cliente_id")
            if cliente_ctx_id is not None:
                self.contexto_facturacion_cliente[int(cliente_ctx_id)] = dict(contexto_facturacion)
        self.crear_interfaz()
        self.cargar_clientes()
        self.cargar_resumenes()

    def _obtener_contexto_facturacion(self, cliente_id):
        contexto = self.contexto_facturacion_cliente.get(cliente_id)
        if contexto:
            return contexto

        fila = ClienteService.obtener(cliente_id)
        if not fila:
            return {
                "cliente_id": cliente_id,
                "modalidad_comprobante": "Solo Resumen",
                "emisor_habitual": "FM Master 98.3",
                "tipo_factura": "No factura",
                "condicion_iva": "",
            }

        contexto = {
            "cliente_id": cliente_id,
            "modalidad_comprobante": fila[21] if len(fila) > 21 and fila[21] else "Solo Resumen",
            "emisor_habitual": fila[22] if len(fila) > 22 and fila[22] else "FM Master 98.3",
            "tipo_factura": fila[12] if len(fila) > 12 and fila[12] else "No factura",
            "condicion_iva": fila[11] if len(fila) > 11 and fila[11] else "",
        }
        self.contexto_facturacion_cliente[cliente_id] = contexto
        return contexto

    def _leer_contexto_facturacion_desde_bd(self, cliente_id):
        fila = ClienteService.obtener(cliente_id)
        if not fila:
            return None

        contexto = {
            "cliente_id": cliente_id,
            "modalidad_comprobante": fila[21] if len(fila) > 21 and fila[21] else "Solo Resumen",
            "emisor_habitual": fila[22] if len(fila) > 22 and fila[22] else "FM Master 98.3",
            "tipo_factura": fila[12] if len(fila) > 12 and fila[12] else "No factura",
            "condicion_iva": fila[11] if len(fila) > 11 and fila[11] else "",
        }
        self.contexto_facturacion_cliente[cliente_id] = contexto
        return contexto

    def crear_interfaz(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        titulo = ctk.CTkLabel(
            self,
            text="RESÚMENES",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        )
        titulo.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        emision = ctk.CTkFrame(self, fg_color="#F4F4F4", corner_radius=4)
        emision.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        emision.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(emision, text="Cliente", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=(14, 8), pady=(10, 0)
        )
        ctk.CTkLabel(emision, text="Fecha", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=8, pady=(10, 0)
        )
        ctk.CTkLabel(emision, text="Vencimiento", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=8, pady=(10, 0)
        )

        self.selector_cliente = ctk.CTkComboBox(
            emision,
            values=[""],
            width=340,
            command=lambda _valor: self.actualizar_vencimiento(),
        )
        self.selector_cliente.grid(row=1, column=0, sticky="ew", padx=(14, 8), pady=(4, 14))

        hoy = date.today().strftime("%d/%m/%Y")
        self.entrada_fecha = ctk.CTkEntry(emision, width=130)
        self.entrada_fecha.insert(0, hoy)
        self.entrada_fecha.grid(row=1, column=1, padx=8, pady=(4, 14))

        self.entrada_vencimiento = ctk.CTkEntry(emision, width=130)
        self.entrada_vencimiento.insert(0, hoy)
        self.entrada_vencimiento.grid(row=1, column=2, padx=8, pady=(4, 14))

        boton_generar = ctk.CTkButton(
            emision,
            text="Generar PDF",
            width=135,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.generar_resumen,
        )
        boton_generar.grid(row=1, column=3, padx=(10, 14), pady=(4, 14))

        barra = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        barra.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        barra.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            barra,
            text="Historial de resumenes",
            font=("Arial", 16, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w")

        self.boton_pendientes = ctk.CTkButton(
            barra,
            text="Generar resúmenes pendientes",
            width=205,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.abrir_resumenes_pendientes,
        )
        self.boton_pendientes.grid(row=0, column=1, padx=(10, 0))

        boton_abrir = ctk.CTkButton(
            barra,
            text="Abrir PDF",
            width=115,
            height=38,
            fg_color="#444444",
            hover_color="#222222",
            command=self.abrir_pdf_seleccionado,
        )
        boton_abrir.grid(row=0, column=2, padx=(10, 0))

        self.boton_whatsapp = ctk.CTkButton(
            barra,
            text="Enviar por WhatsApp",
            width=165,
            height=38,
            fg_color="#333333",
            hover_color="#111111",
            command=self.enviar_whatsapp_seleccionado,
        )
        self.boton_whatsapp.grid(row=0, column=3, padx=(10, 0))

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_rowconfigure(1, weight=0)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = (
            "id", "numero", "fecha", "vencimiento", "cliente",
            "total", "saldo", "estado", "pdf_path",
        )
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=16)
        encabezados = {
            "id": ("ID", 0),
            "numero": ("Resumen", 95),
            "fecha": ("Fecha", 100),
            "vencimiento": ("Vencimiento", 108),
            "cliente": ("Cliente", 360),
            "total": ("Total", 120),
            "saldo": ("Saldo", 120),
            "estado": ("Estado", 115),
            "pdf_path": ("PDF", 0),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(
                columna,
                width=ancho,
                minwidth=0 if columna == "pdf_path" else 40,
                stretch=columna in ("cliente",),
                anchor="e" if columna in ("total", "saldo") else "w",
            )

        self.tabla.tag_configure("estado_pendiente", foreground="#B88600")
        self.tabla.tag_configure("estado_vencido", foreground="#C00000")
        self.tabla.tag_configure("estado_pagado", foreground="#16823A")
        self.tabla.tag_configure("estado_facturado", foreground="#1E5AA8")
        self.tabla.tag_configure("estado_default", foreground="#222222")

        self.tabla.bind("<Double-1>", lambda _evento: self.abrir_pdf_seleccionado())
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        scroll_x = ttk.Scrollbar(tabla_frame, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=scroll.set, xscrollcommand=scroll_x.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    def cargar_clientes(self):
        clientes = ClienteService.listar()
        self.clientes_por_nombre = {
            f"{cliente[1] or '-'} - {cliente[2]}": cliente[0]
            for cliente in clientes
        }
        nombres = list(self.clientes_por_nombre)
        self.selector_cliente.configure(values=nombres or [""])

        seleccionado = ""
        if self.cliente_inicial is not None:
            seleccionado = next(
                (nombre for nombre, identificador in self.clientes_por_nombre.items()
                 if identificador == self.cliente_inicial),
                "",
            )
        if not seleccionado and nombres:
            seleccionado = nombres[0]
        self.selector_cliente.set(seleccionado)
        self.actualizar_vencimiento()

    def actualizar_vencimiento(self):
        cliente_id = self.clientes_por_nombre.get(self.selector_cliente.get())
        if cliente_id is None:
            return
        cliente = ClienteService.obtener(cliente_id)
        if cliente is None:
            return
        try:
            emision = datetime.strptime(self.entrada_fecha.get(), "%d/%m/%Y").date()
        except ValueError:
            emision = date.today()
        vencimiento = ResumenService.calcular_vencimiento(cliente, emision)
        self.entrada_vencimiento.delete(0, "end")
        self.entrada_vencimiento.insert(0, vencimiento.strftime("%d/%m/%Y"))

    def cargar_resumenes(self):
        for item in self.tabla.get_children():
            self.tabla.delete(item)

        for fila in ResumenService.listar():
            estado_cobro = (fila[7] or "").strip()
            datos_facturacion = ResumenService.obtener_datos_facturacion(fila[0]) or {}
            estado_facturacion = str(datos_facturacion.get("estado_facturacion") or "Pendiente").strip()
            estado = self._estado_resumen_para_grilla(estado_cobro, estado_facturacion)
            tag_estado = "estado_facturado" if estado_facturacion.lower() == "facturado" else self._tag_estado(estado_cobro)
            self.tabla.insert("", "end", values=(
                fila[0],
                f"{fila[1]:06d}",
                self.formatear_fecha(fila[2]),
                self.formatear_fecha(fila[3]),
                fila[4],
                self.formatear_moneda(fila[5]),
                self.formatear_moneda(fila[6]),
                estado,
                fila[8] or "",
            ), tags=(tag_estado,))

    def generar_resumen(self):
        cliente_id = self.clientes_por_nombre.get(self.selector_cliente.get())
        if cliente_id is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente.")
            return

        try:
            fecha = datetime.strptime(self.entrada_fecha.get().strip(), "%d/%m/%Y").date()
            vencimiento = datetime.strptime(
                self.entrada_vencimiento.get().strip(), "%d/%m/%Y"
            ).date()
        except ValueError:
            messagebox.showerror("Error", "Las fechas deben tener formato DD/MM/AAAA.")
            return

        try:
            resumen = ResumenService.generar_desde_servicios(
                cliente_id,
                fecha=fecha,
                fecha_vencimiento=vencimiento,
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("No se pudo generar", str(error))
            return
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo generar el resumen: {error}")
            return

        cliente_actual = ClienteService.obtener(resumen.cliente_id)
        if cliente_actual is None:
            messagebox.showerror(
                "No se pudo generar",
                "El resumen se guardó, pero no se pudo volver a leer el cliente para continuar el flujo.",
                parent=self,
            )
            return

        contexto_post = self._leer_contexto_facturacion_desde_bd(resumen.cliente_id)
        if contexto_post is None:
            messagebox.showerror(
                "No se pudo generar",
                "El resumen se guardó, pero no se pudo obtener la configuración actual del cliente.",
                parent=self,
            )
            return

        modalidad = str(contexto_post.get("modalidad_comprobante") or "Solo Resumen").strip()
        emisor_habitual = str(contexto_post.get("emisor_habitual") or "").strip()
        tipo_factura = str(contexto_post.get("tipo_factura") or "").strip()
        condicion_iva = str(contexto_post.get("condicion_iva") or "").strip()

        contexto_disponible = {
            **contexto_post,
            "resumen_id": resumen.id,
            "resumen_numero": resumen.numero,
            "fecha_resumen": resumen.fecha,
            "modalidad_comprobante": modalidad or "Solo Resumen",
            "emisor_habitual": emisor_habitual,
            "tipo_factura": tipo_factura,
            "condicion_iva": condicion_iva,
        }

        self.contexto_facturacion_pendiente[resumen.id] = contexto_disponible
        self.ultimo_contexto_facturacion = contexto_disponible

        self.cargar_resumenes()
        if callable(self.on_cambio):
            self.on_cambio()

        if modalidad == "Solo Resumen":
            try:
                ruta = ResumenPDF.generar(resumen.id)
            except (ValueError, OSError) as error:
                messagebox.showerror("No se pudo generar", str(error), parent=self)
                return
            self.mostrar_modal_resumen_generado(ruta)
            return

        if modalidad in ("Resumen + Factura", "Solo Factura"):
            accion = self._mostrar_vista_previa_resumen_para_factura(resumen)
            if accion == "cancelar":
                return
            if accion == "guardar":
                messagebox.showinfo(
                    "Resumen generado",
                    "Resumen guardado correctamente. Puede emitir la factura más tarde.",
                    parent=self,
                )
                return
            if accion == "emitir":
                self._emitir_factura_arca_desde_resumen(resumen, contexto_disponible)
            return

        messagebox.showinfo(
            "Resumen generado",
            "Resumen guardado correctamente.",
            parent=self,
        )

    def _emitir_factura_arca_desde_resumen(self, resumen, contexto):
        if resumen is None:
            messagebox.showerror(
                "Emitir factura",
                "No se encontró el resumen recién generado.",
                parent=self,
            )
            return

        facturas_existentes = FacturaArcaService.listar_por_resumen(resumen.id)
        if facturas_existentes:
            factura_existente = facturas_existentes[0]
            numero_factura = str(factura_existente[9] if len(factura_existente) > 9 else "" or "-").strip()
            cae = str(factura_existente[10] if len(factura_existente) > 10 else "" or "-").strip()
            messagebox.showwarning(
                "Emitir factura",
                "El resumen ya tiene una factura asociada. No se realizará una nueva emisión.\n\n"
                f"Comprobante: {numero_factura}\n"
                f"CAE: {cae}",
                parent=self,
            )
            return

        if str(resumen.estado_facturacion or "").strip().lower() == "facturado":
            numero_factura = str(getattr(resumen, "numero_factura", "") or "-").strip()
            cae = str(getattr(resumen, "cae", "") or "-").strip()
            messagebox.showwarning(
                "Emitir factura",
                "El resumen ya figura como facturado. No se realizará una nueva emisión.\n\n"
                f"Comprobante: {numero_factura}\n"
                f"CAE: {cae}",
                parent=self,
            )
            return

        cliente = ClienteService.obtener(resumen.cliente_id)
        if not cliente:
            messagebox.showerror(
                "Emitir factura",
                "No se encontraron los datos del cliente para facturar.",
                parent=self,
            )
            return

        modalidad = str(contexto.get("modalidad_comprobante") or "Solo Resumen").strip()
        emisor_habitual = str(contexto.get("emisor_habitual") or "").strip()
        tipo_factura = str(contexto.get("tipo_factura") or "").strip()
        condicion_iva = str(contexto.get("condicion_iva") or "").strip()

        faltantes = []
        if not emisor_habitual:
            faltantes.append("Emisor habitual")
        if not tipo_factura:
            faltantes.append("Tipo de factura")
        if not condicion_iva:
            faltantes.append("Condición de IVA")
        if not getattr(resumen, "conceptos", None):
            faltantes.append("Ítems del resumen")

        if faltantes:
            messagebox.showerror(
                "Emitir factura",
                "No se puede facturar porque faltan datos obligatorios:\n- " + "\n- ".join(faltantes),
                parent=self,
            )
            return

        tipo_factura_normalizado = str(tipo_factura or "").strip()
        if tipo_factura_normalizado not in {"Factura C", "Factura A"}:
            messagebox.showerror(
                "Emitir factura",
                "El tipo de factura configurado no es compatible con este flujo automático (solo Factura C / Factura A).",
                parent=self,
            )
            return

        emisor_fiscal = self._buscar_emisor_fiscal_por_etiqueta(emisor_habitual)
        if not emisor_fiscal:
            messagebox.showerror(
                "Emitir factura",
                "No se encontró el emisor habitual configurado para iniciar la emisión.",
                parent=self,
            )
            return

        emisor_fiscal_id = emisor_fiscal[0]
        emisor_facturacion_id, campo_vinculo = self._resolver_emisor_facturacion_id(cliente, emisor_fiscal)
        if emisor_facturacion_id is None:
            print("DIAGNOSTICO VINCULACION EMISOR")
            print(f"emisor_fiscal_id_recibido: {emisor_fiscal_id}")
            print("emisor_interno_encontrado: None")
            print(f"campo_usado_vinculo: {campo_vinculo}")
            messagebox.showerror(
                "Emitir factura",
                "No se pudo vincular el emisor interno de facturación para registrar la factura.",
                parent=self,
            )
            return

        cuit_emisor = str(emisor_fiscal[3] if len(emisor_fiscal) > 3 else "" or "").strip()
        punto_venta = emisor_fiscal[6] if len(emisor_fiscal) > 6 else ""
        ruta_certificado = str(emisor_fiscal[11] if len(emisor_fiscal) > 11 else "" or "").strip()
        ruta_clave = str(emisor_fiscal[12] if len(emisor_fiscal) > 12 else "" or "").strip()
        carpeta_facturas = str(emisor_fiscal[13] if len(emisor_fiscal) > 13 else "" or "").strip()

        cuit_emisor_normalizado = self._normalizar_cuit(cuit_emisor)
        punto_venta_normalizado = self._normalizar_punto_venta(punto_venta)
        if not cuit_emisor_normalizado:
            messagebox.showerror(
                "Emitir factura",
                "El CUIT del emisor habitual es inválido.",
                parent=self,
            )
            return
        if punto_venta_normalizado is None:
            messagebox.showerror(
                "Emitir factura",
                "El punto de venta del emisor habitual es inválido.",
                parent=self,
            )
            return

        condicion_iva_emisor = str(emisor_fiscal[4] if len(emisor_fiscal) > 4 else "" or "").strip().lower()
        if tipo_factura_normalizado == "Factura A" and "responsable" not in condicion_iva_emisor:
            messagebox.showerror(
                "Emitir factura",
                "No se puede emitir Factura A: el emisor no está configurado como Responsable Inscripto.",
                parent=self,
            )
            return

        resumen_actual = ResumenService.obtener(resumen.id)
        if not resumen_actual:
            messagebox.showerror(
                "Emitir factura",
                "No se pudo recargar el resumen recién guardado para emitir.",
                parent=self,
            )
            return

        items_factura = self._armar_items_factura_desde_resumen(resumen_actual)
        if not items_factura:
            messagebox.showerror(
                "Emitir factura",
                "El resumen no tiene ítems válidos para facturación.",
                parent=self,
            )
            return

        suma_items = self._sumar_importes_items(items_factura)
        total_resumen = float(getattr(resumen_actual, "total", 0) or 0)
        diferencia = round(suma_items - total_resumen, 2)

        print("DIAGNOSTICO PREVIO EMISION ARCA")
        print(f"resumen_id: {resumen_actual.id}")
        print(f"cantidad_items: {len(items_factura)}")
        for idx, item in enumerate(items_factura, 1):
            print(
                f"item_{idx}: descripcion={item['descripcion']} | cantidad={item['cantidad']} | "
                f"precio_unitario={item['precio_unitario']} | importe={item['importe']}"
            )
        print(f"suma_items: {suma_items}")
        print(f"total_resumen: {total_resumen}")

        if abs(diferencia) > 0.01:
            detalle_diferencia = [
                "No se emitió la factura porque los importes no coinciden.",
                "",
                f"Suma de ítems: {self.formatear_moneda(suma_items)}",
                f"Total del resumen: {self.formatear_moneda(total_resumen)}",
                f"Diferencia: {self.formatear_moneda(diferencia)}",
                "",
                "Detalle utilizado:",
            ]
            for item in items_factura:
                detalle_diferencia.append(
                    f"- {item['descripcion']} | Cant: {item['cantidad']} | Unit: {self.formatear_moneda(item['precio_unitario'])} | "
                    f"Importe: {self.formatear_moneda(item['importe'])}"
                )

            messagebox.showerror(
                "Emitir factura",
                "\n".join(detalle_diferencia),
                parent=self,
            )
            return

        total_factura = float(round(suma_items, 2))
        if total_factura <= 0:
            messagebox.showerror(
                "Emitir factura",
                "El total del resumen es inválido para facturación.",
                parent=self,
            )
            return

        documento_cliente = str(cliente[10] if len(cliente) > 10 else "" or "").strip()
        documento_normalizado = "".join(char for char in documento_cliente if char.isdigit())
        condicion_iva_normalizada = condicion_iva.lower()
        if not documento_normalizado and condicion_iva_normalizada != "consumidor final":
            messagebox.showerror(
                "Emitir factura",
                "No se puede facturar porque falta CUIT o documento del cliente.",
                parent=self,
            )
            return

        if tipo_factura_normalizado == "Factura A":
            if "responsable" not in condicion_iva_normalizada:
                messagebox.showerror(
                    "Emitir factura",
                    "No se puede emitir Factura A: el cliente debe ser Responsable Inscripto.",
                    parent=self,
                )
                return
            if len(documento_normalizado) != 11:
                messagebox.showerror(
                    "Emitir factura",
                    "No se puede emitir Factura A: el cliente debe tener CUIT válido de 11 dígitos.",
                    parent=self,
                )
                return
            tipo_documento = 80
            documento_receptor = int(documento_normalizado)
        elif documento_normalizado and len(documento_normalizado) == 11:
            if condicion_iva_normalizada == "consumidor final":
                tipo_documento = 96
                documento_receptor = int(documento_normalizado[2:-1])
            else:
                tipo_documento = 80
                documento_receptor = int(documento_normalizado)
        else:
            tipo_documento = 99
            documento_receptor = 0

        tipo_comprobante = 1 if tipo_factura_normalizado == "Factura A" else 11
        if tipo_factura_normalizado == "Factura A":
            if not self.FACTURA_A_SERVICIOS_IMPORTE_ES_NETO:
                messagebox.showerror(
                    "Emitir factura",
                    "Configuración fiscal inválida: para Factura A este flujo requiere importes netos en servicios.",
                    parent=self,
                )
                return

            neto_factura = round(suma_items, 2)
            alicuota_iva = float(self.FACTURA_A_ALICUOTA_PORCENTAJE)
            importe_iva_factura = round(neto_factura * (alicuota_iva / 100.0), 2)
            total_factura_fiscal = round(neto_factura + importe_iva_factura, 2)
            importe_exento_factura = 0.0
            importe_tot_conc = 0.0
            importe_tributos = 0.0
            alicuotas_iva = [
                {
                    "id": 5,
                    "base_imponible": neto_factura,
                    "importe": importe_iva_factura,
                }
            ]
            condicion_iva_receptor_id = 1
        else:
            neto_factura = round(total_factura, 2)
            alicuota_iva = 0.0
            importe_iva_factura = 0.0
            total_factura_fiscal = round(total_factura, 2)
            importe_exento_factura = 0.0
            importe_tot_conc = 0.0
            importe_tributos = 0.0
            alicuotas_iva = []
            condicion_iva_receptor_id = 5

        if round(neto_factura + importe_iva_factura + importe_exento_factura + importe_tot_conc + importe_tributos, 2) != round(total_factura_fiscal, 2):
            messagebox.showerror(
                "Emitir factura",
                "No se puede emitir: los importes fiscales no cierran (neto + IVA + exento + no gravado + tributos != total).",
                parent=self,
            )
            return

        pre_guardado = FacturaArcaService.validar_pre_guardado(
            cliente_id=cliente[0],
            emisor_id=emisor_facturacion_id,
            resumen_id=resumen.id,
            fecha=date.today().isoformat(),
            punto_venta=str(punto_venta_normalizado),
            tipo_comprobante=tipo_factura_normalizado,
            importe_total=total_factura_fiscal,
            estado="Facturada manualmente",
        )
        if not pre_guardado.get("ok"):
            errores_pre = "\n- ".join(pre_guardado.get("errores") or ["Validación local fallida."])
            messagebox.showerror(
                "Emitir factura",
                "No se puede emitir en ARCA porque la factura no se puede persistir localmente.\n\n- " + errores_pre,
                parent=self,
            )
            return

        try:
            nombre_emisor = EmisorFiscalService.etiqueta_visible(emisor_fiscal)
            print("DIAGNOSTICO EMISION RESUMENES")
            print(f"emisor_id: {emisor_fiscal_id}")
            print(f"nombre_emisor: {nombre_emisor}")
            print(f"certificado_recibido: {ruta_certificado}")
            print(f"clave_privada_recibida: {ruta_clave}")
            print(f"carpeta_facturas_recibida: {carpeta_facturas}")
            print(f"emisor_interno_encontrado: {emisor_facturacion_id}")
            print(f"campo_usado_vinculo: {campo_vinculo}")
            print("funcion_emision: HomologacionService.emitir_comprobante_prueba")
            print(f"tipo_factura_emision: {tipo_factura_normalizado}")
            print(f"importe_neto_enviado_arca: {neto_factura}")
            print(f"importe_iva_enviado_arca: {importe_iva_factura}")
            print(f"importe_total_enviado_arca: {total_factura_fiscal}")

            fecha_comprobante = datetime.now().strftime("%Y%m%d")
            emision = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado=ruta_certificado,
                ruta_clave=ruta_clave,
                cuit_emisor=cuit_emisor_normalizado,
                punto_venta=punto_venta_normalizado,
                tipo_comprobante=tipo_comprobante,
                condicion_iva_receptor_id=condicion_iva_receptor_id,
                concepto=1,
                tipo_documento=tipo_documento,
                documento_receptor=documento_receptor,
                importe_total=total_factura_fiscal,
                importe_neto=neto_factura,
                importe_iva=importe_iva_factura,
                importe_exento=importe_exento_factura,
                fecha_comprobante=fecha_comprobante,
                carpeta_trabajo=carpeta_facturas,
                importe_tot_conc=importe_tot_conc,
                importe_tributos=importe_tributos,
                alicuotas_iva=alicuotas_iva,
            )
            if not emision.get("ok"):
                messagebox.showerror(
                    "Emitir factura",
                    self._mensaje_errores_emision(emision),
                    parent=self,
                )
                return

            numero_emitido = int(emision.get("numero_comprobante") or 0)
            consulta = HomologacionService.consultar_comprobante_emitido(
                ruta_certificado=ruta_certificado,
                ruta_clave=ruta_clave,
                cuit_emisor=cuit_emisor_normalizado,
                punto_venta=punto_venta_normalizado,
                tipo_comprobante=tipo_comprobante,
                numero_comprobante=numero_emitido,
                carpeta_trabajo=carpeta_facturas,
                token=emision.get("token"),
                sign=emision.get("sign"),
            )
            if not consulta.get("ok"):
                messagebox.showerror(
                    "Emitir factura",
                    self._mensaje_errores_emision(consulta),
                    parent=self,
                )
                return

            numero_comprobante = int(consulta.get("numero_comprobante") or numero_emitido)
            punto_venta_num = int(consulta.get("punto_venta") or punto_venta_normalizado)
            numero_factura = self._formatear_codigo_factura(punto_venta_num, numero_comprobante)
            cae = str(consulta.get("cae") or emision.get("cae") or "")
            vencimiento_cae = str(consulta.get("vencimiento_cae") or emision.get("vencimiento_cae") or "")

            factura_id = FacturaArcaService.guardar(
                FacturaArca(
                    cliente_id=cliente[0],
                    emisor_id=emisor_facturacion_id,
                    resumen_id=resumen.id,
                    fecha=date.today().isoformat(),
                    punto_venta=str(punto_venta_num),
                    tipo_comprobante=tipo_factura_normalizado,
                    importe_total=total_factura_fiscal,
                    estado="Facturada manualmente",
                    numero_factura=numero_factura,
                    cae=cae,
                    vencimiento_cae=vencimiento_cae,
                    observaciones=(
                        f"Emitida desde Resúmenes ({modalidad}). Emisor habitual: {emisor_habitual}. "
                        f"Fiscal: neto={neto_factura:.2f}; iva_alicuota={alicuota_iva:.2f}%; "
                        f"iva_importe={importe_iva_factura:.2f}; total={total_factura_fiscal:.2f}"
                    ),
                    fecha_creacion=datetime.now().isoformat(timespec="seconds"),
                )
            )
            print(f"factura_id_registrado: {factura_id}")
            print(f"comprobante_registrado: {numero_factura}")

            ResumenService.marcar_facturado(
                resumen.id,
                numero_factura=numero_factura,
                cae=cae,
                vencimiento_cae=vencimiento_cae,
            )

            codigo_factura = self._formatear_codigo_factura(punto_venta_num, numero_comprobante)
            ruta_sugerida_pdf = str(Path(carpeta_facturas) / nombre_factura_pdf(cliente[0], tipo_factura, codigo_factura))

            periodo_desde, periodo_hasta = self._obtener_periodo_facturado(resumen_actual)

            datos_emisor = {
                "razon_social": str(emisor_fiscal[1] if len(emisor_fiscal) > 1 else "" or ""),
                "nombre_fantasia": str(emisor_fiscal[2] if len(emisor_fiscal) > 2 else "" or ""),
                "cuit": cuit_emisor_normalizado,
                "condicion_iva": str(emisor_fiscal[4] if len(emisor_fiscal) > 4 else "" or ""),
                "domicilio": str(emisor_fiscal[10] if len(emisor_fiscal) > 10 else "" or ""),
                "punto_venta": punto_venta_num,
            }

            cuit_o_doc = documento_normalizado or "0"
            datos_receptor = {
                "razon_social": str(cliente[2] if len(cliente) > 2 else "" or ""),
                "cuit": cuit_o_doc,
                "documento": cuit_o_doc,
                "condicion_iva": condicion_iva,
                "domicilio": self._combinar_domicilio_cliente(cliente),
            }

            datos_comprobante = {
                "tipo": tipo_factura_normalizado,
                "numero": numero_comprobante,
                "fecha": str(consulta.get("fecha_comprobante") or fecha_comprobante or ""),
                "concepto": "1 - Productos",
                "periodo_servicio_desde": periodo_desde,
                "periodo_servicio_hasta": periodo_hasta,
                "vencimiento_pago": self._a_fecha_arca_yyyymmdd(resumen_actual.fecha_vencimiento),
                "importe_neto": neto_factura,
                "importe_iva": importe_iva_factura,
                "alicuota_iva": alicuota_iva,
                "importe_total": total_factura_fiscal,
                "items": items_factura,
                "moneda": str(consulta.get("moneda") or "PES"),
                "cae": cae,
                "vencimiento_cae": vencimiento_cae,
                "ambiente": str(emisor_fiscal[9] if len(emisor_fiscal) > 9 else "Homologación"),
                "punto_venta": punto_venta_num,
            }
            print(f"importe_enviado_pdf: {total_factura_fiscal}")

            pdf = PDFFiscalService.generar_factura_c(
                ruta_destino=ruta_sugerida_pdf,
                datos_emisor=datos_emisor,
                datos_receptor=datos_receptor,
                datos_comprobante=datos_comprobante,
            )
            if not pdf.get("ok"):
                errores_pdf = "\n".join(pdf.get("errores") or ["No se pudo generar el PDF fiscal."])
                messagebox.showwarning(
                    "Emitir factura",
                    "Factura autorizada correctamente, pero falló la generación del PDF fiscal.\n\n"
                    f"{errores_pdf}",
                    parent=self,
                )
                self.cargar_resumenes()
                return

            ruta_pdf = str(pdf.get("ruta_pdf") or "").strip()
            if ruta_pdf:
                try:
                    os.startfile(ruta_pdf)
                except OSError:
                    pass

            self.cargar_resumenes()

            messagebox.showinfo(
                "Emitir factura",
                "Factura autorizada correctamente.\n"
                f"Comprobante: {tipo_factura_normalizado[-1]} {codigo_factura}\n"
                f"CAE: {cae or '-'}\n"
                f"Vencimiento CAE: {vencimiento_cae or '-'}",
                parent=self,
            )
        except Exception as error:
            messagebox.showerror(
                "Emitir factura",
                f"Error inesperado durante la emisión:\n{error}",
                parent=self,
            )

    def _armar_items_factura_desde_resumen(self, resumen):
        items = []
        for concepto in list(getattr(resumen, "conceptos", []) or []):
            cantidad = float(getattr(concepto, "cantidad", 0) or 0)
            precio_unitario = float(getattr(concepto, "importe", 0) or 0)
            importe = float(getattr(concepto, "total", 0) or 0)
            if abs(importe) <= 0.0 and cantidad > 0:
                importe = cantidad * precio_unitario
            texto_concepto = str(getattr(concepto, "concepto", "") or "").strip()
            texto_descripcion = str(getattr(concepto, "descripcion", "") or "").strip()
            descripcion = texto_concepto
            if texto_descripcion:
                descripcion = f"{texto_concepto} - {texto_descripcion}" if texto_concepto else texto_descripcion

            items.append(
                {
                    "concepto": texto_concepto,
                    "descripcion": descripcion or "(Sin descripción)",
                    "cantidad": cantidad,
                    "precio_unitario": precio_unitario,
                    "importe": float(round(importe, 2)),
                }
            )
        return items

    def _sumar_importes_items(self, items):
        return float(round(sum(float(item.get("importe", 0) or 0) for item in list(items or [])), 2))

    def _obtener_periodo_facturado(self, resumen):
        fechas_inicio = []
        fechas_fin = []
        for concepto in list(getattr(resumen, "conceptos", []) or []):
            inicio = self._a_fecha_arca_yyyymmdd(getattr(concepto, "fecha_inicio", ""))
            fin = self._a_fecha_arca_yyyymmdd(getattr(concepto, "fecha_fin", ""))
            if len(inicio) == 8 and inicio.isdigit():
                fechas_inicio.append(inicio)
            if len(fin) == 8 and fin.isdigit():
                fechas_fin.append(fin)

        if not fechas_inicio and not fechas_fin:
            return "", ""

        periodo_desde = min(fechas_inicio) if fechas_inicio else ""
        periodo_hasta = max(fechas_fin) if fechas_fin else ""
        return periodo_desde, periodo_hasta

    def _mostrar_vista_previa_resumen_para_factura(self, resumen):
        resumen_actual = ResumenService.obtener(resumen.id)
        if not resumen_actual:
            messagebox.showerror(
                "Vista previa",
                "No se pudo obtener el resumen recién guardado para previsualizar.",
                parent=self,
            )
            return "cancelar"

        items = self._armar_items_factura_desde_resumen(resumen_actual)
        total_items = self._sumar_importes_items(items)
        total_resumen = float(getattr(resumen_actual, "total", 0) or 0)

        ventana = ctk.CTkToplevel(self)
        ventana.title("Revisar resumen antes de emitir")
        ventana.configure(fg_color="white")
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()

        # Tamaño adaptativo para mantener visible el pie con botones en pantallas bajas.
        ventana.update_idletasks()
        pantalla_ancho = int(ventana.winfo_screenwidth() or 1366)
        pantalla_alto = int(ventana.winfo_screenheight() or 768)
        ancho_objetivo = min(1000, max(860, pantalla_ancho - 80))
        alto_objetivo = min(680, max(500, pantalla_alto - 120))
        pos_x = max(0, (pantalla_ancho - ancho_objetivo) // 2)
        pos_y = max(0, (pantalla_alto - alto_objetivo) // 2)
        ventana.geometry(f"{ancho_objetivo}x{alto_objetivo}+{pos_x}+{pos_y}")
        ventana.minsize(780, 460)
        ventana.grid_rowconfigure(1, weight=1)
        ventana.grid_columnconfigure(0, weight=1)

        accion = ctk.StringVar(value="cancelar")

        encabezado = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 8))
        ctk.CTkLabel(
            encabezado,
            text=f"Vista previa del resumen #{int(resumen_actual.numero or 0):06d}",
            font=("Arial", 22, "bold"),
            text_color="#C00000",
        ).pack(anchor="w")

        tabla_frame = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = ("concepto", "descripcion", "cantidad", "unitario", "importe")
        tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=14)
        tabla.heading("concepto", text="Concepto")
        tabla.heading("descripcion", text="Descripción")
        tabla.heading("cantidad", text="Cantidad")
        tabla.heading("unitario", text="Precio unitario")
        tabla.heading("importe", text="Importe")
        tabla.column("concepto", width=170, anchor="w", stretch=False)
        tabla.column("descripcion", width=410, anchor="w", stretch=True)
        tabla.column("cantidad", width=95, anchor="e", stretch=False)
        tabla.column("unitario", width=145, anchor="e", stretch=False)
        tabla.column("importe", width=145, anchor="e", stretch=False)

        for item in items:
            tabla.insert(
                "",
                "end",
                values=(
                    item["concepto"] or "-",
                    item["descripcion"],
                    f"{float(item['cantidad']):,.2f}",
                    self.formatear_moneda(item["precio_unitario"]),
                    self.formatear_moneda(item["importe"]),
                ),
            )

        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        pie = ctk.CTkFrame(ventana, fg_color="#F7F7F7", corner_radius=8)
        pie.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        pie.grid_columnconfigure(0, weight=1)

        resumen_totales = ctk.CTkFrame(pie, fg_color="#F7F7F7", corner_radius=0)
        resumen_totales.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 10))
        ctk.CTkLabel(
            resumen_totales,
            text=f"Cantidad de ítems: {len(items)}",
            font=("Arial", 14, "bold"),
            text_color="#222222",
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            resumen_totales,
            text=f"Suma de ítems: {self.formatear_moneda(total_items)}",
            font=("Arial", 13),
            text_color="#222222",
        ).pack(anchor="w", pady=2)
        ctk.CTkLabel(
            resumen_totales,
            text=f"Total del resumen: {self.formatear_moneda(total_resumen)}",
            font=("Arial", 13),
            text_color="#222222",
        ).pack(anchor="w", pady=2)

        diferencia = round(total_items - total_resumen, 2)
        if abs(diferencia) > 0.01:
            ctk.CTkLabel(
                resumen_totales,
                text=(
                    "Advertencia: la suma de ítems no coincide con el total del resumen. "
                    f"Diferencia: {self.formatear_moneda(diferencia)}"
                ),
                font=("Arial", 12, "bold"),
                text_color="#C00000",
            ).pack(anchor="w", pady=(2, 0))
        else:
            ctk.CTkLabel(
                resumen_totales,
                text="Validación previa OK: suma de ítems = total del resumen.",
                font=("Arial", 12, "bold"),
                text_color="#1E7A2E",
            ).pack(anchor="w", pady=(2, 0))

        botones = ctk.CTkFrame(pie, fg_color="#F7F7F7", corner_radius=0)
        botones.grid(row=0, column=1, sticky="e", padx=(10, 14), pady=(10, 10))

        def _cerrar(valor):
            accion.set(valor)
            ventana.destroy()

        ctk.CTkButton(
            botones,
            text="Emitir factura",
            fg_color="#C00000",
            hover_color="#990000",
            width=150,
            command=lambda: _cerrar("emitir"),
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            botones,
            text="Solo guardar resumen",
            fg_color="#444444",
            hover_color="#222222",
            width=170,
            command=lambda: _cerrar("guardar"),
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            botones,
            text="Cancelar",
            fg_color="#777777",
            hover_color="#555555",
            width=120,
            command=lambda: _cerrar("cancelar"),
        ).pack(side="right")

        ventana.protocol("WM_DELETE_WINDOW", lambda: _cerrar("cancelar"))
        self.wait_window(ventana)
        return accion.get()

    def _a_fecha_arca_yyyymmdd(self, valor):
        texto = str(valor or "").strip()
        if len(texto) == 8 and texto.isdigit():
            return texto
        if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
            return texto.replace("-", "")
        return texto

    def _combinar_domicilio_cliente(self, cliente_fila):
        direccion = str(cliente_fila[5] if len(cliente_fila) > 5 else "" or "").strip()
        localidad = str(cliente_fila[6] if len(cliente_fila) > 6 else "" or "").strip()
        if direccion and localidad:
            return f"{direccion} - {localidad}"
        return direccion or localidad

    def _buscar_emisor_fiscal_por_etiqueta(self, etiqueta):
        texto_original = str(etiqueta or "").strip()
        if not texto_original:
            return None

        if texto_original.isdigit():
            return EmisorFiscalService.obtener(int(texto_original))

        if texto_original.upper().startswith("EMISOR:"):
            try:
                return EmisorFiscalService.obtener(int(texto_original.split(":", 1)[1]))
            except (TypeError, ValueError):
                return None

        texto = self._normalizar_etiqueta_emisor(texto_original)
        for emisor in EmisorFiscalService.listar():
            visible = self._normalizar_etiqueta_emisor(
                EmisorFiscalService.etiqueta_visible(emisor)
            )
            if visible == texto:
                return emisor
        return None

    def _normalizar_etiqueta_emisor(self, valor):
        texto = str(valor or "").strip().lower()
        return "".join(caracter for caracter in texto if caracter.isalnum())

    def _resolver_emisor_facturacion_id(self, cliente, emisor_fiscal):
        emisor_fiscal_id = emisor_fiscal[0] if emisor_fiscal and len(emisor_fiscal) > 0 else None
        cuit_fiscal = self._normalizar_cuit(emisor_fiscal[3] if len(emisor_fiscal) > 3 else "")
        nombre_fiscal = EmisorFiscalService.etiqueta_visible(emisor_fiscal)
        nombre_fiscal_normalizado = self._normalizar_etiqueta_emisor(nombre_fiscal)

        emisores_internos = EmisorService.listar(False)
        resumen_internos = [
            {
                "id": fila[0],
                "alias": str(fila[1] or "").strip(),
                "titular": str(fila[2] or "").strip(),
                "nombre": str(fila[3] or "").strip(),
                "cuit": str(fila[4] or "").strip(),
            }
            for fila in emisores_internos
        ]

        print("DIAGNOSTICO RESOLVER EMISOR INTERNO")
        print(f"emisor_fiscal_id: {emisor_fiscal_id}")
        print(f"cuit_emisor_fiscal: {cuit_fiscal or '-'}")
        print(f"nombre_emisor_fiscal: {nombre_fiscal or '-'}")
        print(f"emisores_internos_encontrados: {resumen_internos}")

        # 1) Vínculo directo por ID
        if emisor_fiscal_id and EmisorService.obtener(emisor_fiscal_id):
            print("criterio_vinculacion: id_directo")
            print(f"emisor_facturacion_id_final: {emisor_fiscal_id}")
            return emisor_fiscal_id, "id_directo"

        # 2) Vínculo por CUIT exacto
        if cuit_fiscal:
            for emisor in emisores_internos:
                cuit_interno = self._normalizar_cuit(emisor[4] if len(emisor) > 4 else "")
                if cuit_interno and cuit_interno == cuit_fiscal:
                    print("criterio_vinculacion: cuit")
                    print(f"emisor_facturacion_id_final: {emisor[0]}")
                    return emisor[0], "cuit"

        # 3) Vínculo por código único (alias exacto normalizado)
        if nombre_fiscal_normalizado:
            for emisor in emisores_internos:
                alias_normalizado = self._normalizar_etiqueta_emisor(emisor[1] if len(emisor) > 1 else "")
                if alias_normalizado and alias_normalizado == nombre_fiscal_normalizado:
                    print("criterio_vinculacion: alias")
                    print(f"emisor_facturacion_id_final: {emisor[0]}")
                    return emisor[0], "alias"

        # 4) Último recurso: nombre exacto normalizado
        if nombre_fiscal_normalizado:
            for emisor in emisores_internos:
                nombre_normalizado = self._normalizar_etiqueta_emisor(emisor[3] if len(emisor) > 3 else "")
                titular_normalizado = self._normalizar_etiqueta_emisor(emisor[2] if len(emisor) > 2 else "")
                if nombre_normalizado == nombre_fiscal_normalizado or titular_normalizado == nombre_fiscal_normalizado:
                    print("criterio_vinculacion: nombre_exacto_normalizado")
                    print(f"emisor_facturacion_id_final: {emisor[0]}")
                    return emisor[0], "nombre_exacto_normalizado"

        print("criterio_vinculacion: sin_vinculo")
        print("emisor_facturacion_id_final: None")
        return None, "sin_vinculo"

    def _mensaje_errores_emision(self, respuesta):
        errores = []
        for clave in ("errores", "errores_arca", "observaciones"):
            for item in list(respuesta.get(clave) or []):
                texto = str(item).strip()
                if texto:
                    errores.append(texto)
        faultcode = str(respuesta.get("faultcode") or "").strip()
        faultstring = str(respuesta.get("faultstring") or "").strip()
        if faultcode:
            errores.append(f"faultcode: {faultcode}")
        if faultstring:
            errores.append(f"faultstring: {faultstring}")
        if not errores:
            return "No se pudo completar la emisión con ARCA."
        return "No se pudo completar la emisión:\n\n- " + "\n- ".join(dict.fromkeys(errores))

    def _normalizar_cuit(self, cuit):
        texto = str(cuit or "").strip()
        digitos = "".join(char for char in texto if char.isdigit())
        if len(digitos) != 11:
            return None
        return digitos

    def _normalizar_punto_venta(self, punto_venta):
        try:
            valor = int(punto_venta or 0)
        except (TypeError, ValueError):
            return None
        return valor if valor > 0 else None

    def _formatear_codigo_factura(self, punto_venta, numero):
        try:
            pv = int(punto_venta)
        except (TypeError, ValueError):
            pv = 0
        try:
            nro = int(numero)
        except (TypeError, ValueError):
            nro = 0
        return f"{pv:05d}-{nro:08d}"

    def abrir_resumenes_pendientes(self):
        pendientes = ResumenService.listar_pendientes()
        if not pendientes:
            messagebox.showinfo(
                "Resúmenes pendientes",
                "No hay resúmenes pendientes para generar.",
                parent=self,
            )
            return

        ventana = ctk.CTkToplevel(self)
        self.ventana_pendientes = ventana
        ventana.title("Generar resúmenes pendientes")
        ventana.geometry("950x560")
        ventana.minsize(820, 500)
        ventana.configure(fg_color="white")
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()
        ventana.grid_rowconfigure(2, weight=1)
        ventana.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            ventana,
            text="RESÚMENES PENDIENTES",
            font=("Arial", 22, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        seleccion = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        seleccion.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        ctk.CTkButton(
            seleccion,
            text="Seleccionar todos",
            width=135,
            height=36,
            fg_color="#444444",
            hover_color="#222222",
            command=lambda: self.tabla_pendientes.selection_set(
                self.tabla_pendientes.get_children()
            ),
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            seleccion,
            text="Deseleccionar todos",
            width=145,
            height=36,
            fg_color="#666666",
            hover_color="#444444",
            command=lambda: self.tabla_pendientes.selection_remove(
                self.tabla_pendientes.get_children()
            ),
        ).grid(row=0, column=1)

        tabla_frame = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=2, column=0, sticky="nsew", padx=20)
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        columnas = ("cliente", "servicios", "inicio", "fin", "total")
        self.tabla_pendientes = ttk.Treeview(
            tabla_frame,
            columns=columnas,
            show="headings",
            selectmode="extended",
            height=14,
        )
        encabezados = {
            "cliente": ("Cliente", 220),
            "servicios": ("Servicios incluidos", 330),
            "inicio": ("Fecha inicio", 105),
            "fin": ("Fecha fin", 105),
            "total": ("Total", 115),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla_pendientes.heading(columna, text=texto)
            self.tabla_pendientes.column(
                columna,
                width=ancho,
                anchor="w",
                stretch=columna in ("cliente", "servicios"),
            )
        for pendiente in pendientes:
            conceptos = ", ".join(
                servicio["concepto"] for servicio in pendiente["servicios"]
            )
            self.tabla_pendientes.insert(
                "",
                "end",
                iid=str(pendiente["cliente_id"]),
                values=(
                    pendiente["cliente"],
                    conceptos,
                    self.formatear_fecha(pendiente["fecha_inicio"]),
                    self.formatear_fecha(pendiente["fecha_fin"]),
                    self.formatear_moneda(pendiente["total"]),
                ),
            )
        scroll = ttk.Scrollbar(
            tabla_frame,
            orient="vertical",
            command=self.tabla_pendientes.yview,
        )
        self.tabla_pendientes.configure(yscrollcommand=scroll.set)
        self.tabla_pendientes.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tabla_pendientes.selection_set(self.tabla_pendientes.get_children())

        botones = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        botones.grid(row=3, column=0, sticky="e", padx=20, pady=18)
        self.boton_confirmar_pendientes = ctk.CTkButton(
            botones,
            text="Generar seleccionados",
            width=170,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.generar_pendientes_seleccionados,
        )
        self.boton_confirmar_pendientes.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            botones,
            text="Cancelar",
            width=105,
            height=38,
            fg_color="#666666",
            hover_color="#444444",
            command=ventana.destroy,
        ).grid(row=0, column=1)

    def generar_pendientes_seleccionados(self):
        seleccion = self.tabla_pendientes.selection()
        if not seleccion:
            messagebox.showwarning(
                "Resúmenes pendientes",
                "Seleccione al menos un cliente.",
                parent=self.ventana_pendientes,
            )
            return

        generados = 0
        omitidos = 0
        errores = []
        carpeta = PDF_DIR / "resumenes" / date.today().strftime("%Y-%m")
        for item in seleccion:
            cliente_id = int(item)
            try:
                resumen = ResumenService.generar_pendiente_cliente(cliente_id)
                if resumen is None:
                    omitidos += 1
                    continue
                ruta = carpeta / f"resumen_{resumen.numero:06d}.pdf"
                ResumenPDF.generar(resumen.id, ruta)
                generados += 1
            except Exception as error:
                if "resumen" in locals() and resumen is not None:
                    ResumenService.eliminar_generacion(resumen.id)
                errores.append(str(error))
            finally:
                resumen = None

        self.ventana_pendientes.destroy()
        self.cargar_resumenes()
        messagebox.showinfo(
            "Resultado de generación",
            f"Generados: {generados}\n"
            f"Omitidos: {omitidos}\n"
            f"Errores: {len(errores)}",
            parent=self,
        )

    def abrir_pdf_seleccionado(self):
        resumen_id = self._obtener_resumen_id_seleccionado(
            titulo="Atencion",
            mensaje="Seleccione un resumen para abrir.",
        )
        if resumen_id is None:
            return

        resumen = ResumenService.obtener(resumen_id)
        if resumen is None:
            messagebox.showwarning("Atencion", "No se encontró el resumen seleccionado.")
            return

        try:
            ruta_pdf = self._resolver_pdf_resumen(resumen)
            os.startfile(str(ruta_pdf))
        except (OSError, ValueError) as error:
            messagebox.showerror("Error", f"No se pudo abrir el PDF: {error}")

    def _obtener_resumen_id_seleccionado(self, titulo, mensaje):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning(titulo, mensaje, parent=self)
            return None

        valores = self.tabla.item(seleccion[0], "values")
        try:
            return int(valores[0])
        except (TypeError, ValueError, IndexError):
            messagebox.showwarning(titulo, "No se pudo identificar el resumen seleccionado.", parent=self)
            return None

    def _resolver_pdf_resumen(self, resumen):
        if resumen is None:
            raise ValueError("No se encontró el resumen seleccionado.")

        ruta_guardada = str(getattr(resumen, "pdf_path", "") or "").strip()
        ruta_pdf = self._normalizar_ruta_pdf(ruta_guardada) if ruta_guardada else None

        if ruta_pdf is None or not ruta_pdf.is_file():
            ruta_regenerada = ResumenPDF.generar(resumen.id)
            self.cargar_resumenes()
            ruta_pdf = self._normalizar_ruta_pdf(ruta_regenerada)

        if ruta_pdf is None or not ruta_pdf.is_file():
            raise ValueError("No se encontró el archivo PDF del resumen.")

        return ruta_pdf

    @staticmethod
    def _normalizar_ruta_pdf(ruta_pdf):
        ruta = Path(str(ruta_pdf or "").strip())
        if not str(ruta):
            return None
        if not ruta.is_absolute():
            ruta = PDF_DIR.parent / ruta
        return ruta.resolve()

    @staticmethod
    def _obtener_contacto_cliente_para_whatsapp(cliente):
        nombre = str(cliente[2] if len(cliente) > 2 else "" or "").strip()
        nombre_comercial = str(cliente[3] if len(cliente) > 3 else "" or "").strip()
        nombre_cliente = nombre or nombre_comercial or "Cliente"
        whatsapp = str(cliente[8] if len(cliente) > 8 else "" or "").strip()
        telefono = str(cliente[7] if len(cliente) > 7 else "" or "").strip()

        if whatsapp:
            return {"nombre": nombre_cliente, "numero_destino": whatsapp, "fuente": "whatsapp"}
        if telefono:
            return {"nombre": nombre_cliente, "numero_destino": telefono, "fuente": "telefono"}
        return {"nombre": nombre_cliente, "numero_destino": "", "fuente": ""}

    def _crear_mensaje_whatsapp_resumen(self, nombre_cliente, numero_resumen, importe, vencimiento):
        nombre = str(nombre_cliente or "Cliente").strip()
        importe_texto = self.formatear_moneda(importe)
        vencimiento_texto = self.formatear_fecha(vencimiento)
        return (
            f"Hola {nombre}.\n\n"
            f"Te enviamos el Resumen N.º {numero_resumen} correspondiente.\n\n"
            f"Importe: {importe_texto}\n"
            f"Vencimiento: {vencimiento_texto}\n\n"
            "Muchas gracias.\n\n"
            "FM Master 98.3"
        )

    def enviar_whatsapp_seleccionado(self):
        resumen_id = self._obtener_resumen_id_seleccionado(
            titulo="Atencion",
            mensaje="Seleccione un resumen para enviar.",
        )
        if resumen_id is None:
            return

        resumen = ResumenService.obtener(resumen_id)
        if resumen is None:
            messagebox.showwarning("WhatsApp", "No se encontró el resumen seleccionado.", parent=self)
            return

        cliente = ClienteService.obtener(resumen.cliente_id)
        if cliente is None:
            messagebox.showwarning("WhatsApp", "No se encontró el cliente asociado al resumen.", parent=self)
            return

        contacto = self._obtener_contacto_cliente_para_whatsapp(cliente)
        if not contacto["numero_destino"]:
            messagebox.showwarning(
                "WhatsApp",
                "El cliente no tiene WhatsApp ni teléfono cargado.",
                parent=self,
            )
            return

        try:
            numero_normalizado = WhatsAppService.normalizar_numero(contacto["numero_destino"])
        except ValueError as error:
            messagebox.showwarning("WhatsApp", str(error), parent=self)
            return

        try:
            ruta_pdf = self._resolver_pdf_resumen(resumen)
        except (OSError, ValueError) as error:
            messagebox.showerror("WhatsApp", str(error), parent=self)
            return

        numero_resumen = f"{int(resumen.numero or 0):06d}" if resumen.numero else "-"
        mensaje = self._crear_mensaje_whatsapp_resumen(
            nombre_cliente=contacto["nombre"],
            numero_resumen=numero_resumen,
            importe=float(resumen.total or 0),
            vencimiento=str(resumen.fecha_vencimiento or ""),
        )

        try:
            resultado = WhatsAppService.abrir_whatsapp_factura(
                numero=numero_normalizado,
                mensaje=mensaje,
                pdf_path=str(ruta_pdf),
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("WhatsApp", str(error), parent=self)
            return

        origen = "WhatsApp" if contacto["fuente"] == "whatsapp" else "Teléfono"
        advertencia_explorador = str(resultado.get("explorador_advertencia") or "").strip()
        texto_final = (
            "Se abrió WhatsApp Desktop con el mensaje preparado.\n"
            f"Número utilizado: {origen}.\n"
            "Adjuntá manualmente el PDF seleccionado en el Explorador."
        )
        if advertencia_explorador:
            texto_final += f"\n\n{advertencia_explorador}"

        messagebox.showinfo(
            "WhatsApp",
            texto_final,
            parent=self,
        )

    def mostrar_modal_resumen_generado(self, ruta_pdf):
        modal = ctk.CTkToplevel(self)
        modal.title("Resumen generado")
        modal.geometry("440x220")
        modal.resizable(False, False)
        modal.transient(self.winfo_toplevel())
        modal.grab_set()
        modal.configure(fg_color="white")

        contenedor = ctk.CTkFrame(modal, fg_color="white", corner_radius=0)
        contenedor.pack(fill="both", expand=True, padx=20, pady=20)
        contenedor.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            contenedor,
            text="Resumen generado correctamente",
            font=("Arial", 18, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", pady=(0, 18))

        ctk.CTkButton(
            contenedor,
            text="Ver PDF",
            height=36,
            fg_color="#C00000",
            hover_color="#990000",
            command=lambda: self.abrir_pdf_generado(ruta_pdf),
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkButton(
            contenedor,
            text="Enviar por WhatsApp",
            height=36,
            fg_color="#333333",
            hover_color="#111111",
            command=self.mostrar_aviso_whatsapp_pendiente,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkButton(
            contenedor,
            text="Cerrar",
            height=36,
            fg_color="#666666",
            hover_color="#444444",
            command=modal.destroy,
        ).grid(row=3, column=0, sticky="ew")

    def abrir_pdf_generado(self, ruta_pdf):
        try:
            os.startfile(str(Path(ruta_pdf).resolve()))
        except (OSError, ValueError) as error:
            messagebox.showerror("Error", f"No se pudo abrir el PDF: {error}", parent=self)

    def mostrar_aviso_whatsapp_pendiente(self):
        messagebox.showinfo(
            "WhatsApp",
            "La integración de envío por WhatsApp se agregará en el próximo paso.",
            parent=self,
        )

    @staticmethod
    def formatear_fecha(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""

    @staticmethod
    def formatear_moneda(valor):
        numero = f"{float(valor or 0):,.2f}"
        return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _tag_estado(estado):
        estado_limpio = (estado or "").strip().lower()
        if estado_limpio == "pendiente":
            return "estado_pendiente"
        if estado_limpio == "vencido":
            return "estado_vencido"
        if estado_limpio == "pagado":
            return "estado_pagado"
        if estado_limpio == "facturado":
            return "estado_facturado"
        return "estado_default"

    @staticmethod
    def _estado_resumen_para_grilla(estado_cobro, estado_facturacion):
        estado_cobro_txt = str(estado_cobro or "Pendiente").strip() or "Pendiente"
        estado_fact_txt = str(estado_facturacion or "Pendiente").strip() or "Pendiente"
        if estado_fact_txt.lower() == "facturado":
            return f"Facturado | Cobro: {estado_cobro_txt}"
        return estado_cobro_txt
