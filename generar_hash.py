"""Genera hash Werkzeug para usuarios Huente. Uso: python generar_hash.py 'tu_clave'"""

import sys

from werkzeug.security import generate_password_hash


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1]:
        print("Uso: python generar_hash.py 'contraseña'", file=sys.stderr)
        return 1
    print(generate_password_hash(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
