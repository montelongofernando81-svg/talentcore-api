# TalentCore API y agentes

Este repositorio contiene la API de vacaciones y los agentes que generan, prueban,
revisan y preparan el proyecto. El directorio de trabajo predeterminado es la raíz
del repositorio.

## Requisitos

- Python 3.11 o posterior
- Una clave de API de Groq para ejecutar los agentes (la API REST no requiere esa clave)

## Instalación en Windows

Desde la raíz del repositorio, ejecuta en PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` y configura `GROQ_API_KEY` antes de ejecutar agentes. No publiques
ese archivo; `.env` está excluido de Git.

## Ejecutar la API

```powershell
uvicorn app.main:app --reload
```

La comprobación de salud está disponible en `http://127.0.0.1:8000/health`.
La base de datos SQLite `talentcore.db` se crea localmente y no se versiona.

En Swagger (`/docs`), puedes modificar datos de un empleado con
`PATCH /api/v1/empleados/{empleado_id}`. Configura `ADMIN_API_KEY` como variable
secreta del servicio en Render y envía su valor en el header `X-Admin-Key`.
Si no está configurada, la API rechaza las modificaciones. Envía solo los campos
que quieres cambiar: `nombre`, `email`,
`anios_antiguedad` o `manager_id`. Para quitar el manager, envía
`"manager_id": null`.

## Publicar en Render

El archivo `render.yaml` configura TalentCore como un servicio web público.
Conecta este repositorio en Render y crea un **New Blueprint Instance**. Cuando
termine el despliegue, Swagger estará disponible sin autenticación en
`https://<url-del-servicio>/docs`; OpenAPI, en `https://<url-del-servicio>/openapi.json`.
La API REST también quedará expuesta públicamente, por lo que configura la
autenticación antes de usarla con datos reales.

## Ejecutar los agentes

Desde la raíz y con `.env` configurado, ejecuta los scripts en este orden:

1. `python 01_agente_product_owner.py`
2. `python 02_agente_arquitecto.py`
3. `python 03_agente_developer.py`
4. `python 04_agente_qa.py`
5. `python 05_agente_reviewer.py`
6. `python 06_agente_devops.py`

`python 00_test_conexion.py` comprueba la conexión con Groq. El directorio de
trabajo puede cambiarse mediante `WORKSPACE_DIR` en `.env`.
