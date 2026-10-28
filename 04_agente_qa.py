import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from mini_crew import (
    Agent,
    Task,
    Crew,
    Process,
    LLM,
    set_workspace_dir,
    run_pytest_suite,
)
import mini_crew

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
model_name = os.getenv("GROQ_MODEL_NAME", "qwen/qwen3.8-27b")

set_workspace_dir(os.getenv("WORKSPACE_DIR", "."))
base_dir = mini_crew.WORKSPACE_DIR.resolve()
tests_dir = base_dir / "tests"
tests_dir.mkdir(parents=True, exist_ok=True)
(tests_dir / "__init__.py").write_text("# Tests Package\n", encoding="utf-8")

models_file = base_dir / "app" / "models.py"
main_file = base_dir / "app" / "main.py"

if not models_file.exists() or not main_file.exists():
    print("[ERROR] No se encontró el código en app/. Ejecuta primero 03_agente_developer.py.")
    sys.exit(1)

codigo_models = models_file.read_text(encoding="utf-8")
codigo_main = main_file.read_text(encoding="utf-8")
prd_content = Path("PRD.md").read_text(encoding="utf-8") if Path("PRD.md").exists() else ""

llm = LLM(model=model_name, api_key=api_key, temperature=0.1, max_tokens=5000)

qa_engineer = Agent(
    role="Lead QA Automation Engineer (Pytest Specialist)",
    goal="Escribir pruebas de integración deterministas con Pytest y FastAPI TestClient para validar los criterios Gherkin.",
    backstory=(
        "Ingeniero de QA implacable experto en Pytest y FastAPI. "
        "Diseñas suites de pruebas limpias, aisladas y sin efectos secundarios en la base de datos."
    ),
    verbose=True,
    llm=llm,
)

ruta_test_file = str(tests_dir / "test_api.py")
prompt_tests = (
    "Analiza el código real del microservicio y el PRD para escribir la suite de pruebas en `tests/test_api.py`:\n\n"
    f"=== app/models.py ===\n{codigo_models}\n=== FIN app/models.py ===\n\n"
    f"=== app/main.py ===\n{codigo_main}\n=== FIN app/main.py ===\n\n"
    f"=== PRD.md ===\n{prd_content}\n=== FIN PRD.md ===\n\n"
    "Escribe el código Python completo para `tests/test_api.py` usando `pytest` y `from fastapi.testclient import TestClient`.\n"
    "REGLAS OBLIGATORIAS PARA `tests/test_api.py`:\n"
    "1. Importa `app` desde `app.main` y `Base, engine` desde `app.models`.\n"
    "2. Define un fixture `@pytest.fixture(autouse=True)` que antes de cada test ejecute:\n"
    "`Base.metadata.drop_all(bind=engine)` y `Base.metadata.create_all(bind=engine)` para que cada prueba empiece con la base de datos limpia y vacía.\n"
    "3. Incluye exactamente estas 4 funciones de prueba (`test_...`):\n"
    "- `test_health_check()`: Verifica `GET /health` -> 200 OK y `{\"status\": \"ok\"}`.\n"
    "- `test_ac01_solicitud_valida_y_calculo_saldo()`:\n"
    "  * Crea al primer empleado con rol `\"ADMIN_RRHH\"` (ej. id=1).\n"
    "  * Usando header `{\"X-User-Id\": \"1\"}`, crea un `\"MANAGER\"` (id=2) y un `\"EMPLEADO\"` (id=3, `anios_antiguedad=3`, `manager_id=2`).\n"
    "  * Consulta `GET /api/v1/vacaciones/saldo/3` y verifica que `dias_totales == 16` y `saldo_disponible == 16`.\n"
    "  * Solicita 5 días en `POST /api/v1/vacaciones/solicitar` para `empleado_id=3` -> verifica `201 Created` y `estado == \"PENDING\"`.\n"
    "  * El manager (header `{\"X-User-Id\": \"2\"}`) aprueba en `POST /api/v1/vacaciones/1/revisar` con `{\"accion\": \"APPROVE\"}` -> verifica `200 OK`, `estado == \"APPROVED\"` y que el nuevo saldo disponible en `GET /api/v1/vacaciones/saldo/3` ahora sea `11`.\n"
    "- `test_ac02_saldo_insuficiente()`:\n"
    "  * Crea ADMIN_RRHH (id=1) y un `EMPLEADO` (id=2, `anios_antiguedad=1`, le tocan 12 días).\n"
    "  * Intenta solicitar 15 días en `POST /api/v1/vacaciones/solicitar` -> verifica `400 Bad Request` y `\"Insufficient vacation balance\"` en `response.json()[\"detail\"]`.\n"
    "- `test_ac03_manager_no_autorizado()`:\n"
    "  * Crea `ADMIN_RRHH` (id=1), `MANAGER A` (id=2), `MANAGER B` (id=3) y `EMPLEADO` (id=4 con `manager_id=2`).\n"
    "  * El empleado 4 solicita 3 días (201 Created, solicitud id=1).\n"
    "  * El MANAGER B (header `{\"X-User-Id\": \"3\"}`, que NO es su jefe directo) intenta aprobar `POST /api/v1/vacaciones/1/revisar` -> verifica `403 Forbidden` y `\"Unauthorized: Not the direct manager\"` en `response.json()[\"detail\"]`.\n\n"
    "REGLA ESTRICTA: Devuelve ÚNICAMENTE el código Python puro, sin explicaciones antes ni después."
)

tarea_crear_tests = Task(
    description=prompt_tests,
    expected_output="Código Python puro del archivo tests/test_api.py.",
    agent=qa_engineer,
    output_file=ruta_test_file,
)

print("\n" + "=" * 70)
print(" EJECUTANDO AGENTE 4: QA ENGINEER (GENERANDO tests/test_api.py)")
print("=" * 70)
Crew(agents=[qa_engineer], tasks=[tarea_crear_tests], verbose=True).kickoff()

print("\n" + "=" * 70)
print(" EJECUTANDO SUITE PYTEST EN TERMINAL REAL")
print("=" * 70)
max_intentos = 3
for intento in range(1, max_intentos + 1):
    print(f"\n--> Corrida Pytest (Intento {intento}/{max_intentos}):")
    resultado_pytest = run_pytest_suite.run(test_target="tests/test_api.py")
    print(resultado_pytest)
    if "ESTADO: PASSED" in resultado_pytest:
        print("\n" + "=" * 70)
        print(" [OK] ¡100% DE LOS TESTS PASARON EN VERDE!")
        print("=" * 70)
        break
    if intento < max_intentos:
        print("\n[!] Se detectaron fallos en Pytest. Activando Agente de Autocorrección...")
        codigo_test_actual = Path(ruta_test_file).read_text(encoding="utf-8")
        codigo_main_actual = Path(main_file).read_text(encoding="utf-8")
        prompt_fix = (
            "Al ejecutar pytest se obtuvo el siguiente error:\n"
            f"=== SALIDA PYTEST ===\n{resultado_pytest}\n=== FIN SALIDA PYTEST ===\n\n"
            f"=== CÓDIGO ACTUAL app/main.py ===\n{codigo_main_actual}\n=== FIN app/main.py ===\n\n"
            f"=== CÓDIGO ACTUAL tests/test_api.py ===\n{codigo_test_actual}\n=== FIN tests/test_api.py ===\n\n"
            "Corrige el archivo `tests/test_api.py` (ajustando los headers, parámetros o rutas según cómo esté implementado `app/main.py`) "
            "para que las 4 pruebas pasen respetando las reglas de negocio.\n"
            "Devuelve ÚNICAMENTE el código Python corregido de `tests/test_api.py`."
        )
        tarea_fix = Task(
            description=prompt_fix,
            expected_output="Código Python corregido de tests/test_api.py.",
            agent=qa_engineer,
            output_file=ruta_test_file,
        )
        Crew(agents=[qa_engineer], tasks=[tarea_fix], verbose=True).kickoff()
    else:
        print("\n[!] Se alcanzó el límite de reintentos. Revisa la traza de pytest arriba.")