import math
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.strategies import (
    st_config,
    st_item_presupuesto,
    st_presupuesto,
    st_producto,
    st_tela,
    st_monto,
    st_consumo,
    st_multiplicador,
    st_cantidad,
)
from core import Presupuesto, ItemPresupuesto, Producto


class TestDomainHypothesis:
    @given(st_presupuesto())
    def test_invariante_suma_subtotales_igual_a_total(self, presupuesto: Presupuesto):
        """El total final del presupuesto debe ser exactamente la suma de los subtotales de sus items."""
        subtotales = [presupuesto.subtotal_final(it) for it in presupuesto.items]
        suma_calculada = sum(subtotales)
        assert math.isclose(presupuesto.total_final, suma_calculada, rel_tol=1e-5, abs_tol=1e-5)

    @given(st_presupuesto())
    def test_invariante_no_negatividad(self, presupuesto: Presupuesto):
        """Con entradas no negativas, los precios y totales deben ser no negativos."""
        for item in presupuesto.items:
            unitario = presupuesto.precio_unitario_final(item)
            subtotal = presupuesto.subtotal_final(item)
            assert unitario >= 0.0, f"Precio unitario negativo: {unitario}"
            assert subtotal >= 0.0, f"Subtotal negativo: {subtotal}"
        assert presupuesto.total_final >= 0.0

    @given(st_item_presupuesto(), st_config(), st_multiplicador, st_monto)
    def test_invariante_cantidad_cero_da_subtotal_cero(self, item: ItemPresupuesto, config, mult, costo_fijo):
        """Si la cantidad es 0, el subtotal debe ser siempre 0.0 sin importar los costos."""
        item.cantidad = 0
        presupuesto = Presupuesto(
            cliente="Test",
            items=[item],
            config=config,
            multiplicador_usado=mult,
            costo_fijo_usado=costo_fijo,
        )
        assert presupuesto.subtotal_final(item) == 0.0
        assert presupuesto.total_final == 0.0

    @given(st_producto(), st_config(), st_monto)
    def test_invariante_monotonicidad_de_confeccion(self, producto: Producto, config, delta_costo):
        """Aumentar el costo de confección debe incrementar el costo base y precio de venta de forma estrictamente monótona."""
        costo_base_inicial = producto.costo_base
        precio_venta_inicial = producto.precio_venta(config)

        producto.costo_confeccion += delta_costo

        assert producto.costo_base >= costo_base_inicial
        assert producto.precio_venta(config) >= precio_venta_inicial

    @given(st_item_presupuesto(), st_config(), st_multiplicador, st_monto, st_cantidad, st_cantidad)
    def test_invariante_linealidad_de_subtotal(self, item: ItemPresupuesto, config, mult, costo_fijo, q1, q2):
        """El subtotal debe ser lineal con respecto a la cantidad: subtotal(q1) + subtotal(q2) == subtotal(q1 + q2)."""
        presupuesto = Presupuesto(
            cliente="Test",
            items=[item],
            config=config,
            multiplicador_usado=mult,
            costo_fijo_usado=costo_fijo,
        )
        item.cantidad = q1
        sub1 = presupuesto.subtotal_final(item)

        item.cantidad = q2
        sub2 = presupuesto.subtotal_final(item)

        item.cantidad = q1 + q2
        sub_total = presupuesto.subtotal_final(item)

        assert math.isclose(sub1 + sub2, sub_total, rel_tol=1e-5, abs_tol=1e-5)
