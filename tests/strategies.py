from hypothesis import strategies as st
from core import Config, Tela, Producto, ItemPresupuesto, Presupuesto

# Strings realistas y con casos borde (espacios, tildes, caracteres especiales)
st_nombre = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=80)
st_desc = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=300)

# Montos monetarios y consumos financieros finitos no negativos
st_monto = st.floats(min_value=0.0, max_value=1e7, allow_nan=False, allow_infinity=False)
st_consumo = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
st_rendimiento = st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False)
st_cantidad = st.integers(min_value=0, max_value=10000)
st_multiplicador = st.floats(min_value=0.5, max_value=20.0, allow_nan=False, allow_infinity=False)

st_tipo_estampado = st.sampled_from(["Ninguno", "DTF", "Sublimacion", "Serigrafia", "Bordado", "Corte + Sublimado", "Desconocido", "", "   "])

@st.composite
def st_tela(draw):
    return Tela(
        id=draw(st.integers(min_value=1, max_value=100000)),
        nombre=draw(st_nombre),
        precio_kilo=draw(st_monto),
        rendimiento=draw(st_rendimiento),
        descripcion=draw(st_desc),
        activo=draw(st.booleans()),
    )

@st.composite
def st_config(draw):
    return Config(
        costo_fijo_base=draw(st_monto),
        multiplicador_default=draw(st_multiplicador),
        precio_metro_dtf=draw(st_monto),
        precio_metro_sublimacion=draw(st_monto),
        precio_unidad_serigrafia=draw(st_monto),
        precio_unidad_bordado=draw(st_monto),
        descripcion_pdf=draw(st_desc),
        precios_estampado={
            "dtf": draw(st_monto),
            "sublimacion": draw(st_monto),
            "serigrafia": draw(st_monto),
            "bordado": draw(st_monto),
            "corte + sublimado": draw(st_monto),
        },
    )

@st.composite
def st_producto(draw, tela_strategy=None):
    tela_strat = tela_strategy or st_tela()
    tela = draw(tela_strat)
    usa_secundaria = draw(st.booleans())
    tela_sec = draw(tela_strat) if usa_secundaria else None
    
    return Producto(
        id=draw(st.integers(min_value=1, max_value=100000)),
        nombre=draw(st_nombre),
        tela=tela,
        consumo_metros=draw(st_consumo),
        costo_confeccion=draw(st_monto),
        tipo_estampado=draw(st_tipo_estampado),
        consumo_estampado=draw(st_consumo),
        nombre_avio=draw(st_nombre),
        costo_avio=draw(st_monto),
        activo=draw(st.booleans()),
        tela_secundaria=tela_sec,
        consumo_metros_secundaria=draw(st_consumo) if usa_secundaria else 0.0,
    )

@st.composite
def st_item_presupuesto(draw, producto_strategy=None):
    prod_strat = producto_strategy or st_producto()
    return ItemPresupuesto(
        producto=draw(prod_strat),
        cantidad=draw(st_cantidad),
        detalle_estampado=draw(st_desc),
        costo_estampado=draw(st_monto),
    )

@st.composite
def st_presupuesto(draw):
    config = draw(st_config())
    items = draw(st.lists(st_item_presupuesto(), min_size=0, max_size=10))
    custom_mult = draw(st.one_of(st.none(), st_multiplicador))
    custom_costo_fijo = draw(st.one_of(st.none(), st_monto))
    return Presupuesto(
        cliente=draw(st_nombre),
        items=items,
        config=config,
        multiplicador_usado=custom_mult,
        costo_fijo_usado=custom_costo_fijo,
        descripcion_pdf=draw(st_desc),
    )
