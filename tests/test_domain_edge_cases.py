import math
import pytest
from core import Config, Database, ItemPresupuesto, Presupuesto, Producto, Tela, normalizar_texto, seguro_float


class TestDomainEdgeCases:
    def test_seguro_float_casos_borde(self):
        assert seguro_float(None, 5.0) == 5.0
        assert seguro_float("", 3.0) == 3.0
        assert seguro_float("no-es-numero", 1.5) == 1.5
        assert seguro_float(0, 10.0) == 0.0
        assert seguro_float("  42.5  ", 0.0) == 42.5
        assert seguro_float("-12.3", 0.0) == -12.3
        assert seguro_float(float("nan"), 2.0) == 2.0
        assert seguro_float(float("inf"), 2.0) == 2.0
        assert seguro_float(float("-inf"), 2.0) == 2.0

    def test_normalizar_texto_espacios_y_tildes(self):
        assert normalizar_texto("  ALGODÓN  ") == "algodon"
        assert normalizar_texto("Corte + Sublimado") == "corte + sublimado"
        assert normalizar_texto("BORDADO") == "bordado"
        assert normalizar_texto("") == ""
        assert normalizar_texto(None) == ""

    def test_tela_rendimiento_cero_o_negativo(self):
        # Rendimiento cero debe devolver 0.0 sin levantar ZeroDivisionError
        tela_cero = Tela(id=1, nombre="Tela Cero", precio_kilo=15000.0, rendimiento=0.0)
        assert tela_cero.precio_metro == 0.0

        # Rendimiento negativo: la lógica de dominio no debería generar precios negativos por metro
        tela_negativa = Tela(id=2, nombre="Tela Negativa", precio_kilo=15000.0, rendimiento=-2.0)
        assert tela_negativa.precio_metro <= 0.0

    def test_producto_sin_telas_secundarias(self):
        tela = Tela(id=1, nombre="Jersey", precio_kilo=9000.0, rendimiento=3.0)  # metro: 3000
        prod = Producto(
            id=1,
            nombre="Remera",
            tela=tela,
            consumo_metros=1.0,
            costo_confeccion=1500.0,
            costo_avio=200.0,
            tela_secundaria=None,
            consumo_metros_secundaria=0.5,  # tiene consumo pero no tela
        )
        assert prod.costo_tela_secundaria == 0.0
        assert prod.costo_tela == 3000.0
        assert prod.costo_base == 4700.0

    def test_producto_con_tela_secundaria_consumo_cero_o_negativo(self):
        tela1 = Tela(id=1, nombre="Jersey", precio_kilo=9000.0, rendimiento=3.0)
        tela2 = Tela(id=2, nombre="Rib", precio_kilo=12000.0, rendimiento=2.0)
        prod = Producto(
            id=2,
            nombre="Buzo",
            tela=tela1,
            consumo_metros=1.5,
            costo_confeccion=2500.0,
            tela_secundaria=tela2,
            consumo_metros_secundaria=0.0,
        )
        assert prod.costo_tela_secundaria == 0.0

        prod.consumo_metros_secundaria = -0.2
        assert prod.costo_tela_secundaria == 0.0

    def test_costo_estampado_tipos_desconocidos_o_vacios(self):
        cfg = Config(
            precio_metro_dtf=8000.0,
            precio_metro_sublimacion=2500.0,
            precio_unidad_serigrafia=1200.0,
            precio_unidad_bordado=2000.0,
            precios_estampado={"dtf": 8000.0, "sublimacion": 2500.0, "serigrafia": 1200.0, "bordado": 2000.0},
        )
        tela = Tela(id=1, nombre="Piqué", precio_kilo=10000.0, rendimiento=2.5)
        prod = Producto(
            id=10,
            nombre="Chomba",
            tela=tela,
            consumo_metros=1.0,
            costo_confeccion=3000.0,
            tipo_estampado="Estampado Inexistente",
            consumo_estampado=1.0,
        )
        # Tipo no registrado debe costar 0.0 sin romper
        assert prod.costo_estampado(cfg) == 0.0

        # Tipo None o vacío
        prod.tipo_estampado = None
        assert prod.costo_estampado(cfg) == 0.0
        prod.tipo_estampado = ""
        assert prod.costo_estampado(cfg) == 0.0
        prod.tipo_estampado = "Ninguno"
        assert prod.costo_estampado(cfg) == 0.0

        # Consumo negativo o cero
        prod.tipo_estampado = "DTF"
        prod.consumo_estampado = 0.0
        assert prod.costo_estampado(cfg) == 0.0
        prod.consumo_estampado = -1.5
        assert prod.costo_estampado(cfg) == 0.0

    def test_costo_estampado_normalizacion_de_clave(self):
        cfg = Config(precios_estampado={"serigrafia": 1500.0, "corte + sublimado": 4000.0})
        tela = Tela(id=1, nombre="Tela", precio_kilo=1000.0, rendimiento=1.0)
        prod = Producto(
            id=1,
            nombre="P1",
            tela=tela,
            consumo_metros=1.0,
            costo_confeccion=1000.0,
            tipo_estampado="  SERIGRAFÍA  ",
            consumo_estampado=2.0,
        )
        # Debe normalizar acentos y espacios
        assert prod.costo_estampado(cfg) == 3000.0

        prod.tipo_estampado = "Corte + Sublimado"
        prod.consumo_estampado = 1.0
        assert prod.costo_estampado(cfg) == 4000.0

    def test_presupuesto_sin_items(self):
        cfg = Config(costo_fijo_base=5000.0, multiplicador_default=2.0)
        presupuesto = Presupuesto(cliente="Cliente Vacio", items=[], config=cfg)
        assert presupuesto.total_final == 0.0

    def test_presupuesto_cantidad_cero(self):
        cfg = Config(costo_fijo_base=5000.0, multiplicador_default=2.0)
        tela = Tela(id=1, nombre="T", precio_kilo=10000.0, rendimiento=2.0)  # metro: 5000
        prod = Producto(id=1, nombre="P", tela=tela, consumo_metros=1.0, costo_confeccion=2000.0)  # base: 7000
        item = ItemPresupuesto(producto=prod, cantidad=0)
        presupuesto = Presupuesto(cliente="Cliente", items=[item], config=cfg)

        # Precio unitario existe según fórmula, pero el subtotal y total deben ser 0
        assert presupuesto.subtotal_final(item) == 0.0
        assert presupuesto.total_final == 0.0

    def test_presupuesto_multiplicador_default_y_overrides(self):
        cfg = Config(costo_fijo_base=4000.0, multiplicador_default=2.5)
        tela = Tela(id=1, nombre="T", precio_kilo=6000.0, rendimiento=2.0)  # 3000
        prod = Producto(id=1, nombre="P", tela=tela, consumo_metros=1.0, costo_confeccion=1000.0)  # base: 4000
        item = ItemPresupuesto(producto=prod, cantidad=1)

        # Caso default: multiplicador = 2.5, costo fijo = 4000 => (4000 * 2.5) + 4000 = 14000
        p1 = Presupuesto(cliente="C1", items=[item], config=cfg)
        assert p1.multiplicador_usado == 2.5
        assert p1.costo_fijo_usado == 4000.0
        assert p1.precio_unitario_final(item) == 14000.0
        assert p1.total_final == 14000.0

        # Caso con override explícito
        p2 = Presupuesto(cliente="C2", items=[item], config=cfg, multiplicador_usado=3.0, costo_fijo_usado=0.0)
        assert p2.precio_unitario_final(item) == 12000.0
        assert p2.total_final == 12000.0

    def test_presupuesto_compatibilidad_multiplicador_bigint(self):
        # Si desde la base de datos viene como entero (ej: 2 en lugar de 2.0 o redondeado)
        cfg = Config(costo_fijo_base=0.0)
        tela = Tela(id=1, nombre="T", precio_kilo=1000.0, rendimiento=1.0)
        prod = Producto(id=1, nombre="P", tela=tela, consumo_metros=1.0, costo_confeccion=0.0)
        item = ItemPresupuesto(producto=prod, cantidad=1)

        p = Presupuesto(cliente="C", items=[item], config=cfg, multiplicador_usado=2)
        assert p.precio_unitario_final(item) == 2000.0
