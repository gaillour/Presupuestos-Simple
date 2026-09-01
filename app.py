import streamlit as st
from core import Database, ItemPresupuesto, Presupuesto

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Sistema de Presupuestos", layout="wide")

@st.cache_resource
def get_db():
    return Database()

db = get_db()

# --- 2. NAVEGACIÓN ---
st.sidebar.title("Navegación")
opcion = st.sidebar.radio(
    "Seleccioná un módulo:", 
    ["Generar Presupuesto", "Catálogo de Telas", "Catálogo de Productos", "Configuración"]
)

# --- 3. MÓDULO: GENERAR PRESUPUESTO ---
if opcion == "Generar Presupuesto":
    st.title("🛒 Nuevo Presupuesto")

    if "carrito" not in st.session_state:
        st.session_state.carrito = []

    productos = db.obtener_productos()
    config_actual = db.obtener_configuracion()

    if not productos:
        st.warning("⚠️ No hay productos cargados para presupuestar.")
    else:
        st.subheader("1. Agregar Prendas")
        col1, col2 = st.columns([3, 1])
        with col1:
            prod_sel = st.selectbox("Producto Base", productos, format_func=lambda p: p.nombre)
        with col2:
            cantidad = st.number_input("Cantidad de prendas", min_value=1, step=1, value=10)
        
        st.write("🎨 **Detalle de Estampado**")
        tecnica_opciones = ["Ninguno", "Sublimación (por metro)", "DTF (por metro)", "Serigrafía (por unidad)", "Personalizado"]
        tecnica_sel = st.selectbox("Técnica de Estampado", tecnica_opciones)

        costo_est = 0.0
        detalle_est = "Sin estampado"

        if tecnica_sel == "Ninguno":
            costo_est = 0.0
            detalle_est = "Sin estampado"
            st.caption("No se aplica costo de estampado a este ítem.")
            
        elif tecnica_sel == "Sublimación (por metro)":
            precio_metro = float(config_actual.get("precio_metro_sublimacion", 0.0))
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                metros_sub = st.number_input("Metros de Sublimación para el lote", min_value=0.01, value=1.0, step=0.1)
            with col_s2:
                costo_total_est = metros_sub * precio_metro
                costo_est = costo_total_est / cantidad if cantidad > 0 else 0.0
                st.info(f"Precio por metro: **${precio_metro:,.2f}**")
            detalle_est = f"Sublimación ({metros_sub} m para {cantidad} prendas)"

        elif tecnica_sel == "DTF (por metro)":
            precio_metro = float(config_actual.get("precio_metro_dtf", 0.0))
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                metros_dtf = st.number_input("Metros de DTF para el lote", min_value=0.01, value=1.0, step=0.1)
            with col_d2:
                costo_total_est = metros_dtf * precio_metro
                costo_est = costo_total_est / cantidad if cantidad > 0 else 0.0
                st.info(f"Precio por metro: **${precio_metro:,.2f}**")
            detalle_est = f"DTF ({metros_dtf} m para {cantidad} prendas)"

        elif tecnica_sel == "Serigrafía (por unidad)":
            precio_unidad = float(config_actual.get("precio_unidad_serigrafia", 0.0))
            col_se1, col_se2 = st.columns(2)
            with col_se1:
                unidades_seri = st.number_input("Total de unidades/estampas de Serigrafía", min_value=1, value=int(cantidad), step=1)
            with col_se2:
                costo_total_est = unidades_seri * precio_unidad
                costo_est = costo_total_est / cantidad if cantidad > 0 else 0.0
                st.info(f"Precio por unidad: **${precio_unidad:,.2f}**")
            detalle_est = f"Serigrafía ({unidades_seri} u. para {cantidad} prendas)"

        elif tecnica_sel == "Personalizado":
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                desc_p = st.text_input("Descripción técnica", value="Estampado Especial")
            with col_p2:
                costo_est = st.number_input("Costo de estampado por prenda ($)", min_value=0.0, step=500.0, value=0.0)
            detalle_est = desc_p

        # Vista previa de costos unitarios
        costo_base_prenda = prod_sel.costo_base
        costo_prod_unitario = costo_base_prenda + costo_est
        estimado_unitario = (costo_prod_unitario * float(config_actual["multiplicador"])) + float(config_actual["costo_fijo"])

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Costo Prenda Base", f"${costo_base_prenda:,.2f}")
        col_m2.metric("Costo Estampado C/U", f"${costo_est:,.2f}")
        col_m3.metric("Costo Producción C/U", f"${costo_prod_unitario:,.2f}")
        col_m4.metric("Precio Venta Estimado C/U", f"${estimado_unitario:,.2f}")

        if st.button("➕ Agregar al Presupuesto", type="secondary"):
            nuevo_item = ItemPresupuesto(
                producto=prod_sel, 
                cantidad=cantidad,
                detalle_estampado=detalle_est,
                costo_estampado=costo_est
            )
            st.session_state.carrito.append(nuevo_item)
            st.success(f"Agregado: {cantidad}x {prod_sel.nombre}")
            st.rerun()

        if len(st.session_state.carrito) > 0:
            st.divider()
            st.subheader("2. Ajustes de Cobro")
            
            col_ajuste1, col_ajuste2, col_ajuste3 = st.columns(3)
            with col_ajuste1:
                cliente_ref = st.text_input("Nombre del Cliente")
            with col_ajuste2:
                multiplicador = st.number_input("Multiplicador", value=float(config_actual["multiplicador"]), step=0.1)
            with col_ajuste3:
                costo_fijo = st.number_input("Costo Fijo por prenda ($)", value=float(config_actual["costo_fijo"]), step=500.0)

            # Instanciamos el presupuesto para que calcule la matemática
            presupuesto_actual = Presupuesto(
                cliente=cliente_ref, 
                items=st.session_state.carrito,
                multiplicador_usado=multiplicador,
                costo_fijo_usado=costo_fijo
            )

            st.subheader("3. Detalle Final del Pedido")
            tabla_visual = [{
                "Prenda": item.producto.nombre,
                "Estampado": item.detalle_estampado if item.detalle_estampado else "Sin estampado",
                "Costo Estampado C/U": f"${item.costo_estampado:,.2f}",
                "Costo Producción C/U": f"${item.costo_base_unitario:,.2f}",
                "Precio Venta C/U": f"${presupuesto_actual.precio_unitario_final(item):,.2f}",
                "Cantidad": item.cantidad,
                "Total Renglón": f"${presupuesto_actual.subtotal_final(item):,.2f}"
            } for item in st.session_state.carrito]
            
            st.dataframe(tabla_visual, use_container_width=True)

            st.metric("TOTAL A COBRAR AL CLIENTE", f"${presupuesto_actual.total_final:,.2f}")

            col_btn1, col_btn2 = st.columns([1, 4])
            with col_btn1:
                if st.button("Vaciar Carrito"):
                    st.session_state.carrito.clear()
                    st.rerun()
            with col_btn2:
                if st.button("Guardar Presupuesto", type="primary"):
                    if not cliente_ref:
                        st.error("Por favor, ingresá el nombre del cliente.")
                    else:
                        db.guardar_presupuesto(presupuesto_actual)
                        st.session_state.carrito.clear()
                        st.success("¡Presupuesto guardado!")
                        st.rerun()


# --- 4. MÓDULO: TELAS ---
# --- 4. MÓDULO: TELAS ---
elif opcion == "Catálogo de Telas":
    st.title("🧵 Catálogo de Telas")
    
    telas = db.obtener_telas()
    if telas:
        tabla_telas = [{
            "Nombre": t.nombre, 
            "Precio/Kg": f"${t.precio_kilo:,.2f}", 
            "Rendimiento (m)": t.rendimiento,
            "Costo/Metro": f"${t.precio_metro:,.2f}"
        } for t in telas]
        st.dataframe(tabla_telas, use_container_width=True)
    else:
        st.info("No hay telas cargadas todavía.")
    
    col_izq, col_der = st.columns(2)
    
    with col_izq:
        st.subheader("Agregar Nueva Tela")
        with st.form("form_telas"):
            nombre = st.text_input("Nombre de la tela")
            precio = st.number_input("Precio por Kilo ($)", min_value=0.0, step=500.0)
            rendimiento = st.number_input("Rendimiento (metros/kilo)", min_value=0.1, step=0.1)
            
            if st.form_submit_button("Guardar Tela"):
                if nombre:
                    db.agregar_tela(nombre, precio, rendimiento)
                    st.success("Tela guardada.")
                    st.rerun()
                else:
                    st.error("Falta el nombre.")

    with col_der:
        st.subheader("Actualizar Precio")
        if telas:
            # Ponemos el selectbox AFUERA del formulario para que se actualice dinámicamente
            tela_a_editar = st.selectbox(
                "Seleccionar Tela", 
                telas, 
                format_func=lambda x: f"{x.nombre} (Actual: ${x.precio_kilo:,.2f})"
            )
            
            with st.form("form_actualizar_tela"):
                # Toma el precio actual de la tela seleccionada como valor por defecto
                nuevo_precio = st.number_input(
                    "Nuevo Precio por Kilo ($)", 
                    min_value=0.0, 
                    value=float(tela_a_editar.precio_kilo), 
                    step=500.0
                )
                
                if st.form_submit_button("Actualizar Precio"):
                    db.actualizar_precio_tela(tela_a_editar.id, nuevo_precio)
                    st.success(f"Precio actualizado a ${nuevo_precio:,.2f}")
                    st.rerun()

# --- 5. MÓDULO: PRODUCTOS ---
elif opcion == "Catálogo de Productos":
    st.title("👕 Catálogo de Productos")
    
    productos = db.obtener_productos()
    if productos:
        tabla_prod = [{
            "Prenda": p.nombre,
            "Tela": p.tela.nombre,
            "Consumo": f"{p.consumo_metros} m",
            "Costo Confección": f"${p.costo_confeccion:,.2f}"
        } for p in productos]
        st.dataframe(tabla_prod, use_container_width=True)
    
    st.divider()
    st.subheader("Crear Nuevo Producto")
    
    # Solo traemos telas y confección
    telas_db = db.obtener_telas()

    with st.form("form_productos"):
        nombre_prod = st.text_input("Nombre del Producto (Ej: Calza Larga)")
        tela_sel = st.selectbox("Tela", telas_db, format_func=lambda x: x.nombre)
        consumo = st.number_input("Consumo de tela (metros)", min_value=0.01, step=0.05)
# Adentro de with st.form("form_productos"):
        costo_conf = st.number_input("Costo de Confección ($)", min_value=0.0, step=500.0)

        if st.form_submit_button("Guardar Producto"):
            db.agregar_producto(nombre_prod, tela_sel.id, consumo, costo_conf)
            
# --- 6. MÓDULO: CONFIGURACIÓN GENERAL ---
elif opcion == "Configuración":
    st.title("⚙️ Configuración General")
    st.write("Acá definís los valores por defecto y precios de insumos/estampados para todos los presupuestos.")
    
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

        if st.form_submit_button("Actualizar Valores", type="primary"):
            db.actualizar_configuracion(nuevo_fijo, nuevo_mult, nuevo_dtf, nuevo_sub, nuevo_seri)
            st.success("Configuración actualizada correctamente.")
            st.rerun()