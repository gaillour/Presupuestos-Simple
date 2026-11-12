import pytest
from core import Config, ItemPresupuesto, Presupuesto, Producto, Tela, generar_pdf_presupuesto


class TestPdfRobustness:
    @pytest.fixture
    def presupuesto_basico(self):
        cfg = Config(costo_fijo_base=5000.0, multiplicador_default=2.0)
        tela = Tela(id=1, nombre="Algodón 24/1", precio_kilo=12000.0, rendimiento=3.0)
        prod = Producto(id=1, nombre="Remera Regular", tela=tela, consumo_metros=0.8, costo_confeccion=2000.0)
        item = ItemPresupuesto(producto=prod, cantidad=10)
        return Presupuesto(cliente="Juan Pérez", items=[item], config=cfg)

    def test_pdf_con_objeto_presupuesto_valido(self, presupuesto_basico):
        pdf_bytes = generar_pdf_presupuesto(presupuesto_basico)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 500

    def test_pdf_con_items_en_formato_dict(self):
        items = [
            {"nombre": "Buzo Canguro", "cantidad": 5, "precio_unitario": 25000.0, "subtotal": 125000.0},
            {"nombre": "Pantalón Jogger", "cantidad": 2, "precio_unitario": 30000.0, "subtotal": 60000.0},
        ]
        pdf_bytes = generar_pdf_presupuesto("Cliente Dict", items=items, total=185000.0)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_pdf_con_lista_de_items_vacia(self):
        # Debe generar un PDF válido sin ítems sin arrojar IndexError ni ZeroDivisionError
        pdf_bytes = generar_pdf_presupuesto("Cliente Sin Compras", items=[], total=0.0)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_pdf_con_cliente_vacio_o_none(self):
        pdf_bytes = generar_pdf_presupuesto(None, items=[], total=0.0)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_pdf_descripcion_extensa_multilinea(self, presupuesto_basico):
        # Párrafo largo que fuerza múltiples líneas y posible salto de página
        descripcion_larga = (
            "Condición comercial especial: Se requiere una seña del 50% al momento de confirmar el pedido.\n"
            "El saldo restante se cancela contra entrega de la mercadería confeccionada.\n"
            + "Texto de relleno para verificar desborde de márgenes: " * 20
        )
        pdf_bytes = generar_pdf_presupuesto(presupuesto_basico, descripcion_pdf=descripcion_larga)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_pdf_caracteres_latinos_y_tildes(self):
        # Caracteres habituales en español (ñ, tildes, comillas)
        items = [
            {"nombre": "Diseño Especial en Algodón & Piña (Edición 2026)", "cantidad": 1, "precio_unitario": 1000.0, "subtotal": 1000.0}
        ]
        pdf_bytes = generar_pdf_presupuesto(
            "Señor José María Peña",
            items=items,
            total=1000.0,
            descripcion_pdf="Garantía de confección válida por 60 días.",
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_pdf_items_con_claves_faltantes_o_tipos_inesperados(self):
        # Dicts degradados donde faltan campos o vienen tipos sucios
        items_sucios = [
            {"nombre": "Item Sin Precio"},
            {"cantidad": "3", "subtotal": "1500"},
            {"nombre": None, "cantidad": 0, "precio_unitario": 0, "subtotal": 0},
        ]
        pdf_bytes = generar_pdf_presupuesto("Cliente Resiliente", items=items_sucios, total=1500.0)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_pdf_caracteres_fuera_de_latin1_o_emojis(self):
        # Fuzzing de caracteres especiales que suelen crashear fuentes standard como Helvetica
        items = [{"nombre": "Remera Estampada 👕 ✨ 🔥", "cantidad": 2, "precio_unitario": 5000.0, "subtotal": 10000.0}]
        pdf_bytes = generar_pdf_presupuesto("Cliente Con Emojis 😊", items=items, total=10000.0)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

