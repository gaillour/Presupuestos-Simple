from unittest.mock import MagicMock
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from api import app, create_admin_jwt, db
from core import Config, Database, Producto, Tela


class TestApiContracts:
    @pytest.fixture(autouse=True)
    def setup_api(self):
        self.admin_token = create_admin_jwt("admin@simplemdq.com")
        self.auth_headers = {"Authorization": f"Bearer {self.admin_token}"}

    def test_health_check_sin_autenticacion(self, client: TestClient):
        response = client.get("/api/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("status") == "ok"
        assert "service" in data

    def test_endpoints_protegidos_rechazan_sin_token(self, client: TestClient):
        endpoints = [
            ("GET", "/api/auth/me"),
            ("GET", "/api/configuracion"),
            ("GET", "/api/telas"),
            ("POST", "/api/telas"),
            ("GET", "/api/productos"),
            ("POST", "/api/productos"),
            ("GET", "/api/presupuestos"),
            ("POST", "/api/presupuestos/calcular"),
            ("GET", "/api/presupuestos/1/pdf"),
        ]
        for method, url in endpoints:
            res = client.request(method, url)
            assert res.status_code == status.HTTP_401_UNAUTHORIZED, f"Endpoint {method} {url} devolvió {res.status_code} en vez de 401"

    def test_token_invalido_o_corrupto(self, client: TestClient):
        headers = {"Authorization": "Bearer token_completamente_invalido_123"}
        res = client.get("/api/auth/me", headers=headers)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_payload_invalido(self, client: TestClient):
        # Payload vacío
        res = client.post("/api/auth/login", json={})
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Faltan credenciales obligatorias
        res = client.post("/api/auth/login", json={"email": "solo_email@test.com"})
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_crear_tela_validaciones_de_tipos(self, client: TestClient):
        # precio_kilo no es numérico
        payload = {"nombre": "Tela Test", "precio_kilo": "no-es-numero", "rendimiento": 3.0}
        res = client.post("/api/telas", json=payload, headers=self.auth_headers)
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # rendimiento faltante
        payload_incompleto = {"nombre": "Tela Test", "precio_kilo": 5000.0}
        res = client.post("/api/telas", json=payload_incompleto, headers=self.auth_headers)
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_crear_producto_validaciones_de_tipos(self, client: TestClient):
        # tela_id debe ser entero
        payload = {
            "nombre": "Producto Invalido",
            "tela_id": "id-invalido",
            "consumo": 1.0,
            "costo_confeccion": 1000.0,
        }
        res = client.post("/api/productos", json=payload, headers=self.auth_headers)
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_calcular_presupuesto_con_producto_inexistente(self, client: TestClient, monkeypatch):
        # Catálogo vacío en base de datos para forzar no encontrado
        monkeypatch.setattr(db, "obtener_productos", lambda: [])
        monkeypatch.setattr(db, "obtener_configuracion", lambda: {"costo_fijo": 5000.0, "multiplicador": 2.0})

        payload = {
            "cliente": "Cliente Test",
            "items": [{"producto_id": 99999, "cantidad": 2, "costo_estampado": 0.0}],
        }
        res = client.post("/api/presupuestos/calcular", json=payload, headers=self.auth_headers)
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert "no encontrado" in res.json().get("detail", "").lower()

    def test_calcular_presupuesto_rechaza_items_vacios(self, client: TestClient):
        # El contrato Pydantic (min_length=1) debe rechazar peticiones sin ítems con 422
        payload = {
            "cliente": "Cliente Vacio",
            "items": [],
        }
        res = client.post("/api/presupuestos/calcular", json=payload, headers=self.auth_headers)
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_calcular_presupuesto_exitoso_con_producto_valido(self, client: TestClient, monkeypatch):
        t = Tela(id=1, nombre="Algodón", precio_kilo=10000.0, rendimiento=2.0)
        p = Producto(id=10, nombre="Remera Test", tela=t, consumo_metros=1.0, costo_confeccion=2000.0)
        monkeypatch.setattr(db, "obtener_configuracion", lambda: {"costo_fijo": 5000.0, "multiplicador": 2.0})
        monkeypatch.setattr(db, "obtener_productos", lambda: [p])

        payload = {
            "cliente": "Cliente Valido",
            "items": [{"producto_id": 10, "cantidad": 3, "costo_estampado": 0.0}],
        }
        res = client.post("/api/presupuestos/calcular", json=payload, headers=self.auth_headers)
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["cliente"] == "Cliente Valido"
        assert data["total_prendas"] == 3
        # Costo tela: 5000 * 1 = 5000. Base: 5000 + 2000 = 7000. Precio unit: (7000 * 2) + 5000 = 19000. Total: 19000 * 3 = 57000.
        assert data["total_final"] == 57000.0

    def test_descargar_pdf_query_token_vs_header(self, client: TestClient, monkeypatch):
        cabecera_mock = {
            "id": 1,
            "cliente": "Cliente PDF",
            "activo": True,
            "created_at": "2026-11-02T12:00:00Z",
            "multiplicador": 2.0,
            "costo_fijo": 5000.0,
            "total": 10000.0,
        }
        detalles_mock = [
            {
                "cantidad": 2,
                "precio_unitario": 5000.0,
                "productos": {"nombre": "Remera Algodon"},
            }
        ]

        monkeypatch.setattr(db, "obtener_presupuesto_por_id", lambda x: cabecera_mock)
        monkeypatch.setattr(db, "obtener_detalles_presupuesto", lambda x: detalles_mock)
        monkeypatch.setattr(db, "obtener_configuracion", lambda: {"costo_fijo": 5000.0, "multiplicador": 2.0})

        # 1. Con Header Bearer
        res_header = client.get("/api/presupuestos/1/pdf", headers=self.auth_headers)
        assert res_header.status_code == status.HTTP_200_OK
        assert res_header.headers["content-type"] == "application/pdf"
        assert res_header.content.startswith(b"%PDF-")

        # 2. Con Query Param ?token=
        res_query = client.get(f"/api/presupuestos/1/pdf?token={self.admin_token}")
        assert res_query.status_code == status.HTTP_200_OK
        assert res_query.headers["content-type"] == "application/pdf"
        assert res_query.content.startswith(b"%PDF-")

    def test_descargar_pdf_presupuesto_inexistente(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(db, "obtener_presupuesto_por_id", lambda x: None)

        res = client.get("/api/presupuestos/999999/pdf", headers=self.auth_headers)
        assert res.status_code == status.HTTP_404_NOT_FOUND
