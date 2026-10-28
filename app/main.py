import os
import secrets
from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import Optional

from app.models import (
    Base, engine, get_db,
    Empleado, SolicitudVacaciones,
    EmpleadoCreate, EmpleadoUpdate, EmpleadoResponse,
    SaldoResponse, SolicitudCreate,
    RevisionRequest, SolicitudResponse,
)

app = FastAPI(title="TalentCore API")
Base.metadata.create_all(bind=engine)


def calcular_saldo(emp: Empleado, db: Session) -> tuple[int, int, int]:
    dias_totales = 12 if emp.anios_antiguedad < 1 else min(12 + 2 * (emp.anios_antiguedad - 1), 20)
    dias_aprobados = (
        db.query(SolicitudVacaciones)
        .filter(SolicitudVacaciones.empleado_id == emp.id, SolicitudVacaciones.estado == "APPROVED")
        .with_entities(SolicitudVacaciones.dias_solicitados)
        .all()
    )
    dias_aprobados = sum(d[0] for d in dias_aprobados)
    saldo_disponible = dias_totales - dias_aprobados
    return dias_totales, dias_aprobados, saldo_disponible


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/empleados", status_code=201, response_model=EmpleadoResponse)
def crear_empleado(
    payload: EmpleadoCreate,
    x_user_id: Optional[int] = Header(None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    if db.query(Empleado).count() > 0:
        if x_user_id is None:
            raise HTTPException(status_code=403, detail="Missing X-User-Id header")
        admin = db.query(Empleado).filter(Empleado.id == x_user_id).first()
        if not admin:
            raise HTTPException(status_code=404, detail="User not found")
        if admin.rol != "ADMIN_RRHH":
            raise HTTPException(status_code=403, detail="Only ADMIN_RRHH can create employees")
    emp = Empleado(**payload.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@app.patch("/api/v1/empleados/{empleado_id}", response_model=EmpleadoResponse)
def actualizar_empleado(
    empleado_id: int,
    payload: EmpleadoUpdate,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db),
):
    admin_api_key = os.getenv("ADMIN_API_KEY")
    if not admin_api_key:
        raise HTTPException(status_code=503, detail="Employee updates are not configured")
    if not secrets.compare_digest(x_admin_key, admin_api_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    empleado = db.query(Empleado).filter(Empleado.id == empleado_id).first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Employee not found")

    cambios = payload.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    for campo in ("nombre", "email", "anios_antiguedad"):
        if campo in cambios and cambios[campo] is None:
            raise HTTPException(status_code=422, detail=f"{campo} cannot be null")
    if "anios_antiguedad" in cambios and cambios["anios_antiguedad"] < 0:
        raise HTTPException(status_code=422, detail="anios_antiguedad must be non-negative")
    if "manager_id" in cambios and cambios["manager_id"] is not None:
        manager = db.query(Empleado).filter(Empleado.id == cambios["manager_id"]).first()
        if not manager:
            raise HTTPException(status_code=404, detail="Manager not found")
    if "email" in cambios:
        email_en_uso = (
            db.query(Empleado)
            .filter(Empleado.email == cambios["email"], Empleado.id != empleado_id)
            .first()
        )
        if email_en_uso:
            raise HTTPException(status_code=409, detail="Email already registered")

    for campo, valor in cambios.items():
        setattr(empleado, campo, valor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Employee update conflicts with existing data")
    db.refresh(empleado)
    return empleado


@app.get("/api/v1/vacaciones/saldo/{empleado_id}", response_model=SaldoResponse)
def obtener_saldo(empleado_id: int, db: Session = Depends(get_db)):
    emp = db.query(Empleado).filter(Empleado.id == empleado_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    dias_totales, dias_aprobados, saldo_disponible = calcular_saldo(emp, db)
    return SaldoResponse(
        empleado_id=empleado_id,
        dias_totales=dias_totales,
        dias_aprobados=dias_aprobados,
        saldo_disponible=saldo_disponible,
    )


@app.post("/api/v1/vacaciones/solicitar", status_code=201, response_model=SolicitudResponse)
def solicitar_vacaciones(payload: SolicitudCreate, db: Session = Depends(get_db)):
    emp = db.query(Empleado).filter(Empleado.id == payload.empleado_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    _, _, saldo_disponible = calcular_saldo(emp, db)
    if payload.dias_solicitados > saldo_disponible:
        raise HTTPException(status_code=400, detail="Insufficient vacation balance")
    sol = SolicitudVacaciones(
        empleado_id=payload.empleado_id,
        dias_solicitados=payload.dias_solicitados,
        motivo=payload.motivo,
        estado="PENDING",
    )
    db.add(sol)
    db.commit()
    db.refresh(sol)
    return sol


@app.post("/api/v1/vacaciones/{solicitud_id}/revisar", response_model=SolicitudResponse)
def revisar_solicitud(
    solicitud_id: int,
    payload: RevisionRequest,
    x_user_id: int = Header(..., alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    solicitud = db.query(SolicitudVacaciones).filter(SolicitudVacaciones.id == solicitud_id).first()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Request not found")
    manager = db.query(Empleado).filter(Empleado.id == x_user_id).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    empleado = db.query(Empleado).filter(Empleado.id == solicitud.empleado_id).first()
    if manager.rol != "MANAGER" or empleado.manager_id != x_user_id:
        raise HTTPException(status_code=403, detail="Unauthorized: Not the direct manager")
    if solicitud.estado != "PENDING":
        raise HTTPException(status_code=400, detail="Request already processed")
    if payload.accion == "APPROVE":
        solicitud.estado = "APPROVED"
    elif payload.accion == "REJECT":
        solicitud.estado = "REJECTED"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    solicitud.revisado_por_id = x_user_id
    db.commit()
    db.refresh(solicitud)
    return solicitud
