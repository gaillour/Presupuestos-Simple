from dataclasses import dataclass, field
from typing import List
from datetime import datetime
import unicodedata
import json
import os
import streamlit as st
from supabase import create_client, Client
from fpdf import FPDF

CONFIG_EXTRA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".config_extra.json")

def leer_config_extra() -> dict:
    if os.path.exists(CONFIG_EXTRA_FILE):
        try:
            with open(CONFIG_EXTRA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_config_extra(datos: dict):
    try:
        actual = leer_config_extra()
        actual.update(datos)
        with open(CONFIG_EXTRA_FILE, "w", encoding="utf-8") as f:
            json.dump(actual, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8').lower().strip()


def seguro_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

# --- CLASES DE DATOS (MODELOS) ---

@dataclass
class Config:
    costo_fijo_base: float = 6000.0
    multiplicador_default: float = 2.0
    precio_metro_dtf: float = 0.0
    precio_metro_sublimacion: float = 0.0
    precio_unidad_serigrafia: float = 0.0
    precio_unidad_bordado: float = 0.0
    descripcion_pdf: str = "Presupuesto válido por 15 días corridos a partir de la fecha de emisión. Precios sujetos a variación de insumos."

    def __init__(
        self,
        costo_fijo_base: float = 6000.0,
        multiplicador_default: float = 2.0,
        precio_metro_dtf: float = 0.0,
        precio_metro_sublimacion: float = 0.0,
        precio_unidad_serigrafia: float = 0.0,
        precio_unidad_bordado: float = 0.0,
        descripcion_pdf: str = "",
        **kwargs
    ):
        self.costo_fijo_base = seguro_float(costo_fijo_base, 6000.0)
        self.multiplicador_default = seguro_float(multiplicador_default, 2.0)
        self.precio_metro_dtf = seguro_float(precio_metro_dtf, 0.0)
        self.precio_metro_sublimacion = seguro_float(precio_metro_sublimacion, 0.0)
        self.precio_unidad_serigrafia = seguro_float(precio_unidad_serigrafia, 0.0)
        self.precio_unidad_bordado = seguro_float(precio_unidad_bordado, 0.0)
        self.descripcion_pdf = str(descripcion_pdf or "Presupuesto válido por 15 días corridos a partir de la fecha de emisión. Precios sujetos a variación de insumos.")

@dataclass
class Tela:
    id: int
    nombre: str
    precio_kilo: float
    rendimiento: float
    descripcion: str = ""

    @property
    def precio_metro(self) -> float:
        # Evitamos dividir por cero si alguna vez se carga mal un dato
        if self.rendimiento == 0: return 0.0
        return self.precio_kilo / self.rendimiento

@dataclass
class Producto:
    id: int
    nombre: str
    tela: Tela
    consumo_metros: float
    costo_confeccion: float
    tipo_estampado: str = "Ninguno"
    consumo_estampado: float = 0.0
    nombre_avio: str = ""
    costo_avio: float = 0.0

    @property
    def costo_tela(self) -> float:
        return self.tela.precio_metro * self.consumo_metros

    @property
    def costo_base(self) -> float:
        # Tela + Confección + Avíos
        return self.costo_tela + self.costo_confeccion + self.costo_avio

    def costo_estampado(self, config: Config) -> float:
        if not self.tipo_estampado or self.tipo_estampado == "Ninguno" or self.consumo_estampado <= 0:
            return 0.0
        tipo = normalizar_texto(self.tipo_estampado)
        if tipo == "dtf":
            return self.consumo_estampado * config.precio_metro_dtf
        elif tipo == "sublimacion":
            return self.consumo_estampado * config.precio_metro_sublimacion
        elif tipo == "serigrafia":
            return self.consumo_estampado * config.precio_unidad_serigrafia
        elif tipo == "bordado":
            return self.consumo_estampado * config.precio_unidad_bordado
        return 0.0

    def costo_produccion(self, config: Config) -> float:
        # Costo total unitario de producción: Tela + Confección + Avíos + Estampado
        return self.costo_base + self.costo_estampado(config)

    def precio_venta(self, config: Config) -> float:
        # Precio de venta en catálogo con multiplicador y costo fijo
        return (self.costo_produccion(config) * config.multiplicador_default) + config.costo_fijo_base


@dataclass
class ItemPresupuesto:
    producto: Producto
    cantidad: int
    detalle_estampado: str = ""
    costo_estampado: float = 0.0
    
    @property
    def costo_base_unitario(self) -> float:
        # Suma costos puros (Tela + Confección + Avíos + Estampado)
        return self.producto.costo_base + self.costo_estampado

@dataclass
class Presupuesto:
    cliente: str
    items: List[ItemPresupuesto] = field(default_factory=list)
    config: Config = field(default_factory=Config)
    multiplicador_usado: float = None
    costo_fijo_usado: float = None
    
    def __post_init__(self):
        if self.multiplicador_usado is None:
            self.multiplicador_usado = self.config.multiplicador_default
        if self.costo_fijo_usado is None:
            self.costo_fijo_usado = self.config.costo_fijo_base

    # LA NUEVA FÓRMULA MATEMÁTICA POR PRENDA
    def precio_unitario_final(self, item: ItemPresupuesto) -> float:
        return (item.costo_base_unitario * self.multiplicador_usado) + self.costo_fijo_usado

    def subtotal_final(self, item: ItemPresupuesto) -> float:
        return self.precio_unitario_final(item) * item.cantidad

    @property
    def total_final(self) -> float:
        return sum(self.subtotal_final(item) for item in self.items)

# --- MANEJADOR DE BASE DE DATOS ---

class Database:
    def __init__(self):
        url: str = st.secrets["SUPABASE_URL"]
        key: str = st.secrets["SUPABASE_KEY"]
        self.client: Client = create_client(url, key)

    def obtener_telas(self) -> List[Tela]:
        res = self.client.table("telas").select("*").execute()
        telas = []
        for t in res.data:
            telas.append(Tela(
                id=t["id"],
                nombre=t["nombre"],
                precio_kilo=t["precio_kilo"],
                rendimiento=t["rendimiento"],
                descripcion=t.get("descripcion") or ""
            ))
        return telas

    def obtener_productos(self) -> List[Producto]:
        res = self.client.table("productos").select(
            "*, telas(*)"
        ).execute()
        
        productos = []
        for p in res.data:
            tela_data = p["telas"]
            tela_obj = Tela(
                id=tela_data["id"],
                nombre=tela_data["nombre"],
                precio_kilo=tela_data["precio_kilo"],
                rendimiento=tela_data["rendimiento"],
                descripcion=tela_data.get("descripcion") or ""
            )
            
            costo_conf = p.get("costo_confeccion", 0.0)
            tipo_est = p.get("tipo_estampado") or "Ninguno"
            consumo_est = float(p.get("consumo_estampado") or 0.0)
            nombre_av = p.get("nombre_avio") or ""
            costo_av = float(p.get("costo_avio") or 0.0)

            productos.append(Producto(
                id=p["id"],
                nombre=p["nombre"],
                tela=tela_obj,
                consumo_metros=p["consumo_metros"],
                costo_confeccion=costo_conf,
                tipo_estampado=tipo_est,
                consumo_estampado=consumo_est,
                nombre_avio=nombre_av,
                costo_avio=costo_av
            ))
        return productos

    def guardar_presupuesto(self, presupuesto: Presupuesto) -> int:
        mult_val = presupuesto.multiplicador_usado
        # Si es un número entero (ej: 2.0), lo convertimos a int para evitar el error de Postgres con bigint
        if isinstance(mult_val, (int, float)) and float(mult_val).is_integer():
            mult_val = int(mult_val)

        cabecera = {
            "cliente_referencia": presupuesto.cliente,
            "multiplicador": mult_val,
            "costo_fijo": float(presupuesto.costo_fijo_usado),
            "precio_total": float(presupuesto.total_final)
        }
        try:
            res_cabecera = self.client.table("presupuestos").insert(cabecera).execute()
        except Exception:
            # Fallback en caso de que la columna multiplicador sea bigint y se haya ingresado un decimal
            cabecera["multiplicador"] = int(round(float(presupuesto.multiplicador_usado)))
            res_cabecera = self.client.table("presupuestos").insert(cabecera).execute()

        presupuesto_id = res_cabecera.data[0]["id"]

        detalles = []
        for item in presupuesto.items:
            detalles.append({
                "presupuesto_id": presupuesto_id,
                "producto_id": item.producto.id,
                "cantidad": int(item.cantidad),
                "precio_unitario": float(presupuesto.precio_unitario_final(item))
            })
        
        self.client.table("presupuesto_detalles").insert(detalles).execute()
        return presupuesto_id

    def obtener_presupuestos(self) -> list:
        return self.client.table("presupuestos").select("*").order("id", desc=True).execute().data

    def obtener_detalles_presupuesto(self, presupuesto_id: int) -> list:
        return self.client.table("presupuesto_detalles").select("*, productos(id, nombre)").eq("presupuesto_id", presupuesto_id).execute().data

    def eliminar_presupuesto(self, presupuesto_id: int):
        self.client.table("presupuesto_detalles").delete().eq("presupuesto_id", presupuesto_id).execute()
        self.client.table("presupuestos").delete().eq("id", presupuesto_id).execute()
    
    def actualizar_precio_tela(self, tela_id: int, nuevo_precio: float):
        self.client.table("telas").update({
            "precio_kilo": nuevo_precio
        }).eq("id", tela_id).execute()

    def actualizar_tela(self, tela_id: int, nombre: str, precio_kilo: float, rendimiento: float, descripcion: str = ""):
        datos = {
            "nombre": nombre,
            "precio_kilo": precio_kilo,
            "rendimiento": rendimiento,
            "descripcion": descripcion
        }
        try:
            self.client.table("telas").update(datos).eq("id", tela_id).execute()
        except Exception:
            datos_fallback = {"nombre": nombre, "precio_kilo": precio_kilo, "rendimiento": rendimiento}
            self.client.table("telas").update(datos_fallback).eq("id", tela_id).execute()

    def eliminar_tela(self, tela_id: int):
        self.client.table("telas").delete().eq("id", tela_id).execute()

# --- MÉTODOS DE INSERCIÓN Y GESTIÓN DE PRODUCTOS Y TELAS ---
    def agregar_tela(self, nombre: str, precio_kilo: float, rendimiento: float, descripcion: str = ""):
        datos = {
            "nombre": nombre, 
            "precio_kilo": precio_kilo, 
            "rendimiento": rendimiento,
            "descripcion": descripcion
        }
        try:
            self.client.table("telas").insert(datos).execute()
        except Exception:
            datos_fallback = {"nombre": nombre, "precio_kilo": precio_kilo, "rendimiento": rendimiento}
            self.client.table("telas").insert(datos_fallback).execute()

    def agregar_producto(self, nombre: str, tela_id: int, consumo: float, costo_confeccion: float, tipo_estampado: str = "Ninguno", consumo_estampado: float = 0.0, nombre_avio: str = "", costo_avio: float = 0.0):
        datos = {
            "nombre": nombre, 
            "tela_id": tela_id, 
            "consumo_metros": consumo,
            "costo_confeccion": costo_confeccion,
            "tipo_estampado": tipo_estampado,
            "consumo_estampado": consumo_estampado,
            "nombre_avio": nombre_avio,
            "costo_avio": costo_avio
        }
        try:
            self.client.table("productos").insert(datos).execute()
        except Exception:
            datos_fallback = {
                "nombre": nombre, 
                "tela_id": tela_id, 
                "consumo_metros": consumo,
                "costo_confeccion": costo_confeccion,
                "tipo_estampado": tipo_estampado,
                "consumo_estampado": consumo_estampado
            }
            try:
                self.client.table("productos").insert(datos_fallback).execute()
            except Exception:
                datos_base = {
                    "nombre": nombre, 
                    "tela_id": tela_id, 
                    "consumo_metros": consumo, 
                    "costo_confeccion": costo_confeccion
                }
                self.client.table("productos").insert(datos_base).execute()

    def actualizar_producto(self, producto_id: int, nombre: str, tela_id: int, consumo: float, costo_confeccion: float, tipo_estampado: str = "Ninguno", consumo_estampado: float = 0.0, nombre_avio: str = "", costo_avio: float = 0.0):
        datos = {
            "nombre": nombre, 
            "tela_id": tela_id, 
            "consumo_metros": consumo,
            "costo_confeccion": costo_confeccion,
            "tipo_estampado": tipo_estampado,
            "consumo_estampado": consumo_estampado,
            "nombre_avio": nombre_avio,
            "costo_avio": costo_avio
        }
        try:
            self.client.table("productos").update(datos).eq("id", producto_id).execute()
        except Exception:
            datos_fallback = {
                "nombre": nombre, 
                "tela_id": tela_id, 
                "consumo_metros": consumo,
                "costo_confeccion": costo_confeccion,
                "tipo_estampado": tipo_estampado,
                "consumo_estampado": consumo_estampado
            }
            try:
                self.client.table("productos").update(datos_fallback).eq("id", producto_id).execute()
            except Exception:
                datos_base = {
                    "nombre": nombre, 
                    "tela_id": tela_id, 
                    "consumo_metros": consumo, 
                    "costo_confeccion": costo_confeccion
                }
                self.client.table("productos").update(datos_base).eq("id", producto_id).execute()

    def eliminar_producto(self, producto_id: int):
        self.client.table("productos").delete().eq("id", producto_id).execute()

    # --- MÉTODOS AUXILIARES PARA LOS SELECTS ---
    
    def obtener_tipos_estampado(self):
        return self.client.table("tipo_estampado").select("*").execute().data

    # --- MÉTODOS DE CONFIGURACIÓN ---
    def obtener_configuracion(self):
        # Lee la fila de configuración base
        config_res = self.client.table("configuracion").select("*").eq("id", 1).execute()
        config_data = config_res.data[0] if config_res.data else {"costo_fijo": 6000.0, "multiplicador": 2.0}

        # Obtenemos los costos de tipo_estampado
        estampados = self.obtener_tipos_estampado()
        estampados_dict = {}
        for item in estampados:
            nombre_norm = normalizar_texto(item.get("nombre") or "")
            if item.get("costo") is not None:
                estampados_dict[nombre_norm] = float(item["costo"])

        desc_pdf = config_data.get("descripcion_pdf")
        if not desc_pdf:
            extra = leer_config_extra()
            desc_pdf = extra.get("descripcion_pdf", "Presupuesto válido por 15 días corridos a partir de la fecha de emisión. Precios sujetos a variación de insumos.")

        return {
            "costo_fijo": seguro_float(config_data.get("costo_fijo"), 6000.0),
            "multiplicador": seguro_float(config_data.get("multiplicador"), 2.0),
            "precio_metro_dtf": seguro_float(estampados_dict.get("dtf"), 0.0),
            "precio_metro_sublimacion": seguro_float(estampados_dict.get("sublimacion"), 0.0),
            "precio_unidad_serigrafia": seguro_float(estampados_dict.get("serigrafia"), 0.0),
            "precio_unidad_bordado": seguro_float(estampados_dict.get("bordado"), 0.0),
            "descripcion_pdf": str(desc_pdf or "Presupuesto válido por 15 días corridos a partir de la fecha de emisión. Precios sujetos a variación de insumos.")
        }

    def actualizar_configuracion(self, costo_fijo: float, multiplicador: float, precio_dtf: float = 0.0, precio_sublimacion: float = 0.0, precio_serigrafia: float = 0.0, precio_bordado: float = 0.0, descripcion_pdf: str = ""):
        guardar_config_extra({"descripcion_pdf": descripcion_pdf})
        try:
            self.client.table("configuracion").update({
                "costo_fijo": costo_fijo, 
                "multiplicador": multiplicador,
                "descripcion_pdf": descripcion_pdf
            }).eq("id", 1).execute()
        except Exception:
            self.client.table("configuracion").update({
                "costo_fijo": costo_fijo, 
                "multiplicador": multiplicador
            }).eq("id", 1).execute()

        # Obtenemos estampados existentes
        estampados_actuales = self.obtener_tipos_estampado()
        
        # Mapeamos nombre normalizado a lista de IDs
        estampados_map = {}
        for item in estampados_actuales:
            nom_norm = normalizar_texto(item.get("nombre") or "")
            if nom_norm not in estampados_map:
                estampados_map[nom_norm] = []
            estampados_map[nom_norm].append(item["id"])

        valores_nuevos = [
            ("DTF", "dtf", precio_dtf),
            ("Sublimación", "sublimacion", precio_sublimacion),
            ("Serigrafía", "serigrafia", precio_serigrafia),
            ("Bordado", "bordado", precio_bordado),
        ]

        for nombre_display, clave_norm, costo in valores_nuevos:
            ids = estampados_map.get(clave_norm, [])
            if ids:
                self.client.table("tipo_estampado").update({"costo": costo, "nombre": nombre_display}).eq("id", ids[0]).execute()
                # Limpiamos duplicados si hubiera
                for dup_id in ids[1:]:
                    self.client.table("tipo_estampado").delete().eq("id", dup_id).execute()
            else:
                self.client.table("tipo_estampado").insert({"nombre": nombre_display, "costo": costo}).execute()

# --- FUNCIONES DE EXPORTACIÓN ---

def generar_pdf_presupuesto(presupuesto_o_cliente, items: list = None, total: float = None, fecha: str = None, descripcion_pdf: str = None) -> bytes:
    if isinstance(presupuesto_o_cliente, Presupuesto):
        presupuesto = presupuesto_o_cliente
        cliente = presupuesto.cliente or "Consumidor Final"
        items_data = [
            {
                "nombre": item.producto.nombre,
                "cantidad": item.cantidad,
                "precio_unitario": presupuesto.precio_unitario_final(item),
                "subtotal": presupuesto.subtotal_final(item),
            }
            for item in presupuesto.items
        ]
        total_val = presupuesto.total_final
        fecha_val = datetime.now().strftime("%d/%m/%Y")
        desc_final = descripcion_pdf or getattr(presupuesto.config, "descripcion_pdf", "")
    else:
        cliente = str(presupuesto_o_cliente or "Consumidor Final")
        items_data = items or []
        total_val = total if total is not None else sum(float(i.get("subtotal", 0.0)) for i in items_data)
        fecha_val = fecha or datetime.now().strftime("%d/%m/%Y")
        desc_final = descripcion_pdf or ""

    class PDF(FPDF):
        def header(self):
            # Membrete con marca SIMPLE destacada
            self.set_font("Helvetica", "B", 26)
            self.set_text_color(18, 30, 49)
            self.cell(0, 11, "SIMPLE MDQ", new_x="LMARGIN", new_y="NEXT", align="L")
            self.set_font("Helvetica", "B", 12)
            self.set_text_color(71, 85, 105)
            self.cell(0, 6, "PRESUPUESTO / COTIZACION", new_x="LMARGIN", new_y="NEXT", align="L")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5, "Diseño y Confeccion Textil", new_x="LMARGIN", new_y="NEXT", align="L")
            self.ln(3)
            self.set_draw_color(210, 215, 225)
            self.set_line_width(0.5)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(5)

        def footer(self):
            self.set_y(-20)
            self.set_draw_color(220, 220, 220)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(3)
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 4, "SIMPLE", new_x="LMARGIN", new_y="NEXT", align="C")
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(130, 130, 130)
            self.cell(0, 4, "Presupuesto valido por 30 dias corridos a partir de la fecha de emision.", new_x="LMARGIN", new_y="NEXT", align="C")

    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    # Datos cabecera
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(100, 7, f"Cliente: {cliente}", align="L")
    pdf.cell(90, 7, f"Fecha: {fecha_val}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(5)

    # Tabla sin columna de estampado
    columnas = [
        ("Prenda / Producto", 100),
        ("Cantidad", 25),
        ("Precio Unit.", 32),
        ("Subtotal", 33),
    ]

    pdf.set_fill_color(240, 243, 250)
    pdf.set_text_color(20, 30, 60)
    pdf.set_font("Helvetica", "B", 9)
    for col_name, width in columnas:
        align = "R" if col_name != "Prenda / Producto" else "L"
        pdf.cell(width, 8, col_name, border=1, fill=True, align=align)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 40)
    for item in items_data:
        nombre = str(item.get("nombre", ""))
        cant = str(item.get("cantidad", 0))
        p_unit = f"${float(item.get('precio_unitario', 0.0)):,.2f}"
        subt = f"${float(item.get('subtotal', 0.0)):,.2f}"

        pdf.cell(100, 7, nombre[:50], border=1, align="L")
        pdf.cell(25, 7, cant, border=1, align="R")
        pdf.cell(32, 7, p_unit, border=1, align="R")
        pdf.cell(33, 7, subt, border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.ln(4)

    # Total
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(240, 245, 255)
    cant_total = sum(int(item.get("cantidad", 0)) for item in items_data)
    pdf.cell(125, 10, f"Total Prendas: {cant_total} u.", border=0, align="L")
    pdf.cell(65, 10, f"TOTAL: ${total_val:,.2f}", border=1, fill=True, new_x="LMARGIN", new_y="NEXT", align="R")

    # Observaciones y condiciones personalizadas
    if desc_final and desc_final.strip():
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(70, 80, 95)
        pdf.cell(0, 5, "Observaciones y Condiciones:", new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(190, 4, desc_final.strip(), border=0, align="L")

    return bytes(pdf.output())