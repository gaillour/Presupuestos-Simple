from typing import List, Optional
from datetime import datetime
import os
from fastapi import FastAPI, HTTPException, status, Response, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

import core
from core import (
    Database,
    Config,
    Tela,
    Producto,
    ItemPresupuesto,
    Presupuesto,
    generar_pdf_presupuesto,
    mensaje_error_amigable,
    seguro_float,
)

# Inicialización de FastAPI con esquema de seguridad Bearer
app = FastAPI(
    title="Presupuestos Simple API",
    description="API RESTful para el cálculo de costos, gestión de telas, catálogo de productos y cotizaciones textiles con autenticación Supabase Auth.",
    version="1.1.0",
)

# Configuración de CORS según REFACTOR_CONTEXT.md
# Configuración de CORS para Vercel (*.vercel.app), entornos locales y dominios configurados
raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url and frontend_url.strip() not in allowed_origins:
    allowed_origins.append(frontend_url.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instancia central de base de datos
db = Database()

# Esquema de seguridad Bearer (auto_error=False para personalizar las respuestas 401)
bearer_scheme = HTTPBearer(auto_error=False)


# --- AUTENTICACIÓN & DEPENDENCIAS ---

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)):
    """Verifica el token JWT contra Supabase Auth y retorna el usuario autenticado."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Token JWT requerido en el encabezado Authorization.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        res = db.client.auth.get_user(token)
        if not res or not res.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido o expirado.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return res.user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada o token no válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verificar_acceso_pdf(
    token_query: Optional[str] = Query(None, alias="token", description="Token opcional en query param para visualización en pestaña"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """Permite autenticar la descarga de PDF tanto por Bearer Header como por parámetro query ?token=."""
    token = credentials.credentials if credentials else token_query
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Se requiere token para descargar el comprobante.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        res = db.client.auth.get_user(token)
        if not res or not res.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido o expirado.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return res.user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada o token no válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# --- MODELOS PYDANTIC ---

class LoginRequest(BaseModel):
    email: str = Field(..., description="Correo electrónico registrado en Supabase Auth")
    password: str = Field(..., description="Contraseña de acceso")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    expires_at: Optional[int] = None
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    role: str = "authenticated"


class ConfiguracionUpdate(BaseModel):
    costo_fijo: float = Field(..., ge=0, description="Costo fijo base por prenda")
    multiplicador: float = Field(..., ge=1.0, description="Multiplicador / margen de ganancia general")
    precio_dtf: float = Field(0.0, ge=0, description="Precio por metro de estampa DTF")
    precio_sublimacion: float = Field(0.0, ge=0, description="Precio por metro de Sublimación")
    precio_serigrafia: float = Field(0.0, ge=0, description="Precio por unidad de Serigrafía")
    precio_bordado: float = Field(0.0, ge=0, description="Precio por unidad de Bordado")
    descripcion_pdf: str = Field("", description="Condiciones u observaciones al pie del PDF")


class TelaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, description="Nombre de la tela")
    precio_kilo: float = Field(..., gt=0, description="Precio por kilo")
    rendimiento: float = Field(..., gt=0, description="Rendimiento en metros por kilo")
    descripcion: str = Field("", description="Descripción o notas de la tela")


class TelaUpdate(BaseModel):
    nombre: str = Field(..., min_length=1)
    precio_kilo: float = Field(..., gt=0)
    rendimiento: float = Field(..., gt=0)
    descripcion: str = ""


class ProductoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, description="Nombre de la prenda / producto")
    tela_id: int = Field(..., description="ID de la tela asociada")
    consumo_metros: float = Field(..., gt=0, description="Consumo de tela en metros por prenda")
    costo_confeccion: float = Field(..., ge=0, description="Costo de confección o taller")
    tipo_estampado: str = Field("Ninguno", description="Técnica de estampado: Ninguno, DTF, Sublimación, Serigrafía, Bordado")
    consumo_estampado: float = Field(0.0, ge=0, description="Consumo de estampado (metros o unidades)")
    nombre_avio: str = Field("", description="Nombre del avío si aplica (ej: Cierres, Botones)")
    costo_avio: float = Field(0.0, ge=0, description="Costo adicional por avíos")


class ProductoUpdate(BaseModel):
    nombre: str = Field(..., min_length=1)
    tela_id: int
    consumo_metros: float = Field(..., gt=0)
    costo_confeccion: float = Field(..., ge=0)
    tipo_estampado: str = "Ninguno"
    consumo_estampado: float = Field(0.0, ge=0)
    nombre_avio: str = ""
    costo_avio: float = Field(0.0, ge=0)


class ItemPresupuestoInput(BaseModel):
    producto_id: int = Field(..., description="ID del producto en catálogo")
    cantidad: int = Field(..., gt=0, description="Cantidad de prendas")
    detalle_estampado: Optional[str] = Field(None, description="Detalle opcional de la estampa")
    costo_estampado_personalizado: Optional[float] = Field(None, ge=0, description="Sobrescribir costo unitario de estampado si se requiere")


class PresupuestoRequest(BaseModel):
    cliente: str = Field(..., min_length=1, description="Nombre o referencia del cliente")
    multiplicador: Optional[float] = Field(None, ge=1.0, description="Multiplicador personalizado (opcional)")
    costo_fijo: Optional[float] = Field(None, ge=0, description="Costo fijo personalizado (opcional)")
    items: List[ItemPresupuestoInput] = Field(..., min_length=1, description="Lista de ítems cotizados")


# --- HELPERS INTERNOS ---

def _obtener_config_obj() -> Config:
    """Obtiene la configuración actual y construye el objeto de dominio Config."""
    cfg_data = db.obtener_configuracion()
    return Config(
        costo_fijo_base=seguro_float(cfg_data.get("costo_fijo"), 6000.0),
        multiplicador_default=seguro_float(cfg_data.get("multiplicador"), 2.0),
        precio_metro_dtf=seguro_float(cfg_data.get("precio_metro_dtf"), 0.0),
        precio_metro_sublimacion=seguro_float(cfg_data.get("precio_metro_sublimacion"), 0.0),
        precio_unidad_serigrafia=seguro_float(cfg_data.get("precio_unidad_serigrafia"), 0.0),
        precio_unidad_bordado=seguro_float(cfg_data.get("precio_unidad_bordado"), 0.0),
        descripcion_pdf=str(cfg_data.get("descripcion_pdf", "")),
    )


# --- ENDPOINTS: HEALTH CHECK (PÚBLICO) ---

@app.get("/api/health", tags=["Estado"])
def health_check():
    return {"status": "ok", "service": "Presupuestos Simple API"}


# --- ENDPOINTS: AUTENTICACIÓN ---

@app.post("/api/auth/login", response_model=LoginResponse, tags=["Autenticación"])
def login(credenciales: LoginRequest):
    """Autentica al usuario contra Supabase Auth y retorna el JWT Bearer Token."""
    try:
        res = db.client.auth.sign_in_with_password({
            "email": credenciales.email,
            "password": credenciales.password,
        })
        if not res.session or not res.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas.",
            )
        return {
            "access_token": res.session.access_token,
            "token_type": "bearer",
            "expires_in": res.session.expires_in,
            "expires_at": res.session.expires_at,
            "user": {
                "id": res.user.id,
                "email": res.user.email,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e).lower()
        if "invalid login credentials" in err_msg or "invalid credentials" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email o contraseña incorrectos.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo iniciar sesión: {str(e)}",
        )


@app.get("/api/auth/me", response_model=UserResponse, tags=["Autenticación"])
def get_me(user=Depends(get_current_user)):
    """Retorna la información del usuario autenticado actual."""
    return {
        "id": user.id,
        "email": user.email,
        "role": getattr(user, "role", "authenticated"),
    }


@app.post("/api/auth/logout", tags=["Autenticación"])
def logout(user=Depends(get_current_user)):
    """Cierra la sesión del usuario en Supabase Auth."""
    try:
        db.client.auth.sign_out()
    except Exception:
        pass
    return {"message": "Sesión cerrada correctamente"}


# --- ENDPOINTS: CONFIGURACIÓN GENERAL (PROTEGIDOS) ---

@app.get("/api/configuracion", tags=["Configuración"])
def obtener_configuracion(user=Depends(get_current_user)):
    try:
        return db.obtener_configuracion()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mensaje_error_amigable(e, "obtener la configuración"),
        )


@app.put("/api/configuracion", tags=["Configuración"])
def actualizar_configuracion(datos: ConfiguracionUpdate, user=Depends(get_current_user)):
    try:
        db.actualizar_configuracion(
            costo_fijo=datos.costo_fijo,
            multiplicador=datos.multiplicador,
            precio_dtf=datos.precio_dtf,
            precio_sublimacion=datos.precio_sublimacion,
            precio_serigrafia=datos.precio_serigrafia,
            precio_bordado=datos.precio_bordado,
            descripcion_pdf=datos.descripcion_pdf,
        )
        return {
            "message": "Configuración actualizada correctamente",
            "configuracion": db.obtener_configuracion(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "actualizar la configuración"),
        )


# --- ENDPOINTS: CATÁLOGO DE TELAS (PROTEGIDOS) ---

@app.get("/api/telas", tags=["Telas"])
def listar_telas(user=Depends(get_current_user)):
    try:
        telas = db.obtener_telas()
        return [
            {
                "id": t.id,
                "nombre": t.nombre,
                "precio_kilo": t.precio_kilo,
                "rendimiento": t.rendimiento,
                "descripcion": t.descripcion,
                "precio_metro": round(t.precio_metro, 2),
            }
            for t in telas
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mensaje_error_amigable(e, "obtener las telas"),
        )


@app.post("/api/telas", status_code=status.HTTP_201_CREATED, tags=["Telas"])
def crear_tela(tela: TelaCreate, user=Depends(get_current_user)):
    try:
        db.agregar_tela(
            nombre=tela.nombre,
            precio_kilo=tela.precio_kilo,
            rendimiento=tela.rendimiento,
            descripcion=tela.descripcion,
        )
        return {"message": "Tela agregada correctamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "agregar la tela"),
        )


@app.put("/api/telas/{tela_id}", tags=["Telas"])
def actualizar_tela(tela_id: int, tela: TelaUpdate, user=Depends(get_current_user)):
    try:
        db.actualizar_tela(
            tela_id=tela_id,
            nombre=tela.nombre,
            precio_kilo=tela.precio_kilo,
            rendimiento=tela.rendimiento,
            descripcion=tela.descripcion,
        )
        return {"message": "Tela actualizada correctamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "actualizar la tela"),
        )


@app.delete("/api/telas/{tela_id}", tags=["Telas"])
def eliminar_tela(tela_id: int, user=Depends(get_current_user)):
    try:
        db.eliminar_tela(tela_id)
        return {"message": "Tela eliminada correctamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "eliminar la tela"),
        )


# --- ENDPOINTS: CATÁLOGO DE PRODUCTOS (PROTEGIDOS) ---

@app.get("/api/productos", tags=["Productos"])
def listar_productos(user=Depends(get_current_user)):
    try:
        config_obj = _obtener_config_obj()
        productos = db.obtener_productos()

        resultado = []
        for p in productos:
            costo_est = p.costo_estampado(config_obj)
            costo_prod = p.costo_produccion(config_obj)
            precio_vta = p.precio_venta(config_obj)

            resultado.append({
                "id": p.id,
                "nombre": p.nombre,
                "tela": {
                    "id": p.tela.id,
                    "nombre": p.tela.nombre,
                    "precio_kilo": p.tela.precio_kilo,
                    "rendimiento": p.tela.rendimiento,
                    "precio_metro": round(p.tela.precio_metro, 2),
                },
                "consumo_metros": p.consumo_metros,
                "costo_confeccion": p.costo_confeccion,
                "tipo_estampado": p.tipo_estampado,
                "consumo_estampado": p.consumo_estampado,
                "nombre_avio": p.nombre_avio,
                "costo_avio": p.costo_avio,
                "costo_tela": round(p.costo_tela, 2),
                "costo_estampado": round(costo_est, 2),
                "costo_base": round(p.costo_base, 2),
                "costo_produccion": round(costo_prod, 2),
                "precio_venta": round(precio_vta, 2),
            })
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mensaje_error_amigable(e, "obtener los productos"),
        )


@app.post("/api/productos", status_code=status.HTTP_201_CREATED, tags=["Productos"])
def crear_producto(prod: ProductoCreate, user=Depends(get_current_user)):
    try:
        db.agregar_producto(
            nombre=prod.nombre,
            tela_id=prod.tela_id,
            consumo=prod.consumo_metros,
            costo_confeccion=prod.costo_confeccion,
            tipo_estampado=prod.tipo_estampado,
            consumo_estampado=prod.consumo_estampado,
            nombre_avio=prod.nombre_avio,
            costo_avio=prod.costo_avio,
        )
        return {"message": "Producto agregado correctamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "agregar el producto"),
        )


@app.put("/api/productos/{producto_id}", tags=["Productos"])
def actualizar_producto(producto_id: int, prod: ProductoUpdate, user=Depends(get_current_user)):
    try:
        db.actualizar_producto(
            producto_id=producto_id,
            nombre=prod.nombre,
            tela_id=prod.tela_id,
            consumo=prod.consumo_metros,
            costo_confeccion=prod.costo_confeccion,
            tipo_estampado=prod.tipo_estampado,
            consumo_estampado=prod.consumo_estampado,
            nombre_avio=prod.nombre_avio,
            costo_avio=prod.costo_avio,
        )
        return {"message": "Producto actualizado correctamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "actualizar el producto"),
        )


@app.delete("/api/productos/{producto_id}", tags=["Productos"])
def eliminar_producto(producto_id: int, user=Depends(get_current_user)):
    try:
        db.eliminar_producto(producto_id)
        return {"message": "Producto eliminado correctamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "eliminar el producto"),
        )


# --- ENDPOINTS: PRESUPUESTOS (PROTEGIDOS) ---

def _construir_objeto_presupuesto(datos: PresupuestoRequest) -> Presupuesto:
    """Construye el objeto de dominio Presupuesto a partir de la petición."""
    config_obj = _obtener_config_obj()
    productos_dict = {p.id: p for p in db.obtener_productos()}

    items_dominio = []
    for item_req in datos.items:
        prod = productos_dict.get(item_req.producto_id)
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con ID {item_req.producto_id} no encontrado en el catálogo.",
            )

        if item_req.costo_estampado_personalizado is not None:
            costo_est = item_req.costo_estampado_personalizado
        else:
            costo_est = prod.costo_estampado(config_obj)

        detalle_est = item_req.detalle_estampado or prod.tipo_estampado

        items_dominio.append(
            ItemPresupuesto(
                producto=prod,
                cantidad=item_req.cantidad,
                detalle_estampado=detalle_est,
                costo_estampado=costo_est,
            )
        )

    mult_val = datos.multiplicador if datos.multiplicador is not None else config_obj.multiplicador_default
    costo_fijo_val = datos.costo_fijo if datos.costo_fijo is not None else config_obj.costo_fijo_base

    return Presupuesto(
        cliente=datos.cliente,
        items=items_dominio,
        config=config_obj,
        multiplicador_usado=mult_val,
        costo_fijo_usado=costo_fijo_val,
    )


@app.get("/api/presupuestos", tags=["Presupuestos"])
def listar_presupuestos(user=Depends(get_current_user)):
    try:
        return db.obtener_presupuestos()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mensaje_error_amigable(e, "obtener los presupuestos"),
        )


@app.get("/api/presupuestos/{presupuesto_id}", tags=["Presupuestos"])
def obtener_presupuesto(presupuesto_id: int, user=Depends(get_current_user)):
    try:
        cabecera = db.obtener_presupuesto_por_id(presupuesto_id)
        if not cabecera or not cabecera.get("activo", True):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Presupuesto #{presupuesto_id} no encontrado.",
            )
        detalles = db.obtener_detalles_presupuesto(presupuesto_id)
        return {
            "presupuesto": cabecera,
            "detalles": detalles,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mensaje_error_amigable(e, "obtener los detalles del presupuesto"),
        )


@app.post("/api/presupuestos/calcular", tags=["Presupuestos"])
def calcular_presupuesto(datos: PresupuestoRequest, user=Depends(get_current_user)):
    """Calcula y desglosa un presupuesto en vivo sin persistirlo en la base de datos."""
    try:
        presupuesto = _construir_objeto_presupuesto(datos)

        items_calculados = []
        for item in presupuesto.items:
            items_calculados.append({
                "producto_id": item.producto.id,
                "nombre": item.producto.nombre,
                "cantidad": item.cantidad,
                "detalle_estampado": item.detalle_estampado,
                "costo_estampado": round(item.costo_estampado, 2),
                "costo_base_unitario": round(item.costo_base_unitario, 2),
                "precio_unitario": round(presupuesto.precio_unitario_final(item), 2),
                "subtotal": round(presupuesto.subtotal_final(item), 2),
            })

        return {
            "cliente": presupuesto.cliente,
            "multiplicador_usado": presupuesto.multiplicador_usado,
            "costo_fijo_usado": presupuesto.costo_fijo_usado,
            "items": items_calculados,
            "total_prendas": sum(i.cantidad for i in presupuesto.items),
            "total_final": round(presupuesto.total_final, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mensaje_error_amigable(e, "calcular el presupuesto"),
        )


@app.post("/api/presupuestos", status_code=status.HTTP_201_CREATED, tags=["Presupuestos"])
def guardar_presupuesto(datos: PresupuestoRequest, user=Depends(get_current_user)):
    """Calcula y persiste un presupuesto junto con sus ítems en Supabase."""
    try:
        presupuesto = _construir_objeto_presupuesto(datos)
        presupuesto_id = db.guardar_presupuesto(presupuesto)
        return {
            "id": presupuesto_id,
            "message": "Presupuesto guardado correctamente",
            "total_final": round(presupuesto.total_final, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "guardar el presupuesto"),
        )


@app.delete("/api/presupuestos/{presupuesto_id}", tags=["Presupuestos"])
def eliminar_presupuesto(presupuesto_id: int, user=Depends(get_current_user)):
    try:
        db.eliminar_presupuesto(presupuesto_id)
        return {"message": f"Presupuesto #{presupuesto_id} eliminado correctamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_error_amigable(e, "eliminar el presupuesto"),
        )


@app.get("/api/presupuestos/{presupuesto_id}/pdf", tags=["Presupuestos"])
def descargar_pdf_presupuesto(presupuesto_id: int, user=Depends(verificar_acceso_pdf)):
    """Genera y retorna el archivo PDF del presupuesto cotizado."""
    try:
        cabecera = db.obtener_presupuesto_por_id(presupuesto_id)
        if not cabecera or not cabecera.get("activo", True):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Presupuesto #{presupuesto_id} no encontrado.",
            )

        detalles = db.obtener_detalles_presupuesto(presupuesto_id)
        cfg_data = db.obtener_configuracion()

        items_para_pdf = []
        for d in detalles:
            prod_info = d.get("productos")
            nombre_prod = prod_info.get("nombre") if isinstance(prod_info, dict) else f"Producto #{d.get('producto_id')}"
            cant = int(d.get("cantidad", 0))
            p_unit = float(d.get("precio_unitario", 0.0))
            subt = cant * p_unit

            items_para_pdf.append({
                "nombre": nombre_prod,
                "cantidad": cant,
                "precio_unitario": p_unit,
                "subtotal": subt,
            })

        fecha_raw = cabecera.get("created_at")
        if fecha_raw:
            try:
                dt = datetime.fromisoformat(fecha_raw.replace("Z", "+00:00"))
                fecha_str = dt.strftime("%d/%m/%Y")
            except Exception:
                fecha_str = datetime.now().strftime("%d/%m/%Y")
        else:
            fecha_str = datetime.now().strftime("%d/%m/%Y")

        pdf_bytes = generar_pdf_presupuesto(
            presupuesto_o_cliente=cabecera.get("cliente_referencia", "Consumidor Final"),
            items=items_para_pdf,
            total=float(cabecera.get("precio_total", 0.0)),
            fecha=fecha_str,
            descripcion_pdf=cfg_data.get("descripcion_pdf", ""),
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename=presupuesto_{presupuesto_id}.pdf"
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mensaje_error_amigable(e, "generar el PDF del presupuesto"),
        )


# --- ENDPOINTS: TÉCNICAS DE ESTAMPADO (PROTEGIDOS) ---

@app.get("/api/tipos-estampado", tags=["Estampados"])
def listar_tipos_estampado(user=Depends(get_current_user)):
    try:
        return db.obtener_tipos_estampado()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mensaje_error_amigable(e, "obtener los tipos de estampado"),
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)

