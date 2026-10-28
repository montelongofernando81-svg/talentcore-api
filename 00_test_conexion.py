import os
from dotenv import load_dotenv
from mini_crew import LLM
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
model_name = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile")
print(f"--> Probando conexion con Groq ({model_name})...")
try:
    llm = LLM(model=model_name, api_key=api_key, temperature=0.2)
    respuesta = llm.client.chat.completions.create(
        model=llm.model,
        messages=[{"role": "user", "content": "Responde en una sola frase: ¿Que es un agente de software?"}],
        max_tokens=100
    )
    print("\n[OK] Conexion exitosa:")
    print(f"Respuesta del modelo: {respuesta.choices[0].message.content}")
except Exception as e:
    print(f"\n[ERROR] Falla al conectar: {e}")