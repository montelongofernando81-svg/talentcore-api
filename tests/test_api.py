import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import Base, get_db


@pytest.fixture(autouse=True)
def clean_database(tmp_path):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def client():
    return TestClient(app)


def crear_empleado(client, nombre, rol, anios_antiguedad=1, manager_id=None, user_id=None):
    payload = {
        "nombre": nombre,
        "email": f"{nombre.lower().replace(' ', '.')}@example.com",
        "rol": rol,
        "anios_antiguedad": anios_antiguedad,
        "manager_id": manager_id,
    }
    headers = {"X-User-Id": str(user_id)} if user_id is not None else {}
    return client.post("/api/v1/empleados", json=payload, headers=headers)


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ac01_solicitud_valida_y_calculo_saldo(client):
    assert crear_empleado(client, "Admin", "ADMIN_RRHH").status_code == 201
    assert crear_empleado(client, "Manager", "MANAGER", user_id=1).status_code == 201
    assert crear_empleado(
        client,
        "Empleado",
        "EMPLEADO",
        anios_antiguedad=3,
        manager_id=2,
        user_id=1,
    ).status_code == 201

    saldo_inicial = client.get("/api/v1/vacaciones/saldo/3")
    assert saldo_inicial.status_code == 200
    assert saldo_inicial.json()["dias_totales"] == 16
    assert saldo_inicial.json()["saldo_disponible"] == 16

    solicitud = client.post(
        "/api/v1/vacaciones/solicitar",
        json={"empleado_id": 3, "dias_solicitados": 5},
    )
    assert solicitud.status_code == 201
    assert solicitud.json()["estado"] == "PENDING"

    revision = client.post(
        f"/api/v1/vacaciones/{solicitud.json()['id']}/revisar",
        json={"accion": "APPROVE"},
        headers={"X-User-Id": "2"},
    )
    assert revision.status_code == 200
    assert revision.json()["estado"] == "APPROVED"

    saldo_final = client.get("/api/v1/vacaciones/saldo/3")
    assert saldo_final.json()["saldo_disponible"] == 11


def test_ac02_saldo_insuficiente(client):
    assert crear_empleado(client, "Admin", "ADMIN_RRHH").status_code == 201
    assert crear_empleado(
        client,
        "Empleado",
        "EMPLEADO",
        anios_antiguedad=1,
        user_id=1,
    ).status_code == 201

    response = client.post(
        "/api/v1/vacaciones/solicitar",
        json={"empleado_id": 2, "dias_solicitados": 15},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient vacation balance"


def test_ac03_manager_no_autorizado(client):
    assert crear_empleado(client, "Admin", "ADMIN_RRHH").status_code == 201
    assert crear_empleado(client, "Manager A", "MANAGER", user_id=1).status_code == 201
    assert crear_empleado(client, "Manager B", "MANAGER", user_id=1).status_code == 201
    assert crear_empleado(
        client,
        "Empleado",
        "EMPLEADO",
        manager_id=2,
        user_id=1,
    ).status_code == 201

    solicitud = client.post(
        "/api/v1/vacaciones/solicitar",
        json={"empleado_id": 4, "dias_solicitados": 3},
    )
    assert solicitud.status_code == 201

    response = client.post(
        f"/api/v1/vacaciones/{solicitud.json()['id']}/revisar",
        json={"accion": "APPROVE"},
        headers={"X-User-Id": "3"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Unauthorized: Not the direct manager"
