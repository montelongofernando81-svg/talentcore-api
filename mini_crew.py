import os
import re
import json
import subprocess
import time
from pathlib import Path
from groq import Groq, RateLimitError, APIStatusError
from dotenv import load_dotenv

load_dotenv()

WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "."))

def set_workspace_dir(path: str):
    """Cambia el directorio base donde los agentes escriben y leen código."""
    global WORKSPACE_DIR
    WORKSPACE_DIR = Path(path)

def limpiar_bloques_codigo(texto: str, extension: str = "") -> str:
    """Elimina envoltorios Markdown (```python...```) si el modelo los incluye al escribir código."""
    texto = texto.strip()
    patron = r"^```[a-zA-Z0-9_-]*\n([\s\S]*?)\n```$"
    coincidencia = re.match(patron, texto)
    if coincidencia:
        return coincidencia.group(1).strip() + "\n"
    if texto.startswith("```") and texto.endswith("```"):
        lineas = texto.splitlines()
        if len(lineas) >= 2:
            return "\n".join(lineas[1:-1]).strip() + "\n"
    return texto

class LLM:
    def __init__(self, model: str = None, api_key: str = None, temperature: float = 0.2, max_tokens: int = 4096):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile")
        if self.model.startswith("groq/"):
            self.model = self.model.replace("groq/", "")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = Groq(api_key=self.api_key)

class Tool:
    def __init__(self, name: str, description: str, parameters: dict, func):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_groq_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, **kwargs) -> str:
        return str(self.func(**kwargs))

def tool(name: str, description: str, parameters: dict):
    def decorador(func):
        return Tool(name=name, description=description, parameters=parameters, func=func)
    return decorador

@tool(
    name="write_project_file",
    description="Crea o sobrescribe un archivo completo dentro del proyecto.",
    parameters={
        "type": "object",
        "properties": {
            "relative_path": {"type": "string", "description": "Ruta relativa, ej: app/main.py"},
            "content": {"type": "string", "description": "Contenido completo del archivo"},
        },
        "required": ["relative_path", "content"],
    },
)
def write_project_file(relative_path: str, content: str) -> str:
    base = WORKSPACE_DIR.resolve()
    destino = (base / relative_path).resolve()
    if destino != base and base not in destino.parents:
        return f"ERROR DE SEGURIDAD: Ruta fuera del proyecto ({relative_path})."
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not relative_path.endswith(".md"):
        content = limpiar_bloques_codigo(content)
    destino.write_text(content, encoding="utf-8")
    return f"OK: Archivo '{relative_path}' guardado exitosamente ({len(content)} caracteres)."

@tool(
    name="read_project_file",
    description="Lee el contenido de un archivo existente dentro del proyecto.",
    parameters={
        "type": "object",
        "properties": {
            "relative_path": {"type": "string", "description": "Ruta relativa, ej: app/main.py"},
        },
        "required": ["relative_path"],
    },
)
def read_project_file(relative_path: str) -> str:
    base = WORKSPACE_DIR.resolve()
    destino = (base / relative_path).resolve()
    if destino != base and base not in destino.parents:
        return "ERROR DE SEGURIDAD: Ruta fuera del proyecto."
    if not destino.exists():
        return f"ERROR: El archivo '{relative_path}' no existe."
    return destino.read_text(encoding="utf-8")

@tool(
    name="run_pytest_suite",
    description="Ejecuta 'pytest -v' dentro del directorio del proyecto y devuelve el resultado.",
    parameters={
        "type": "object",
        "properties": {
            "test_target": {"type": "string", "description": "Ruta de tests, por defecto 'tests/'"},
        },
        "required": [],
    },
)
def run_pytest_suite(test_target: str = "tests/") -> str:
    try:
        import sys
        resultado = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", test_target],
            cwd=str(WORKSPACE_DIR.resolve()),
            capture_output=True, text=True, timeout=45,
        )
        estado = "PASSED" if resultado.returncode == 0 else "FAILED"
        salida = (resultado.stdout + "\n" + resultado.stderr).strip()
        if len(salida) > 2500:
            salida = salida[:2500] + "\n... [salida truncada]..."
        return f"ESTADO: {estado} (código {resultado.returncode})\n{salida}"
    except subprocess.TimeoutExpired:
        return "ERROR: pytest superó el límite de 45 segundos."
    except Exception as e:
        return f"ERROR al ejecutar pytest: {type(e).__name__}: {e}"

class Agent:
    def __init__(self, role: str, goal: str, backstory: str, llm: LLM = None, verbose: bool = True,
                 allow_delegation: bool = False, tools: list = None, max_tool_iterations: int = 8):
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.llm = llm or LLM()
        self.verbose = verbose
        self.tools = tools or []
        self.max_tool_iterations = max_tool_iterations

    def _llamar_modelo(self, messages: list):
        params = dict(
            messages=messages,
            model=self.llm.model,
            temperature=self.llm.temperature,
            max_tokens=self.llm.max_tokens,
        )
        if self.tools:
            params["tools"] = [t.to_groq_schema() for t in self.tools]
            params["tool_choice"] = "auto"
        for intento in range(1, 5):
            try:
                time.sleep(2)
                response = self.llm.client.chat.completions.create(**params)
                break
            except RateLimitError:
                if intento == 4:
                    raise
                espera = 25 * intento
                print(f" [!] Límite de tokens por minuto (429) en Groq. Pausando {espera}s (reintento {intento}/3)...")
                time.sleep(espera)
            except APIStatusError as e:
                if getattr(e, "status_code", None) == 413:
                    print(f"\n[!] ERROR 413 [{self.role}]: El prompt excede el límite de entrada de Groq.")
                    raise
        if response.choices[0].finish_reason == "length":
            print(f"\n[!] ADVERTENCIA [{self.role}]: La respuesta alcanzó max_tokens={self.llm.max_tokens}.")
        return response

    def _ejecutar_tool(self, tool_call) -> str:
        nombre = tool_call.function.name
        herramienta = next((t for t in self.tools if t.name == nombre), None)
        if herramienta is None:
            return f"ERROR: La herramienta '{nombre}' no está disponible."
        try:
            args = json.loads(tool_call.function.arguments or "{}")
            return herramienta.run(**args)
        except Exception as e:
            return f"ERROR al ejecutar '{nombre}': {type(e).__name__}: {e}"

    def execute_task(self, task_description: str, context: str = "", expected_output: str = "") -> str:
        system_prompt = (
            f"ERES: {self.role}\n"
            f"OBJETIVO: {self.goal}\n"
            f"CONTEXTO: {self.backstory}\n"
            f"INSTRUCCIÓN: Sé conciso, técnico y directo. No agregues saludos ni texto de relleno."
        )
        user_prompt = f"TAREA:\n{task_description}"
        if expected_output:
            user_prompt += f"\n\nFORMATO ESPERADO:\n{expected_output}"
        if context:
            user_prompt += f"\n\nCONTEXTO PREVIO:\n{context}"
        if self.verbose:
            print(f"\n[{self.role}] Procesando tarea...")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        for _ in range(self.max_tool_iterations):
            response = self._llamar_modelo(messages)
            mensaje = response.choices[0].message
            if not mensaje.tool_calls:
                return mensaje.content or ""
            messages.append({
                "role": "assistant",
                "content": mensaje.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in mensaje.tool_calls
                ],
            })
            for tc in mensaje.tool_calls:
                if self.verbose:
                    print(f" [Tool] Invocando '{tc.function.name}'...")
                resultado = self._ejecutar_tool(tc)
                if self.verbose:
                    print(f" [Tool] Resultado: {resultado[:180]}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": resultado})
        return "Tarea finalizada tras ejecutar las herramientas."

class Task:
    def __init__(self, description: str, expected_output: str, agent: Agent, output_file: str = None):
        self.description = description
        self.expected_output = expected_output
        self.agent = agent
        self.output_file = output_file
        self.output = None

class Crew:
    def __init__(self, agents: list, tasks: list, process=None, verbose: bool = True):
        self.agents = agents
        self.tasks = tasks
        self.verbose = verbose

    def kickoff(self) -> str:
        accumulated_context = ""
        last_output = ""
        for idx, task in enumerate(self.tasks, 1):
            if self.verbose:
                print(f"\n--> Ejecutando Tarea {idx}/{len(self.tasks)} | Agente: {task.agent.role}")
            output = task.agent.execute_task(
                task.description,
                context=accumulated_context,
                expected_output=task.expected_output,
            )
            task.output = output
            last_output = output
            accumulated_context += f"\n--- Salida de {task.agent.role} ---\n{output}\n"
            if task.output_file:
                contenido_guardar = output
                if not task.output_file.endswith(".md"):
                    contenido_guardar = limpiar_bloques_codigo(output)
                with open(task.output_file, "w", encoding="utf-8") as f:
                    f.write(contenido_guardar)
                if self.verbose:
                    print(f" [+] Entregable guardado en: {task.output_file}")
        return last_output

class Process:
    sequential = "sequential"