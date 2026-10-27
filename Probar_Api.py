import os
import sys
import uuid

import httpx

BASE_URL = os.environ.get("PROBA_API_BASE_URL", "http://127.0.0.1:8000")


def imprimir_paso(titulo: str, estado: bool, detalle: object = "") -> None:
    color = "\033[92m[EXITO]\033[0m" if estado else "\033[91m[FALLO]\033[0m"
    print(f"{color} {titulo}")
    if detalle:
        print(f"       -> {detalle}")
    if not estado:
        raise RuntimeError(f"Falló la prueba: {titulo}")


def validar_respuesta(
    titulo: str, respuesta: httpx.Response, codigo_esperado: int
) -> dict[str, object]:
    try:
        datos = respuesta.json()
    except ValueError:
        datos = respuesta.text

    imprimir_paso(
        titulo,
        respuesta.status_code == codigo_esperado,
        f"HTTP {respuesta.status_code}: {datos}",
    )
    if not isinstance(datos, dict):
        raise RuntimeError(f"La respuesta de {titulo} no contiene un objeto JSON")
    return datos


def ejecutar_auditoria() -> None:
    identificador = uuid.uuid4().hex
    print("=" * 70)
    print("   INICIANDO BATERÍA DE PRUEBAS DINÁMICAS (CLIENTE HTTP)")
    print("=" * 70)

    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        validar_respuesta(
            "1. Verificación de servicio (/health)",
            client.get("/health"),
            200,
        )

        admin_data = {
            "nombre_completo": "Super Admin",
            "email": f"admin_{identificador}@corp.com",
            "rol": "ADMIN_RRHH",
            "anios_antiguedad": 5,
        }
        admin = validar_respuesta(
            "2. Registro del primer Administrador",
            client.post("/api/v1/empleados", json=admin_data),
            201,
        )
        admin_id = admin["id"]

        headers_admin = {"X-User-Id": str(admin_id)}
        manager_data = {
            "nombre_completo": "Jefe de Operaciones",
            "email": f"jefe_{identificador}@corp.com",
            "rol": "MANAGER",
            "anios_antiguedad": 4,
        }
        manager = validar_respuesta(
            "3. Registro de Manager",
            client.post(
                "/api/v1/empleados",
                json=manager_data,
                headers=headers_admin,
            ),
            201,
        )
        manager_id = manager["id"]

        empleado_data = {
            "nombre_completo": "Ana Desarrolladora",
            "email": f"ana_{identificador}@corp.com",
            "rol": "EMPLEADO",
            "anios_antiguedad": 2,
            "manager_id": manager_id,
        }
        empleado = validar_respuesta(
            "4. Registro de Empleado (2 años de antigüedad)",
            client.post(
                "/api/v1/empleados",
                json=empleado_data,
                headers=headers_admin,
            ),
            201,
        )
        empleado_id = empleado["id"]

        saldo = validar_respuesta(
            "5. Consulta del saldo inicial",
            client.get(f"/api/v1/vacaciones/saldo/{empleado_id}"),
            200,
        )
        imprimir_paso(
            "5a. Verificación del cálculo legal (14 días)",
            saldo.get("saldo_disponible") == 14,
            saldo,
        )

        solicitud_exceso = {
            "empleado_id": empleado_id,
            "dias_solicitados": 15,
            "motivo": "Exceso",
        }
        exceso = client.post(
            "/api/v1/vacaciones/solicitar",
            json=solicitud_exceso,
        )
        if exceso.status_code == 400:
            detalle_exceso = exceso.json()
        else:
            detalle_exceso = f"HTTP {exceso.status_code}: {exceso.text}"
        imprimir_paso(
            "6. Rechazo de solicitud que excede el saldo",
            exceso.status_code == 400,
            detalle_exceso,
        )

        solicitud_valida = {
            "empleado_id": empleado_id,
            "dias_solicitados": 4,
            "motivo": "Viaje corto",
        }
        solicitud = validar_respuesta(
            "7. Registro de solicitud válida (PENDING)",
            client.post(
                "/api/v1/vacaciones/solicitar",
                json=solicitud_valida,
            ),
            201,
        )
        solicitud_id = solicitud["id"]

        headers_usurpador = {"X-User-Id": "999"}
        intento_no_autorizado = client.post(
            f"/api/v1/vacaciones/{solicitud_id}/revisar",
            json={"accion": "APPROVE"},
            headers=headers_usurpador,
        )
        imprimir_paso(
            "8. Rechazo de aprobación por usuario no autorizado",
            intento_no_autorizado.status_code in (403, 404),
            f"HTTP {intento_no_autorizado.status_code}: {intento_no_autorizado.text}",
        )

        headers_manager = {"X-User-Id": str(manager_id)}
        validar_respuesta(
            "9. Aprobación por el Manager directo",
            client.post(
                f"/api/v1/vacaciones/{solicitud_id}/revisar",
                json={"accion": "APPROVE"},
                headers=headers_manager,
            ),
            200,
        )

        saldo_final = validar_respuesta(
            "10. Consulta del saldo final",
            client.get(f"/api/v1/vacaciones/saldo/{empleado_id}"),
            200,
        )
        imprimir_paso(
            "10a. Verificación del saldo final (14 - 4 = 10 días)",
            saldo_final.get("saldo_disponible") == 10,
            saldo_final,
        )

    print("=" * 70)
    print("   BATERÍA DE PRUEBAS COMPLETADA EXITOSAMENTE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        ejecutar_auditoria()
    except httpx.RequestError as error:
        print(f"\n[ERROR] No se pudo conectar al servidor: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except RuntimeError as error:
        print(f"\n[ERROR] {error}", file=sys.stderr)
        raise SystemExit(1) from error