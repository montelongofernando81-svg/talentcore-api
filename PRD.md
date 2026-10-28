# PRD: TalentCore API

## 1. ROLES DEL SISTEMA
*   **EMPLEADO**: Consulta su saldo y crea solicitudes de vacaciones para sí mismo.
*   **MANAGER**: Aprueba o rechaza solicitudes **únicamente** de subordinados directos (`empleado.manager_id == manager.id`).
*   **ADMIN_RRHH**: Único rol autorizado para crear registros de empleados.

## 2. REGLA DE SALDO DE VACACIONES
*   **Cálculo de Días Totales**:
    *   Si `anios_antiguedad < 1`: `dias_totales = 12`.
    *   Si `anios_antiguedad >= 1`: `dias_totales = min(12 + 2 * (anios_antiguedad - 1), 20)`.
*   **Saldo Disponible**:
    *   `saldo_disponible = dias_totales - SUM(dias_solicitados)` donde `estado == 'APPROVED'`.
*   **Validación**: La suma de días solicitados en estado `PENDING` + `APPROVED` no puede exceder `dias_totales`.

## 3. MÁQUINA DE ESTADOS DE SOLICITUD
*   **Estados**: `PENDING` (inicial), `APPROVED` (descuenta saldo), `REJECTED` (no descuenta saldo).
*   **Transiciones**:
    *   `PENDING` -> `APPROVED`: Solo por MANAGER autorizado.
    *   `PENDING` -> `REJECTED`: Solo por MANAGER autorizado.
    *   Transiciones desde `APPROVED` o `REJECTED` están prohibidas.
*   **Restricción**: Solo se permite modificar solicitudes en estado `PENDING`.

## 4. CRITERIOS DE ACEPTACIÓN (Gherkin)

```gherkin
Scenario: AC-01 Crear solicitud válida
  Given un EMPLEADO con saldo_disponible >= dias_solicitados
  When crea una solicitud de vacaciones
  Then responde HTTP 201 Created
  And la solicitud tiene estado PENDING

Scenario: AC-02 Solicitud con saldo insuficiente
  Given un EMPLEADO con saldo_disponible < dias_solicitados
  When intenta crear una solicitud de vacaciones
  Then responde HTTP 400 Bad Request
  And el body contiene detail: "Insufficient vacation balance"

Scenario: AC-03 Manager sin autoridad
  Given un MANAGER que NO es el manager_id directo del EMPLEADO solicitante
  When intenta aprobar o rechazar la solicitud
  Then responde HTTP 403 Forbidden
  And el body contiene detail: "Unauthorized: Not the direct manager"
```