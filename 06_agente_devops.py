import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from mini_crew import Agent, Task, Crew, Process, LLM, set_workspace_dir
import mini_crew

#1. Cargar configuración y preparar carpetas
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
model_name = os.getenv("GROQ_MODEL_NAME", "qwen/qwen3.8-27b")

set_workspace_dir(os.getenv("WORKSPACE_DIR", "."))
base_dir = mini_crew.WORKSPACE_DIR.resolve()
workflows_dir = base_dir / ".github" / "workflows"
workflows_dir.mkdir(parents=True, exist_ok=True)

if not (base_dir / "app" / "main.py").exists():
    print("[ERROR] No existe app/main.py. Ejecuta primero el Agente 03.")
    sys.exit(1)

#2. Configurar LLM y Agente 6 (DevOps Engineer)
llm = LLM(model=model_name, api_key=api_key, temperature=0.1, max_tokens=2500)

devops_engineer = Agent(
    role="Senior DevOps & Cloud Infrastructure Engineer",
    goal="Empaquetar TalentCore API en contenedores Docker ligeros y configurar su pipeline CI/CD en GitHub Actions.",
    backstory=(
        "Especialista en Docker, contenedores seguros y automatización CI/CD para microservicios FastAPI. "
        "Generas archivos de configuración limpios, listos para producción y sin texto explicativo extra."
    ),
    verbose=True,
    llm=llm,
)

#3. Tarea 1: Generar Dockerfile
ruta_dockerfile = str(base_dir / "Dockerfile")
tarea_dockerfile = Task(
    description=(
        "Escribe un Dockerfile limpio para el microservicio FastAPI ubicado en `app/main.py`.\n"
        "Requisitos:\n"
        "- Imagen base: `python:3.11-slim`.\n"
        "- WORKDIR `/app`.\n"
        "- Copiar requirements.txt e instalar con `pip install --no-cache-dir -r requirements.txt`.\n"
        "- Copiar la carpeta `./app` a `/app/app` y `./tests` a `/app/tests`.\n"
        "- Exponer el puerto `8000`.\n"
        "- Comando de arranque: `CMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]`.\n"
        "REGLA ESTRICTA: Devuelve ÚNICAMENTE el contenido del Dockerfile, sin explicaciones."
    ),
    expected_output="Contenido puro del archivo Dockerfile.",
    agent=devops_engineer,
    output_file=ruta_dockerfile,
)

#4. Tarea 2: Generar docker-compose.yml
ruta_compose = str(base_dir / "docker-compose.yml")
tarea_compose = Task(
    description=(
        "Escribe un archivo docker-compose.yml para levantar el servicio `talentcore-api`.\n"
        "Requisitos:\n"
        "- Construir desde el directorio actual (`build: .`).\n"
        "- Mapear el puerto `8000:8000`.\n"
        "- Definir variable de entorno `PYTHONUNBUFFERED=1`.\n"
        "- Configurar `restart: unless-stopped`.\n"
        "REGLA ESTRICTA: Devuelve ÚNICAMENTE el código YAML puro, sin explicaciones."
    ),
    expected_output="Contenido YAML puro del archivo docker-compose.yml.",
    agent=devops_engineer,
    output_file=ruta_compose,
)

#5. Tarea 3: Generar Pipeline CI en GitHub Actions (.github/workflows/ci.yml)
ruta_ci = str(workflows_dir / "ci.yml")
tarea_ci = Task(
    description=(
        "Escribe un workflow de GitHub Actions (`.github/workflows/ci.yml`) llamado `TalentCore CI`.\n"
        "Requisitos:\n"
        "- Disparadores: `push` y `pull_request` en la rama `main`.\n"
        "- Job `test` sobre `ubuntu-latest` con Python `3.11`.\n"
        "- Pasos: `actions/checkout@v4`, `actions/setup-python@v5` (python-version: '3.11'), "
        "instalar dependencias (`pip install -r requirements.txt`) y ejecutar `pytest -v`.\n"
        "REGLA ESTRICTA: Devuelve ÚNICAMENTE el código YAML puro, sin explicaciones."
    ),
    expected_output="Contenido YAML puro del archivo ci.yml.",
    agent=devops_engineer,
    output_file=ruta_ci,
)

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print(" EJECUTANDO AGENTE 6: DEVOPS ENGINEER (DOCKER & CI/CD)")
    print("=" * 70)
    for idx, t in enumerate([tarea_dockerfile, tarea_compose, tarea_ci], 1):
        print(f"\n--> Generando artefacto DevOps {idx}/3...")
        Crew(agents=[devops_engineer], tasks=[t], process=Process.sequential, verbose=True).kickoff()
    print("\n" + "=" * 70)
    print(" [OK] INFRAESTRUCTURA DEVOPS GENERADA EXITOSAMENTE")
    print("=" * 70)
    for rel in ["Dockerfile", "docker-compose.yml", ".github/workflows/ci.yml"]:
        p = base_dir / rel
        estado = f"OK ({p.stat().st_size} bytes)" if p.exists() else "FALTA"
        print(f" - {rel}: {estado}")