import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy-key")

from core import Config, Database, ItemPresupuesto, Presupuesto, Producto, Tela, normalizar_texto


class DummyResponse:
    def __init__(self, data):
        self.data = data


class TestCoreDomainMath(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            costo_fijo_base=6000.0,
            multiplicador_default=2.0,
            precio_metro_dtf=10000.0,
            precio_metro_sublimacion=3000.0,
            precio_unidad_serigrafia=1500.0,
            precio_unidad_bordado=2500.0,
            precios_estampado={
                "dtf": 10000.0,
                "sublimacion": 3000.0,
                "serigrafia": 1500.0,
                "bordado": 2500.0,
                "corte + sublimado": 4200.0,
            },
        )
        self.tela_algodon = Tela(id=1, nombre="Algodón 24/1", precio_kilo=12000.0, rendimiento=3.0)
        self.tela_lycra = Tela(id=2, nombre="Lycra", precio_kilo=16000.0, rendimiento=2.0)

    def test_tela_precio_metro_y_division_por_cero(self):
        self.assertAlmostEqual(self.tela_algodon.precio_metro, 4000.0)
        self.assertAlmostEqual(self.tela_lycra.precio_metro, 8000.0)
        tela_cero = Tela(id=3, nombre="Falla", precio_kilo=10000.0, rendimiento=0.0)
        self.assertEqual(tela_cero.precio_metro, 0.0)

    def test_producto_una_sola_tela_y_precio_venta(self):
        # Costo tela: 4000 * 0.8 = 3200
        # Costo base: 3200 + 2000 (confección) + 300 (avío) = 5500
        # Estampa DTF: 0.25m * 10000 = 2500
        # Precio venta: (5500 * 2.0) + 6000 + 2500 = 19500
        prod = Producto(
            id=10,
            nombre="Remera Básica",
            tela=self.tela_algodon,
            consumo_metros=0.8,
            costo_confeccion=2000.0,
            tipo_estampado="DTF",
            consumo_estampado=0.25,
            nombre_avio="Etiqueta",
            costo_avio=300.0,
        )
        self.assertAlmostEqual(prod.costo_tela_principal, 3200.0)
        self.assertAlmostEqual(prod.costo_tela_secundaria, 0.0)
        self.assertAlmostEqual(prod.costo_tela, 3200.0)
        self.assertAlmostEqual(prod.costo_base, 5500.0)
        self.assertAlmostEqual(prod.costo_estampado(self.config), 2500.0)
        self.assertAlmostEqual(prod.costo_produccion(self.config), 8000.0)
        self.assertAlmostEqual(prod.precio_venta(self.config), 19500.0)

    def test_producto_dos_telas_combinadas(self):
        # Tela 1 (Algodón): 4000 * 0.7 = 2800
        # Tela 2 (Lycra): 8000 * 0.25 = 2000
        # Costo tela total = 4800
        # Costo base = 4800 + 2200 (confección) + 0 (avío) = 7000
        # Técnica dinámica "Corte + Sublimado" (por unidad = 1): 1 * 4200 = 4200
        # Precio venta = (7000 * 2.0) + 6000 + 4200 = 24200
        prod = Producto(
            id=11,
            nombre="Remera Combinada Algodón + Lycra",
            tela=self.tela_algodon,
            consumo_metros=0.7,
            tela_secundaria=self.tela_lycra,
            consumo_metros_secundaria=0.25,
            costo_confeccion=2200.0,
            tipo_estampado="Corte + Sublimado",
            consumo_estampado=1.0,
        )
        self.assertAlmostEqual(prod.costo_tela_principal, 2800.0)
        self.assertAlmostEqual(prod.costo_tela_secundaria, 2000.0)
        self.assertAlmostEqual(prod.costo_tela, 4800.0)
        self.assertAlmostEqual(prod.costo_base, 7000.0)
        self.assertAlmostEqual(prod.costo_estampado(self.config), 4200.0)
        self.assertAlmostEqual(prod.precio_venta(self.config), 24200.0)

    def test_presupuesto_calculo_alineado_con_front(self):
        prod = Producto(
            id=11,
            nombre="Remera Combinada",
            tela=self.tela_algodon,
            consumo_metros=0.7,
            tela_secundaria=self.tela_lycra,
            consumo_metros_secundaria=0.25,
            costo_confeccion=2200.0,
            tipo_estampado="Corte + Sublimado",
            consumo_estampado=1.0,
        )
        item = ItemPresupuesto(
            producto=prod,
            cantidad=10,
            detalle_estampado="Corte + Sublimado",
            costo_estampado=prod.costo_estampado(self.config),
        )
        presupuesto = Presupuesto(
            cliente="Cliente Test",
            items=[item],
            config=self.config,
            multiplicador_usado=2.5,
            costo_fijo_usado=5000.0,
        )
        # Costo base = 7000; (7000 * 2.5) + 5000 + 4200 = 17500 + 5000 + 4200 = 26700
        self.assertAlmostEqual(presupuesto.precio_unitario_final(item), 26700.0)
        self.assertAlmostEqual(presupuesto.subtotal_final(item), 267000.0)
        self.assertAlmostEqual(presupuesto.total_final, 267000.0)


class TestDatabaseQueriesAndFallbacks(unittest.TestCase):
    @patch("core.create_client")
    def test_obtener_productos_con_una_y_dos_telas(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        telas_rows = [
            {"id": 1, "nombre": "Algodón", "precio_kilo": 12000.0, "rendimiento": 3.0, "descripcion": "", "activo": True},
            {"id": 2, "nombre": "Lycra", "precio_kilo": 16000.0, "rendimiento": 2.0, "descripcion": "", "activo": True},
        ]
        productos_rows = [
            {
                "id": 100,
                "nombre": "Remera Simple",
                "tela_id": 1,
                "consumo_metros": 0.8,
                "tela_secundaria_id": None,
                "consumo_metros_secundaria": 0,
                "costo_confeccion": 2000.0,
                "tipo_estampado": "Ninguno",
                "consumo_estampado": 0.0,
                "nombre_avio": "",
                "costo_avio": 0.0,
                "activo": True,
            },
            {
                "id": 101,
                "nombre": "Remera Combinada",
                "tela_id": 1,
                "consumo_metros": 0.6,
                "tela_secundaria_id": 2,
                "consumo_metros_secundaria": 0.3,
                "costo_confeccion": 2500.0,
                "tipo_estampado": "DTF",
                "consumo_estampado": 0.2,
                "nombre_avio": "Cierre",
                "costo_avio": 500.0,
                "activo": True,
            },
        ]

        def table_side_effect(table_name):
            tbl = MagicMock()
            if table_name == "telas":
                tbl.select.return_value.execute.return_value = DummyResponse(telas_rows)
                tbl.select.return_value.eq.return_value.execute.return_value = DummyResponse(telas_rows)
            elif table_name == "productos":
                tbl.select.return_value.eq.return_value.execute.return_value = DummyResponse(productos_rows)
                tbl.select.return_value.execute.return_value = DummyResponse(productos_rows)
            return tbl

        mock_client.table.side_effect = table_side_effect

        db = Database()
        productos = db.obtener_productos(solo_activos=True)

        self.assertEqual(len(productos), 2)
        self.assertIsNone(productos[0].tela_secundaria)
        self.assertEqual(productos[0].costo_tela, 3200.0)

        self.assertIsNotNone(productos[1].tela_secundaria)
        self.assertEqual(productos[1].tela_secundaria.nombre, "Lycra")
        self.assertAlmostEqual(productos[1].costo_tela_principal, 2400.0)
        self.assertAlmostEqual(productos[1].costo_tela_secundaria, 2400.0)
        self.assertAlmostEqual(productos[1].costo_tela, 4800.0)

    @patch("core.create_client")
    def test_agregar_y_actualizar_producto_envia_segunda_tela(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        db = Database()
        db.agregar_producto(
            nombre="Buzo Combinado",
            tela_id=1,
            consumo=1.1,
            costo_confeccion=3500.0,
            tipo_estampado="Bordado",
            consumo_estampado=1.0,
            nombre_avio="Cordón",
            costo_avio=400.0,
            tela_secundaria_id=2,
            consumo_metros_secundaria=0.35,
        )

        insert_arg = mock_table.insert.call_args[0][0]
        self.assertEqual(insert_arg["tela_id"], 1)
        self.assertEqual(insert_arg["tela_secundaria_id"], 2)
        self.assertAlmostEqual(insert_arg["consumo_metros_secundaria"], 0.35)


class TestApiEndpoints(unittest.TestCase):
    @patch.dict(os.environ, {"JWT_SECRET": "test_secret_key_for_unit_tests_32b"}, clear=False)
    def setUp(self):
        from fastapi.testclient import TestClient
        import api

        self.api = api
        self.client = TestClient(api.app)
        self.token = api.create_admin_jwt("admin@simplemdq.com")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_health_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_listar_y_crear_producto_con_segunda_tela(self):
        t1 = Tela(id=1, nombre="Algodón", precio_kilo=12000.0, rendimiento=3.0)
        t2 = Tela(id=2, nombre="Lycra", precio_kilo=16000.0, rendimiento=2.0)
        prod_mock = Producto(
            id=50,
            nombre="Remera Combinada",
            tela=t1,
            consumo_metros=0.7,
            tela_secundaria=t2,
            consumo_metros_secundaria=0.25,
            costo_confeccion=2200.0,
            tipo_estampado="Corte + Sublimado",
            consumo_estampado=1.0,
        )
        cfg_mock = Config(
            costo_fijo_base=6000.0,
            multiplicador_default=2.0,
            precios_estampado={"corte + sublimado": 4200.0},
        )

        with patch.object(self.api, "_obtener_config_obj", return_value=cfg_mock), \
             patch.object(self.api.db, "obtener_productos", return_value=[prod_mock]), \
             patch.object(self.api.db, "agregar_producto") as mock_agregar:

            res_get = self.client.get("/api/productos", headers=self.headers)
            self.assertEqual(res_get.status_code, 200)
            data = res_get.json()
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["tela"]["nombre"], "Algodón")
            self.assertEqual(data[0]["tela_secundaria"]["nombre"], "Lycra")
            self.assertAlmostEqual(data[0]["consumo_metros_secundaria"], 0.25)
            self.assertAlmostEqual(data[0]["costo_tela"], 4800.0)
            self.assertAlmostEqual(data[0]["precio_venta"], 24200.0)

            res_post = self.client.post(
                "/api/productos",
                headers=self.headers,
                json={
                    "nombre": "Nueva Combinada",
                    "tela_id": 1,
                    "consumo_metros": 0.7,
                    "tela_secundaria_id": 2,
                    "consumo_metros_secundaria": 0.25,
                    "costo_confeccion": 2200.0,
                    "tipo_estampado": "Corte + Sublimado",
                    "consumo_estampado": 1.0,
                    "nombre_avio": "",
                    "costo_avio": 0.0,
                },
            )
            self.assertEqual(res_post.status_code, 201)
            mock_agregar.assert_called_once_with(
                nombre="Nueva Combinada",
                tela_id=1,
                consumo=0.7,
                costo_confeccion=2200.0,
                tipo_estampado="Corte + Sublimado",
                consumo_estampado=1.0,
                nombre_avio="",
                costo_avio=0.0,
                tela_secundaria_id=2,
                consumo_metros_secundaria=0.25,
            )


if __name__ == "__main__":
    unittest.main()
