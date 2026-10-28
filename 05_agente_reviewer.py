import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from mini_crew import Agent, Task, Crew, Process, LLM, set_workspace_dir
import mini_crew

#1. Cargar configuración y leer artefactos
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
model_name = os.getenv("GROQ_MODEL_NAME", "qwen/qwen3.8-27b")

set_workspace_dir(os.getenv("WORKSPACE_DIR", "."))
base_dir = mini_crew.WORKSPACE_DIR.resolve()
models_file = base_dir / "app" / "models.py"
main_file = base_dir / "app" / "main.py"

if not models_file.exists() or not main_file.exists():
    print("[ERROR] No se encontró el código en app/. Ejecuta primero el Agente 03.")
    sys.exit(1)

codigo_models = models_file.read_text(encoding="utf-8")
codigo_main = main_file.read_text(encoding="utf-8")
prd_content = Path("PRD.md").read_text(encoding="utf-8") if Path("PRD.md").exists() else ""

#2. Configurar LLM y Agente 5 (Code Reviewer & OWASP Auditor)
llm = LLM(model=model_name, api_key=api_key, temperature=0.2, max_tokens=2500)

code_reviewer = Agent(
    role="Principal Security Auditor & Code Reviewer",
    goal="Auditar el código de TalentCore API frente al PRD y OWASP API Security Top 10.",
    backstory=(
        "Auditor de seguridad de software y revisor de arquitectura Python. "
        "Verificas trazabilidad de requerimientos, control de acceso basado en roles (RBAC) "
        "y prevención de vulnerabilidades BOLA (Broken Object Level Authorization)."
    ),
    verbose=True,
    llm=llm,
)

prompt_auditoria = (
    "Realiza una auditoría técnica y de seguridad sobre el código generado para TalentCore API:\n\n"
    f"=== PRD.md ===\n{prd_content}\n=== FIN PRD.md ===\n\n"
    f"=== app/models.py ===\n{codigo_models}\n=== FIN app/models.py ===\n\n"
    f"=== app/main.py ===\n{codigo_main}\n=== FIN app/main.py ===\n\n"
    "Genera el reporte de auditoría en Markdown con estas 4 secciones exactas:\n"
    "1. VEREDICTO EJECUTIVO: Estado de aprobación (APPROVED FOR PRODUCTION) y calificación (ej. 9.5/10).\n"
    "2. MATRIZ DE TRAZABILIDAD DEL PRD: Tabla Markdown verificando si el código cumple AC-01, AC-02, AC-03 y la fórmula de antigüedad.\n"
    "3. AUDITORÍA OWASP API SECURITY: Análisis breve de cómo el código mitiga API1 (BOLA validación de manager_id) y API5 (BFLA validación de rol ADMIN_RRHH).\n"
    "4. RECOMENDACIONES DE MEJORA PARA PRODUCCIÓN: 3 puntos concretos (ej. migrar header X-User-Id a JWT firmado, índices o migraciones con Alembic)."
)

tarea_auditoria = Task(
    description=prompt_auditoria,
    expected_output="Documento AUDIT_REPORT.md estructurado, conciso y técnico (máximo 400 palabras).",
    agent=code_reviewer,
    output_file="AUDIT_REPORT.md",
)

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print(" EJECUTANDO AGENTE 5: CODE REVIEWER & SECURITY AUDITOR")
    print("=" * 70)
    Crew(agents=[code_reviewer], tasks=[tarea_auditoria], process=Process.sequential, verbose=True).kickoff()
    print("\n[OK] Reporte de auditoría generado en: AUDIT_REPORT.md")