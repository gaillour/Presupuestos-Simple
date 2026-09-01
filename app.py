import streamlit as st
from datetime import datetime
from core import Database, ItemPresupuesto, Presupuesto, Config, generar_pdf_presupuesto


# 0 - login
def verificar_contrasena():
    """Devuelve True si la contraseña ingresada coincide con los secretos."""
    def validar():
        if st.session_state["clave_ingresada"] == st.secrets["passwords"]["pyme_admin"]:
            st.session_state["autorizado"] = True
            del st.session_state["clave_ingresada"]  # Limpiamos la variable por seguridad
        else:
            st.session_state["autorizado"] = False

    if "autorizado" not in st.session_state:
        st.title("🔒 Acceso Restringido")
        st.text_input("Ingresá la contraseña", type="password", on_change=validar, key="clave_ingresada")
        return False
    elif not st.session_state["autorizado"]:
        st.title("🔒 Acceso Restringido")
        st.text_input("Ingresá la contraseña", type="password", on_change=validar, key="clave_ingresada")
        st.error("Contraseña incorrecta.")
        return False
    
    return True

# Si la contraseña no está aprobada, st.stop() corta la ejecución de todo el código de acá para abajo.
if not verificar_contrasena():
    st.stop()

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Gestión Textil - Catálogo y Costos", layout="wide")

@st.cache_resource
def get_db():
    return Database()

db = get_db()

# Cargar configuración global para cálculos en tiempo real
config_dict = db.obtener_configuracion()
config_obj = Config(
    costo_fijo_base=float(config_dict.get("costo_fijo", 6000.0)),
    multiplicador_default=float(config_dict.get("multiplicador", 2.0)),
    precio_metro_dtf=float(config_dict.get("precio_metro_dtf", 0.0)),
    precio_metro_sublimacion=float(config_dict.get("precio_metro_sublimacion", 0.0)),
    precio_unidad_serigrafia=float(config_dict.get("precio_unidad_serigrafia", 0.0)),
    descripcion_pdf=str(config_dict.get("descripcion_pdf", "Presupuesto válido por 15 días corridos a partir de la fecha de emisión. Precios sujetos a variación de insumos."))
)

# --- 2. NAVEGACIÓN ---
st.sidebar.title("Sistema Textil")
opcion = st.sidebar.radio(
    "Seleccioná un módulo:", 
    [
        "Catálogo de Productos",
        "Catálogo de Telas",
        "Configuración General",
        "Generador de Presupuestos"
    ]
)

# --- 3. MÓDULO PRINCIPAL: CATÁLOGO DE PRODUCTOS ---
if opcion == "Catálogo de Productos":
    st.title("👕 Catálogo de Productos")
    st.caption("Gestioná y mantené actualizados los costos de producción y precios de venta de tus prendas.")

    tab_catalogo, tab_crear, tab_editar = st.tabs([
        "📋 Catálogo y Precios", 
        "➕ Nuevo Producto", 
        "✏️ Editar / Eliminar"
    ])

    productos = db.obtener_productos()
    telas = db.obtener_telas()

    # --- PESTAÑA 1: CATÁLOGO Y PRECIOS ---
    with tab_catalogo:
        with st.container(border=True):
            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            col_k1.metric("Prendas en Catálogo", len(productos))
            col_k2.metric("Multiplicador Vigente", f"{config_obj.multiplicador_default}x")
            col_k3.metric("Costo Fijo Base", f"${config_obj.costo_fijo_base:,.2f}")
            col_k4.metric("Técnicas Activas", "DTF / Sublimación / Serigrafía")

        if not productos:
            st.info("No hay productos cargados en el catálogo. Podés agregar el primero en la pestaña 'Nuevo Producto'.")
        else:
            filtro_nombre = st.text_input("Buscar prenda por nombre...", placeholder="Ej: Calza, Remera, Buzo...")
            
            prods_mostrados = [
                p for p in productos 
                if filtro_nombre.lower() in p.nombre.lower() or filtro_nombre.lower() in p.tela.nombre.lower()
            ] if filtro_nombre else productos

            tabla_prod = []
            for p in prods_mostrados:
                c_estampado = p.costo_estampado(config_obj)
                c_produccion = p.costo_produccion(config_obj)
                p_venta = p.precio_venta(config_obj)
                
                unidad_est = "m" if p.tipo_estampado in ["DTF", "Sublimación"] else "u"
                detalle_est = (
                    f"{p.tipo_estampado} ({p.consumo_estampado:.2f} {unidad_est})"
                    if p.tipo_estampado and p.tipo_estampado != "Ninguno" and p.consumo_estampado > 0
                    else "Sin estampado"
                )

                tabla_prod.append({
                    "ID": p.id,
                    "Prenda": p.nombre,
                    "Tela": p.tela.nombre,
                    "Consumo Tela": f"{p.consumo_metros:.2f} m",
                    "Costo Tela": f"${p.costo_tela:,.2f}",
                    "Costo Confección": f"${p.costo_confeccion:,.2f}",
                    "Estampado": detalle_est,
                    "Costo Estampado": f"${c_estampado:,.2f}",
                    "Costo Producción": f"${c_produccion:,.2f}",
                    "Precio Venta Catálogo": f"${p_venta:,.2f}"
                })

            st.dataframe(tabla_prod, width="stretch")

    # --- PESTAÑA 2: NUEVO PRODUCTO ---
    with tab_crear:
        st.subheader("Registrar Nueva Prenda en el Catálogo")
        if not telas:
            st.warning("⚠️ Debés cargar al menos una tela en el Catálogo de Telas antes de crear productos.")
        else:
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                nuevo_nombre = st.text_input("Nombre de la prenda", placeholder="Ej: Calza Larga con Sublimación")
                nueva_tela = st.selectbox("Tela", telas, format_func=lambda t: f"{t.nombre} (${t.precio_metro:,.2f}/m)")
                nuevo_consumo = st.number_input("Consumo de tela por prenda (metros)", min_value=0.01, step=0.05, value=0.75)
                nuevo_costo_conf = st.number_input("Costo de confección ($)", min_value=0.0, step=500.0, value=2500.0)

            with col_c2:
                nueva_tecnica = st.selectbox("Técnica de estampado", ["Ninguno", "Sublimación", "DTF", "Serigrafía"])
                
                if nueva_tecnica == "Sublimación":
                    p_ref = config_obj.precio_metro_sublimacion
                    nuevo_consumo_est = st.number_input("Metros de Sublimación por prenda", min_value=0.0, step=0.05, value=0.10)
                    st.info(f"Precio de referencia: **${p_ref:,.2f} / metro**")
                elif nueva_tecnica == "DTF":
                    p_ref = config_obj.precio_metro_dtf
                    nuevo_consumo_est = st.number_input("Metros de DTF por prenda", min_value=0.0, step=0.05, value=0.10)
                    st.info(f"Precio de referencia: **${p_ref:,.2f} / metro**")
                elif nueva_tecnica == "Serigrafía":
                    p_ref = config_obj.precio_unidad_serigrafia
                    nuevo_consumo_est = st.number_input("Cantidad de estampas por prenda", min_value=0.0, step=1.0, value=1.0)
                    st.info(f"Precio de referencia: **${p_ref:,.2f} / unidad**")
                else:
                    nuevo_consumo_est = 0.0
                    st.caption("Esta prenda no incluye estampado.")

            # Cálculo de costos en tiempo real
            costo_tela_prev = nueva_tela.precio_metro * nuevo_consumo
            if nueva_tecnica == "DTF":
                costo_est_prev = nuevo_consumo_est * config_obj.precio_metro_dtf
            elif nueva_tecnica == "Sublimación":
                costo_est_prev = nuevo_consumo_est * config_obj.precio_metro_sublimacion
            elif nueva_tecnica == "Serigrafía":
                costo_est_prev = nuevo_consumo_est * config_obj.precio_unidad_serigrafia
            else:
                costo_est_prev = 0.0

            costo_prod_prev = costo_tela_prev + nuevo_costo_conf + costo_est_prev
            precio_venta_prev = (costo_prod_prev * config_obj.multiplicador_default) + config_obj.costo_fijo_base

            with st.container(border=True):
                st.write("📊 **Desglose de Costos y Precio de Venta Estimado**")
                col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                col_m1.metric("Costo Tela", f"${costo_tela_prev:,.2f}")
                col_m2.metric("Confección", f"${nuevo_costo_conf:,.2f}")
                col_m3.metric("Estampado", f"${costo_est_prev:,.2f}")
                col_m4.metric("Costo Producción", f"${costo_prod_prev:,.2f}")
                col_m5.metric("Precio Venta Catálogo", f"${precio_venta_prev:,.2f}")

            if st.button("💾 Guardar Producto en Catálogo", type="primary"):
                if not nuevo_nombre.strip():
                    st.error("Por favor, ingresá el nombre de la prenda.")
                else:
                    db.agregar_producto(
                        nombre=nuevo_nombre.strip(),
                        tela_id=nueva_tela.id,
                        consumo=nuevo_consumo,
                        costo_confeccion=nuevo_costo_conf,
                        tipo_estampado=nueva_tecnica,
                        consumo_estampado=nuevo_consumo_est
                    )
                    st.success(f"¡Producto '{nuevo_nombre}' agregado al catálogo con éxito!")
                    st.rerun()

    # --- PESTAÑA 3: EDITAR / ELIMINAR ---
    with tab_editar:
        st.subheader("Modificar o Eliminar Prenda")
        if not productos:
            st.info("No hay productos disponibles para editar.")
        else:
            prod_seleccionado = st.selectbox(
                "Seleccioná la prenda a editar:", 
                productos, 
                format_func=lambda p: f"{p.nombre} (ID: {p.id} | Tela: {p.tela.nombre})"
            )

            col_e1, col_e2 = st.columns(2)
            with col_e1:
                edit_nombre = st.text_input("Nombre de la prenda", value=prod_seleccionado.nombre)
                
                # Encontrar índice de tela actual
                idx_tela = 0
                for i, t in enumerate(telas):
                    if t.id == prod_seleccionado.tela.id:
                        idx_tela = i
                        break
                edit_tela = st.selectbox("Tela", telas, index=idx_tela, format_func=lambda t: f"{t.nombre} (${t.precio_metro:,.2f}/m)", key="edit_tela_sel")
                edit_consumo = st.number_input("Consumo de tela por prenda (metros)", min_value=0.01, step=0.05, value=float(prod_seleccionado.consumo_metros), key="edit_consumo_input")
                edit_costo_conf = st.number_input("Costo de confección ($)", min_value=0.0, step=500.0, value=float(prod_seleccionado.costo_confeccion), key="edit_conf_input")

            with col_e2:
                tecnicas_disponibles = ["Ninguno", "Sublimación", "DTF", "Serigrafía"]
                idx_tec = 0
                for i, tec in enumerate(tecnicas_disponibles):
                    if tec.lower() == (prod_seleccionado.tipo_estampado or "").lower():
                        idx_tec = i
                        break
                edit_tecnica = st.selectbox("Técnica de estampado", tecnicas_disponibles, index=idx_tec, key="edit_tec_sel")
                
                if edit_tecnica == "Sublimación":
                    p_ref = config_obj.precio_metro_sublimacion
                    edit_consumo_est = st.number_input("Metros de Sublimación por prenda", min_value=0.0, step=0.05, value=float(prod_seleccionado.consumo_estampado), key="edit_sub_input")
                    st.info(f"Precio de referencia: **${p_ref:,.2f} / metro**")
                elif edit_tecnica == "DTF":
                    p_ref = config_obj.precio_metro_dtf
                    edit_consumo_est = st.number_input("Metros de DTF por prenda", min_value=0.0, step=0.05, value=float(prod_seleccionado.consumo_estampado), key="edit_dtf_input")
                    st.info(f"Precio de referencia: **${p_ref:,.2f} / metro**")
                elif edit_tecnica == "Serigrafía":
                    p_ref = config_obj.precio_unidad_serigrafia
                    edit_consumo_est = st.number_input("Cantidad de estampas por prenda", min_value=0.0, step=1.0, value=float(prod_seleccionado.consumo_estampado), key="edit_seri_input")
                    st.info(f"Precio de referencia: **${p_ref:,.2f} / unidad**")
                else:
                    edit_consumo_est = 0.0
                    st.caption("Esta prenda no incluye estampado.")

            # Vista previa de cambios
            edit_costo_tela = edit_tela.precio_metro * edit_consumo
            if edit_tecnica == "DTF":
                edit_costo_est = edit_consumo_est * config_obj.precio_metro_dtf
            elif edit_tecnica == "Sublimación":
                edit_costo_est = edit_consumo_est * config_obj.precio_metro_sublimacion
            elif edit_tecnica == "Serigrafía":
                edit_costo_est = edit_consumo_est * config_obj.precio_unidad_serigrafia
            else:
                edit_costo_est = 0.0

            edit_costo_prod = edit_costo_tela + edit_costo_conf + edit_costo_est
            edit_precio_venta = (edit_costo_prod * config_obj.multiplicador_default) + config_obj.costo_fijo_base

            with st.container(border=True):
                st.write("📊 **Previsualización con los Nuevos Valores**")
                col_em1, col_em2, col_em3, col_em4 = st.columns(4)
                col_em1.metric("Costo Tela", f"${edit_costo_tela:,.2f}")
                col_em2.metric("Costo Estampado", f"${edit_costo_est:,.2f}")
                col_em3.metric("Costo Producción", f"${edit_costo_prod:,.2f}")
                col_em4.metric("Nuevo Precio Venta", f"${edit_precio_venta:,.2f}")

            col_btn_edit, col_btn_del = st.columns([2, 1])
            with col_btn_edit:
                if st.button("💾 Guardar Cambios en la Prenda", type="primary"):
                    db.actualizar_producto(
                        producto_id=prod_seleccionado.id,
                        nombre=edit_nombre.strip(),
                        tela_id=edit_tela.id,
                        consumo=edit_consumo,
                        costo_confeccion=edit_costo_conf,
                        tipo_estampado=edit_tecnica,
                        consumo_estampado=edit_consumo_est
                    )
                    st.success(f"Prenda '{edit_nombre}' actualizada correctamente.")
                    st.rerun()

            with col_btn_del:
                if st.button("🗑️ Eliminar Prenda del Catálogo", type="secondary"):
                    db.eliminar_producto(prod_seleccionado.id)
                    st.success(f"Prenda eliminada del catálogo.")
                    st.rerun()


# --- 4. MÓDULO: CATÁLOGO DE TELAS ---
elif opcion == "Catálogo de Telas":
    st.title("🧵 Catálogo de Telas")
    st.caption("Gestioná los precios por kilo y rendimiento de tus telas. Al cambiar un precio, se actualizan todas las prendas asociadas.")
    
    tab_telas_catalogo, tab_telas_nueva, tab_telas_editar = st.tabs([
        "📋 Catálogo de Telas", 
        "➕ Nueva Tela", 
        "✏️ Editar / Actualizar"
    ])

    telas = db.obtener_telas()

    # --- PESTAÑA 1: CATÁLOGO Y PRECIOS DE TELAS ---
    with tab_telas_catalogo:
        if telas:
            col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
            col_kpi1.metric("Total de Telas", f"{len(telas)}")
            prom_kilo = sum(t.precio_kilo for t in telas) / len(telas)
            col_kpi2.metric("Precio Promedio / Kg", f"${prom_kilo:,.2f}")
            prom_metro = sum(t.precio_metro for t in telas) / len(telas)
            col_kpi3.metric("Costo Promedio / Metro", f"${prom_metro:,.2f}")

            filtro_tela = st.text_input("Buscar tela...", placeholder="Filtrar por nombre...", key="filtro_telas_cat")
            telas_mostradas = [t for t in telas if filtro_tela.lower() in t.nombre.lower()] if filtro_tela else telas

            tabla_telas = [{
                "Nombre": t.nombre, 
                "Precio/Kg": f"${t.precio_kilo:,.2f}", 
                "Rendimiento (m/kg)": f"{t.rendimiento:.2f}",
                "Costo/Metro": f"${t.precio_metro:,.2f}"
            } for t in telas_mostradas]
            st.dataframe(tabla_telas, width="stretch")
        else:
            st.info("No hay telas cargadas todavía en el catálogo.")

    # --- PESTAÑA 2: NUEVA TELA ---
    with tab_telas_nueva:
        st.subheader("Cargar Nueva Tela")
        with st.form("form_nueva_tela"):
            col_nt1, col_nt2 = st.columns(2)
            with col_nt1:
                nombre = st.text_input("Nombre de la tela", placeholder="Ej: Jersey 24/1 Peinado")
                precio = st.number_input("Precio por Kilo ($)", min_value=0.0, step=500.0, value=15000.0)
            with col_nt2:
                rendimiento = st.number_input("Rendimiento (metros por kilo)", min_value=0.1, step=0.1, value=3.0)

            costo_metro_est = precio / rendimiento if rendimiento > 0 else 0.0
            st.info(f"💡 **Costo estimado por metro:** ${costo_metro_est:,.2f}")

            if st.form_submit_button("➕ Guardar Tela", type="primary"):
                if not nombre.strip():
                    st.error("Por favor, ingresá un nombre para la tela.")
                else:
                    db.agregar_tela(nombre.strip(), precio, rendimiento)
                    st.success(f"Tela '{nombre.strip()}' guardada exitosamente.")
                    st.rerun()

    # --- PESTAÑA 3: EDITAR / ACTUALIZAR TELA ---
    with tab_telas_editar:
        st.subheader("Editar o Modificar Tela Existente")
        if not telas:
            st.warning("No hay telas disponibles para editar.")
        else:
            tela_a_editar = st.selectbox(
                "Seleccionar Tela para Modificar", 
                telas, 
                format_func=lambda x: f"{x.nombre} (${x.precio_kilo:,.2f}/kg - Rend: {x.rendimiento} m)"
            )
            
            with st.form("form_editar_tela"):
                col_et1, col_et2 = st.columns(2)
                with col_et1:
                    edit_nombre = st.text_input("Nombre de la tela", value=tela_a_editar.nombre)
                    edit_precio = st.number_input("Precio por Kilo ($)", min_value=0.0, step=500.0, value=float(tela_a_editar.precio_kilo))
                with col_et2:
                    edit_rendimiento = st.number_input("Rendimiento (metros por kilo)", min_value=0.1, step=0.1, value=float(tela_a_editar.rendimiento))

                nuevo_costo_m = edit_precio / edit_rendimiento if edit_rendimiento > 0 else 0.0
                st.info(f"💡 **Nuevo costo resultante por metro:** ${nuevo_costo_m:,.2f}")

                col_b1, col_b2 = st.columns([2, 1])
                with col_b1:
                    if st.form_submit_button("💾 Guardar Cambios en la Tela", type="primary"):
                        if not edit_nombre.strip():
                            st.error("El nombre no puede estar vacío.")
                        else:
                            db.actualizar_tela(tela_a_editar.id, edit_nombre.strip(), edit_precio, edit_rendimiento)
                            st.success(f"Tela '{edit_nombre.strip()}' actualizada correctamente.")
                            st.rerun()
                with col_b2:
                    if st.form_submit_button("🗑️ Eliminar Tela"):
                        db.eliminar_tela(tela_a_editar.id)
                        st.success(f"Tela eliminada del catálogo.")
                        st.rerun()


# --- 5. MÓDULO: CONFIGURACIÓN GENERAL ---
elif opcion == "Configuración General":
    st.title("⚙️ Configuración General")
    st.caption("Valores globales del negocio. Al modificarlos, los precios de venta y costos de estampado de todo el catálogo se recalculan automáticamente.")
    
    config_actual = db.obtener_configuracion()
    
    with st.form("form_config"):
        st.subheader("1. Ganancia y Costo Fijo")
        col1, col2 = st.columns(2)
        with col1:
            nuevo_mult = st.number_input("Multiplicador Global (Ganancia)", value=float(config_actual["multiplicador"]), step=0.1)
        with col2:
            nuevo_fijo = st.number_input("Costo Fijo Base por Prenda ($)", value=float(config_actual["costo_fijo"]), step=500.0)
            
        st.subheader("2. Precios de Técnicas de Estampado")
        col3, col4, col5 = st.columns(3)
        with col3:
            nuevo_dtf = st.number_input("DTF ($ por metro)", value=float(config_actual.get("precio_metro_dtf", 0.0)), min_value=0.0, step=500.0)
        with col4:
            nuevo_sub = st.number_input("Sublimación ($ por metro)", value=float(config_actual.get("precio_metro_sublimacion", 0.0)), min_value=0.0, step=500.0)
        with col5:
            nuevo_seri = st.number_input("Serigrafía ($ por unidad/estampa)", value=float(config_actual.get("precio_unidad_serigrafia", 0.0)), min_value=0.0, step=500.0)

        st.subheader("3. Observaciones y Condiciones para los PDFs")
        nueva_desc_pdf = st.text_area(
            "Texto al pie del presupuesto (Observaciones, Validez, Formas de pago)",
            value=config_actual.get("descripcion_pdf", "Presupuesto válido por 15 días corridos a partir de la fecha de emisión. Precios sujetos a variación de insumos."),
            height=90,
            help="Este texto se incluirá al final de todos los presupuestos emitidos en formato PDF."
        )

        if st.form_submit_button("Actualizar Valores", type="primary"):
            db.actualizar_configuracion(nuevo_fijo, nuevo_mult, nuevo_dtf, nuevo_sub, nuevo_seri, nueva_desc_pdf.strip())
            st.success("Configuración actualizada correctamente.")
            st.rerun()


# --- 6. MÓDULO: GENERADOR DE PRESUPUESTOS (SECUNDARIO) ---
elif opcion == "Generador de Presupuestos":
    st.title("🛒 Generador de Presupuestos")
    st.caption("Herramienta comercial para cotizar pedidos a clientes y consultar el historial de cotizaciones.")

    tab_nuevo_p, tab_historial_p = st.tabs(["🛒 Nuevo Presupuesto", "📂 Presupuestos Guardados"])

    productos = db.obtener_productos()

    # --- PESTAÑA 1: NUEVO PRESUPUESTO ---
    with tab_nuevo_p:
        if "carrito" not in st.session_state:
            st.session_state.carrito = []

        if not productos:
            st.warning("⚠️ No hay productos cargados en el catálogo para presupuestar.")
        else:
            st.subheader("1. Seleccionar Prenda del Catálogo")
            col1, col2 = st.columns([3, 1])
            with col1:
                prod_sel = st.selectbox("Prenda", productos, format_func=lambda p: f"{p.nombre} (Tela: {p.tela.nombre})")
            with col2:
                cantidad = st.number_input("Cantidad", min_value=1, step=1, value=10)

            # Detalles del producto seleccionado (costo y precio catálogo sugerido)
            c_estampado_unit = prod_sel.costo_estampado(config_obj)
            c_prod_unit = prod_sel.costo_produccion(config_obj)
            p_venta_unit = prod_sel.precio_venta(config_obj)

            with st.container(border=True):
                col_d1, col_d2, col_d3 = st.columns(3)
                col_d1.metric("Prenda Seleccionada", prod_sel.nombre)
                col_d2.metric("Tela", prod_sel.tela.nombre)
                col_d3.metric("Precio Venta Catálogo C/U", f"${p_venta_unit:,.2f}")

            if st.button("➕ Agregar al Pedido", type="secondary"):
                nuevo_item = ItemPresupuesto(
                    producto=prod_sel, 
                    cantidad=cantidad,
                    costo_estampado=c_estampado_unit
                )
                st.session_state.carrito.append(nuevo_item)
                st.success(f"Agregado: {cantidad}x {prod_sel.nombre}")
                st.rerun()

            if len(st.session_state.carrito) > 0:
                st.divider()
                st.subheader("2. Ajustes de Cobro del Presupuesto")
                
                col_aj1, col_aj2, col_aj3 = st.columns(3)
                with col_aj1:
                    cliente_ref = st.text_input("Nombre del Cliente")
                with col_aj2:
                    multiplicador = st.number_input("Multiplicador", value=float(config_obj.multiplicador_default), step=0.1)
                with col_aj3:
                    costo_fijo = st.number_input("Costo Fijo por prenda ($)", value=float(config_obj.costo_fijo_base), step=500.0)

                presupuesto_actual = Presupuesto(
                    cliente=cliente_ref, 
                    items=st.session_state.carrito,
                    config=config_obj,
                    multiplicador_usado=multiplicador,
                    costo_fijo_usado=costo_fijo
                )

                st.subheader("3. Detalle Final del Pedido")
                tabla_visual = [{
                    "Prenda": item.producto.nombre,
                    "Cantidad": item.cantidad,
                    "Precio Unitario": f"${presupuesto_actual.precio_unitario_final(item):,.2f}",
                    "Total Renglón": f"${presupuesto_actual.subtotal_final(item):,.2f}"
                } for item in st.session_state.carrito]
                
                st.dataframe(tabla_visual, width="stretch")

                st.metric("TOTAL A COBRAR AL CLIENTE", f"${presupuesto_actual.total_final:,.2f}")

                # Generar PDF del presupuesto actual (marca SIMPLE, sin estampados, con observaciones)
                pdf_data = generar_pdf_presupuesto(presupuesto_actual, descripcion_pdf=config_obj.descripcion_pdf)
                nombre_cliente_limpio = (cliente_ref.strip() or "Cliente").replace(" ", "_")
                nombre_archivo_pdf = f"Presupuesto_SIMPLE_{nombre_cliente_limpio}_{datetime.now().strftime('%Y%m%d')}.pdf"

                col_btn1, col_btn2, col_btn3 = st.columns([1, 1.5, 2])
                with col_btn1:
                    if st.button("Vaciar Carrito"):
                        st.session_state.carrito.clear()
                        st.rerun()
                with col_btn2:
                    st.download_button(
                        label="📄 Exportar a PDF",
                        data=pdf_data,
                        file_name=nombre_archivo_pdf,
                        mime="application/pdf"
                    )
                with col_btn3:
                    if st.button("💾 Guardar Presupuesto", type="primary"):
                        if not cliente_ref:
                            st.error("Por favor, ingresá el nombre del cliente.")
                        else:
                            db.guardar_presupuesto(presupuesto_actual)
                            st.session_state.carrito.clear()
                            st.success("¡Presupuesto guardado exitosamente en el historial!")
                            st.rerun()

    # --- PESTAÑA 2: HISTORIAL DE PRESUPUESTOS GUARDADOS ---
    with tab_historial_p:
        st.subheader("Historial de Cotizaciones Emitidas")
        presupuestos_guardados = db.obtener_presupuestos()

        if not presupuestos_guardados:
            st.info("Aún no hay presupuestos guardados en el sistema.")
        else:
            filtro_cliente = st.text_input("Buscar por cliente...", placeholder="Nombre del cliente...", key="filtro_hist_p")
            
            p_filtrados = [
                p for p in presupuestos_guardados 
                if filtro_cliente.lower() in (p.get("cliente_referencia") or "").lower()
            ] if filtro_cliente else presupuestos_guardados

            st.write(f"Mostrando **{len(p_filtrados)}** presupuestos guardados:")

            for p in p_filtrados:
                fecha_raw = p.get("created_at") or ""
                try:
                    fecha_dt = datetime.fromisoformat(fecha_raw.replace("Z", "+00:00"))
                    fecha_formateada = fecha_dt.strftime("%d/%m/%Y %H:%M")
                    fecha_corta = fecha_dt.strftime("%d/%m/%Y")
                except Exception:
                    fecha_formateada = fecha_raw[:10]
                    fecha_corta = fecha_raw[:10]

                cliente_nombre = p.get("cliente_referencia") or "Sin nombre"
                total_p = float(p.get("precio_total") or 0.0)

                with st.expander(f"📄 #{p['id']} - {cliente_nombre} | Total: ${total_p:,.2f} | Fecha: {fecha_formateada}"):
                    detalles = db.obtener_detalles_presupuesto(p["id"])
                    
                    if not detalles:
                        st.caption("No se encontraron detalles para este presupuesto.")
                    else:
                        items_tabla = []
                        items_para_pdf = []
                        total_prendas_guardadas = 0

                        for d in detalles:
                            p_info = d.get("productos") or {}
                            nombre_p = p_info.get("nombre") or f"Producto #{d.get('producto_id')}"
                            cant = int(d.get("cantidad") or 0)
                            total_prendas_guardadas += cant
                            p_unit = float(d.get("precio_unitario") or 0.0)
                            subt = cant * p_unit

                            items_tabla.append({
                                "Prenda": nombre_p,
                                "Cantidad": cant,
                                "Precio Unitario": f"${p_unit:,.2f}",
                                "Subtotal": f"${subt:,.2f}"
                            })

                            items_para_pdf.append({
                                "nombre": nombre_p,
                                "cantidad": cant,
                                "precio_unitario": p_unit,
                                "subtotal": subt
                            })

                        st.dataframe(items_tabla, width="stretch")

                        col_hp1, col_hp2, col_hp3 = st.columns([2, 1.5, 1])
                        with col_hp1:
                            st.write(f"**Prendas totales:** {total_prendas_guardadas} u. | **Total:** ${total_p:,.2f}")
                        with col_hp2:
                            pdf_historial_bytes = generar_pdf_presupuesto(
                                presupuesto_o_cliente=cliente_nombre,
                                items=items_para_pdf,
                                total=total_p,
                                fecha=fecha_corta,
                                descripcion_pdf=config_obj.descripcion_pdf
                            )
                            cli_clean = cliente_nombre.replace(" ", "_")
                            st.download_button(
                                label="📄 Descargar PDF",
                                data=pdf_historial_bytes,
                                file_name=f"Presupuesto_SIMPLE_{cli_clean}_{p['id']}.pdf",
                                mime="application/pdf",
                                key=f"btn_pdf_hist_{p['id']}"
                            )
                        with col_hp3:
                            if st.button("🗑️ Eliminar", key=f"btn_del_p_{p['id']}", type="secondary"):
                                db.eliminar_presupuesto(p["id"])
                                st.success("Presupuesto eliminado.")
                                st.rerun()