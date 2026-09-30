"""Cliente de la API del hospital (`api/servidor.py`): estado del día, en JSON como texto.

Solo stdlib. Cada función devuelve el cuerpo JSON tal cual lo manda la API, como string:
eso es lo que va a los `contextos` del evaluador y lo que lee el modelo. Los errores de la
API (nombre inexistente, parámetro faltante) también se devuelven como texto, porque traen
la lista de opciones válidas y el agente se corrige con eso.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("API_HOSPITAL_URL", "http://localhost:8765")
TIMEOUT = 10


def _get(ruta, **params):
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{BASE_URL}{ruta}" + (f"?{query}" if query else "")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8")
    except Exception as e:
        return json.dumps(
            {"error": f"no se pudo consultar la API del hospital en {BASE_URL}: {e}"},
            ensure_ascii=False,
        )


def camas(sector):
    return _get("/camas", sector=sector)


def guardia(especialidad):
    return _get("/guardia", especialidad=especialidad)


def turnos(especialidad):
    return _get("/turnos", especialidad=especialidad)


def farmacia(medicamento):
    return _get("/farmacia", medicamento=medicamento)


def espera():
    return _get("/espera")
