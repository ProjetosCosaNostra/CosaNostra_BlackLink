from pathlib import Path

# BASE_DIR = pasta raiz do projeto CosaNostra_BlackLink
BASE_DIR = Path(__file__).resolve().parents[2]

# Pasta onde os HTMLs dos usuários serão gerados
USERS_DIR = BASE_DIR / "users"

# Pasta de templates do backend (Jinja2)
TEMPLATES_DIR = Path(__file__).resolve().parents[1].parent / "templates"

# Garante que as pastas existam
USERS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
