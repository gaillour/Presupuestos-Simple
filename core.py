from dataclasses import dataclass, field
from typing import List
import unicodedata
import streamlit as st
from supabase import create_client, Client

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8').lower().strip()


# --- CLASES DE DATOS (MODELOS) ---

@dataclass
class Config:
    costo_fijo_base: float = 6000.0
    multiplicador_default: float = 2.0
    precio_metro_dtf: float = 0.0
    precio_metro_sublimacion: float = 0.0
    precio_unidad_serigrafia: float = 0.0

@dataclass
class Tela:
    id: int
    nombre: str
    precio_kilo: float
    rendimiento: float

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
    # ¡Chau estampado de acá!

    @property
    def costo_base(self) -> float:
        costo_tela = self.tela.precio_metro * self.consumo_metros
        return costo_tela + self.costo_confeccion

@dataclass
class ItemPresupuesto:
    producto: Producto
    cantidad: int
    detalle_estampado: str = ""
    costo_estampado: float = 0.0
    
    @property
    def costo_base_unitario(self) -> float:
        # Solo suma los costos puros (Tela + Confección + Estampado)
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
                rendimiento=t["rendimiento"]
            ))
        return telas

    def obtener_productos(self) -> List[Producto]:
        # Sacamos 'tipos_confeccion(*)' del select
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
                rendimiento=tela_data["rendimiento"]
            )
            
            # Ahora el costo viene directo como un número en el producto
            costo_conf = p.get("costo_confeccion", 0.0)

            productos.append(Producto(
                id=p["id"],
                nombre=p["nombre"],
                tela=tela_obj,
                consumo_metros=p["consumo_metros"],
                costo_confeccion=costo_conf
            ))
        return productos

    def guardar_presupuesto(self, presupuesto: Presupuesto) -> int:
        cabecera = {
            "cliente_referencia": presupuesto.cliente,
            "multiplicador": presupuesto.multiplicador_usado,
            "costo_fijo": presupuesto.costo_fijo_usado,
            "precio_total": presupuesto.total_final
        }
        res_cabecera = self.client.table("presupuestos").insert(cabecera).execute()
        presupuesto_id = res_cabecera.data[0]["id"]

        detalles = []
        for item in presupuesto.items:
            detalles.append({
                "presupuesto_id": presupuesto_id,
                "producto_id": item.producto.id,
                "cantidad": item.cantidad,
                "precio_unitario": presupuesto.precio_unitario_final(item) # Guarda el precio con la ganancia y el costo fijo aplicado
            })
        
        self.client.table("presupuesto_detalles").insert(detalles).execute()
        return presupuesto_id
    
    def actualizar_precio_tela(self, tela_id: int, nuevo_precio: float):
        self.client.table("telas").update({
            "precio_kilo": nuevo_precio
        }).eq("id", tela_id).execute()

# --- MÉTODOS DE INSERCIÓN ---
    def agregar_tela(self, nombre: str, precio_kilo: float, rendimiento: float):
        self.client.table("telas").insert({
            "nombre": nombre, "precio_kilo": precio_kilo, "rendimiento": rendimiento
        }).execute()



    def agregar_producto(self, nombre: str, tela_id: int, consumo: float, costo_confeccion: float):
        self.client.table("productos").insert({
            "nombre": nombre, 
            "tela_id": tela_id, 
            "consumo_metros": consumo,
            "costo_confeccion": costo_confeccion
        }).execute()

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

        return {
            "costo_fijo": float(config_data.get("costo_fijo", 6000.0)),
            "multiplicador": float(config_data.get("multiplicador", 2.0)),
            "precio_metro_dtf": estampados_dict.get("dtf", 0.0),
            "precio_metro_sublimacion": estampados_dict.get("sublimacion", 0.0),
            "precio_unidad_serigrafia": estampados_dict.get("serigrafia", 0.0),
        }

    def actualizar_configuracion(self, costo_fijo: float, multiplicador: float, precio_dtf: float = 0.0, precio_sublimacion: float = 0.0, precio_serigrafia: float = 0.0):
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