# ARCHITECTURE.md

## 1. MODELO DE DATOS (SQLite / SQLAlchemy)

Definición exacta de las entidades usando SQLAlchemy 2.0.

```python
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Empleado(Base):
    __tablename__ = "empleados"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    rol = Column(String, nullable=False) # 'EMPLEADO', 'MANAGER', 'ADMIN_RRHH'
    anios_antiguedad = Column(Integer, nullable=False, default=1)
    manager_id = Column(Integer, ForeignKey("empleados.id"), nullable=True)

class SolicitudVacaciones(Base):
    __tablename__ = "solicitudes_vacaciones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    dias_solicitados = Column(Integer, nullable=False)
    motivo = Column(String, nullable=True)
    estado = Column(String, nullable=False, default="PENDING") # 'PENDING', 'APPROVED', 'REJECTED'
    revisado_por_id = Column(Integer, ForeignKey("empleados.id"), nullable=True)
```

## 2. ESQUEMAS PYDANTIC V2

Clases de validación y serialización.

```python
from pydantic import BaseModel, ConfigDict
from typing import Optional

class EmpleadoCreate(BaseModel):
    nombre: str
    email: str
    rol: str
    anios_antiguedad: int
    manager_id: Optional[int] = None

class EmpleadoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    email: str
    rol: str
    anios_antiguedad: int
    manager_id: Optional[int] = None

class SaldoResponse(BaseModel):
    empleado_id: int
    dias_totales: int
    dias_aprobados: int
    saldo_disponible: int

class SolicitudCreate(BaseModel):
    empleado_id: int
    dias_solicitados: int
    motivo: Optional[str] = None

class RevisionRequest(BaseModel):
    accion: str # 'APPROVE' | 'REJECT'

class SolicitudResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empleado_id: int
    dias_solicitados: int
    motivo: Optional[str]
    estado: str
    revisado_por_id: Optional[int]
```

## 3. ENDPOINTS REST Y RBAC

Autenticación implícita vía header `X-User-Id: int`. Si el ID no existe en BD, responder `404`.

### 1. Health Check
*   **Método**: `GET`
*   **Ruta**: `/health`
*   **RBAC**: Público.
*   **Respuesta**: `200 OK` con body `{"status": "ok"}`.

### 2. Crear Empleado
*   **Método**: `POST`
*   **Ruta**: `/api/v1/empleados`
*   **Body**: `EmpleadoCreate`
*   **RBAC**:
    *   Si `COUNT(empleados) == 0`: Permitir creación sin validar rol (primer ADMIN_RRHH).
    *   Si `COUNT(empleados) > 0`: El usuario `X-User-Id` debe tener `rol == 'ADMIN_RRHH'`. Si no, `403 Forbidden`.
*   **Respuesta**: `201 Created` con `EmpleadoResponse`.

### 3. Consultar Saldo
*   **Método**: `GET`
*   **Ruta**: `/api/v1/vacaciones/saldo/{empleado_id}`
*   **RBAC**: Público (o autenticado, según contexto, pero el PRD no restringe explícitamente el acceso a la lectura del saldo más allá de la existencia del empleado).
*   **Lógica**:
    *   `dias_totales = min(12 + 2 * max(anios_antiguedad - 1, 0), 20)`
    *   `dias_aprobados = SUM(dias_solicitados) WHERE estado == 'APPROVED'`
    *   `saldo_disponible = dias_totales - dias_aprobados`
*   **Respuesta**: `200 OK` con `SaldoResponse`.

### 4. Crear Solicitud
*   **Método**: `POST`
*   **Ruta**: `/api/v1/vacaciones/solicitar`
*   **Body**: `SolicitudCreate`
*   **RBAC**: El usuario `X-User-Id` debe ser el `empleado_id` de la solicitud (implícito por el contexto de "consulta su saldo y crea para sí mismo", aunque el PRD dice "EMPLEADO crea para sí mismo". Asumimos que `X-User-Id` debe coincidir con `empleado_id` en el body o que el body no incluye `empleado_id` y se toma del header. *Corrección basada en el esquema `SolicitudCreate` que incluye `empleado_id`*: Validar que `X-User-Id == empleado_id` en el body. Si no coincide, `403 Forbidden`.
*   **Validación**:
    *   Calcular `saldo_disponible` actual.
    *   Si `dias_solicitados > saldo_disponible`: `400 Bad Request` con `detail="Insufficient vacation balance"`.
*   **Respuesta**: `201 Created` con `SolicitudResponse` (estado `PENDING`).

### 5. Revisar Solicitud
*   **Método**: `POST`
*   **Ruta**: `/api/v1/vacaciones/{solicitud_id}/revisar`
*   **Body**: `RevisionRequest`
*   **RBAC**:
    1.  Usuario `X-User-Id` debe existir.
    2.  Usuario debe tener `rol == 'MANAGER'`.
    3.  El `empleado_id` de la solicitud debe tener `manager_id == X-User-Id`.
    4.  Si falla cualquiera de las condiciones anteriores: `403 Forbidden` con `detail="Unauthorized: Not the direct manager"`.
*   **Validación de Estado**:
    *   Si `solicitud.estado != 'PENDING'`: `400 Bad Request`.
*   **Lógica**:
    *   Si `accion == 'APPROVE'`: `estado = 'APPROVED'`.
    *   Si `accion == 'REJECT'`: `estado = 'REJECTED'`.
    *   `revisado_por_id = X-User-Id`.
*   **Respuesta**: `200 OK` con `SolicitudResponse` actualizado.