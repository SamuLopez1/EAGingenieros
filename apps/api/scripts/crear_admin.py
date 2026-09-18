#!/usr/bin/env python3
"""Crea el primer usuario administrador.

No hay registro público: las cuentas se crean por invitación de un
administrador. Este script resuelve el problema del arranque, cuando todavía no
existe ningún administrador que pueda invitar.

Uso:

    python -m scripts.crear_admin --email admin@eag.local

Si se omite `--password`, se genera una aleatoria y se imprime **una sola vez**.
Es la opción recomendada: evita que la contraseña quede en el historial del
shell o en la lista de procesos de la máquina.
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys

from sqlalchemy import select

from app.auth.passwords import MIN_PASSWORD_LENGTH, WeakPasswordError, hash_password
from app.auth.principal import Role
from app.auth.service import normalise_email
from app.config import Settings
from app.db.models import Base, User
from app.db.session import create_engine_from_url, create_session_factory, session_scope


def generate_password(length: int = 24) -> str:
    """Genera una contraseña aleatoria legible.

    Se evitan caracteres ambiguos (O/0, l/1/I) porque estas contraseñas se
    transcriben a mano la primera vez.
    """

    letters = string.ascii_letters.translate(str.maketrans("", "", "lIO"))
    digits = string.digits.translate(str.maketrans("", "", "01"))
    alphabet = letters + digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crea un usuario administrador de EAG.")
    parser.add_argument("--email", required=True, help="Correo del administrador")
    parser.add_argument("--name", default=None, help="Nombre para mostrar")
    parser.add_argument(
        "--password",
        default=None,
        help="Contraseña. Si se omite, se genera una aleatoria y se muestra una vez.",
    )
    parser.add_argument(
        "--role",
        choices=[r.value for r in Role],
        default=Role.ADMINISTRATOR.value,
        help="Rol del usuario (por defecto: administrador)",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if not settings.database_is_configured:
        print(
            "ERROR: EAG_DATABASE_URL no está configurada.\n"
            "Defínala o levante el entorno con infra/dev/docker-compose.yml.",
            file=sys.stderr,
        )
        return 2

    password = args.password or generate_password()
    generated = args.password is None

    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"ERROR: la contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.",
            file=sys.stderr,
        )
        return 2

    engine = create_engine_from_url(settings.require_database_url())
    factory = create_session_factory(engine)
    email = normalise_email(args.email)

    try:
        # Las tablas se crean si no existen, para que el script sirva en un
        # entorno recién levantado sin obligar a ejecutar la migración aparte.
        Base.metadata.create_all(engine)

        with session_scope(factory) as session:
            existing = session.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
            if existing is not None:
                print(
                    f"ERROR: ya existe un usuario con el correo {email}.", file=sys.stderr
                )
                return 1

            try:
                user = User(
                    email=email,
                    display_name=args.name,
                    password_hash=hash_password(password),
                    role=args.role,
                    is_active=True,
                )
            except WeakPasswordError as error:
                print(f"ERROR: {error}", file=sys.stderr)
                return 2

            session.add(user)
            session.flush()
            user_id = user.id

        print(f"Usuario creado: {email} (id {user_id}, rol {args.role})")
        if generated:
            print()
            print(f"  Contraseña: {password}")
            print()
            print("  Guárdela ahora: no se vuelve a mostrar y solo está almacenada")
            print("  como hash Argon2id, del que no se puede recuperar.")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
