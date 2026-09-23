"""Procedencia multifuente y agrupación conservadora de oportunidades.

Revision ID: 20260923000005
Revises: 20260918000004

Añade lo necesario para mezclar SECOP I y SECOP II en un mismo listado sin
perder de dónde vino cada fila y sin fusionar por su cuenta lo que no puede
demostrar que es el mismo proceso.

Decisiones que se reflejan en el esquema:

  * `platform` se separa de `source_dataset` porque son cosas distintas: el
    conjunto es un recurso de datos concreto y la plataforma es el sistema del
    Estado que lo publica. La interfaz declara procedencia con la plataforma.

  * `entity_nit` en dígitos es la única columna que permite reconocer la misma
    entidad en ambas plataformas. El nombre comercial cambia entre ellas
    («CAUCA - ALCALDÍA MUNICIPIO DE TIMBIQUI» frente a «ALCALDIA DE TIMBIQUI»);
    el NIT no.

  * `amount` es NUMERIC y no coma flotante porque es dinero: el redondeo
    binario no debe decidir la comparación de dos valores económicos.

  * `group_key` NO fusiona. Solo permite señalar «estas dos filas podrían ser
    el mismo proceso» para que lo confirme una persona. La medición del
    2026-09-23 no respalda ninguna clave que garantice la equivalencia entre
    plataformas, así que el sistema no decide por su cuenta.

Los datos existentes se rellenan desde `raw_payload`, que se conserva
precisamente para poder renormalizar sin volver a consultar la fuente.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260923000005"
down_revision: str | None = "20260918000004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Conjuntos conocidos en el momento de esta migración.
SECOP_II_DATASET = "p6dx-8zbt"
SECOP_I_DATASET = "f789-7hwg"


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column(
            "platform",
            sa.String(length=16),
            nullable=False,
            # Valor por defecto en el servidor para que las filas ya existentes
            # queden válidas al añadir una columna NOT NULL. Se retira después:
            # dejar el default haría que un olvido del código insertara filas
            # marcadas como SECOP II por descarte, que es una procedencia
            # inventada.
            server_default="SECOP_II",
        ),
    )
    op.add_column("opportunities", sa.Column("entity_nit", sa.String(length=32), nullable=True))
    op.add_column(
        "opportunities",
        sa.Column("amount", sa.Numeric(precision=20, scale=2), nullable=True),
    )
    op.add_column("opportunities", sa.Column("group_key", sa.String(length=320), nullable=True))

    op.create_index(
        "ix_opportunity_group_key", "opportunities", ["group_key"], unique=False
    )
    op.create_index(
        "ix_opportunity_source_dataset", "opportunities", ["source_dataset"], unique=False
    )
    op.create_index(
        "ix_opportunity_entity_nit", "opportunities", ["entity_nit"], unique=False
    )

    # --- Relleno de las filas existentes ----------------------------------
    # La procedencia se deduce del conjunto, que sí es fiable.
    op.execute(
        f"""
        UPDATE opportunities
           SET platform = 'SECOP_I'
         WHERE source_dataset = '{SECOP_I_DATASET}'
        """
    )
    op.execute(
        f"""
        UPDATE opportunities
           SET platform = 'SECOP_II'
         WHERE source_dataset = '{SECOP_II_DATASET}'
        """
    )

    # El NIT, solo dígitos: se descarta cualquier separador de formato.
    # El NIT, solo dígitos: se descarta cualquier separador de formato. El
    # nombre del campo cambia entre plataformas, de ahí el par (platform, field).
    for platform, field in (
        ("SECOP_II", "nit_entidad"),
        ("SECOP_I", "nit_de_la_entidad"),
    ):
        op.execute(
            f"""
            UPDATE opportunities
               SET entity_nit = NULLIF(
                     regexp_replace(raw_payload->>'{field}', '\\D', '', 'g'), ''
                   )
             WHERE platform = '{platform}' AND raw_payload ? '{field}'
            """
        )

    # El valor económico. Cada plataforma usa su propio campo: `precio_base` y
    # `cuantia_proceso` NO miden lo mismo, y por eso se guardan por separado en
    # lugar de fusionarse en una única columna «valor».
    #
    # El cast se protege con una comprobación de forma numérica. Sin ella, una
    # sola fila con texto en ese campo —el conjunto ha cambiado de tipo entre
    # versiones— abortaría la migración completa y dejaría el esquema a medias.
    for platform, field in (("SECOP_II", "precio_base"), ("SECOP_I", "cuantia_proceso")):
        op.execute(
            f"""
            UPDATE opportunities
               SET amount = (raw_payload->>'{field}')::numeric
             WHERE platform = '{platform}'
               AND raw_payload ? '{field}'
               AND (raw_payload->>'{field}') ~ '^[0-9]+(\\.[0-9]+)?$'
            """
        )

    # La clave de agrupación, con la misma normalización que el código:
    # mayúsculas y sin separadores. Se calcula en SQL para no dejar la columna
    # vacía hasta la siguiente sincronización.
    op.execute(
        """
        UPDATE opportunities
           SET group_key = entity_nit || ':' || upper(
                 regexp_replace(reference, '[^0-9A-Za-z]+', '', 'g')
               )
         WHERE entity_nit IS NOT NULL
           AND reference IS NOT NULL
           AND upper(regexp_replace(reference, '[^0-9A-Za-z]+', '', 'g')) <> ''
        """
    )

    # El default ya no es necesario y su presencia sería peligrosa: una fila
    # insertada sin `platform` explícito quedaría declarando una procedencia
    # que nadie comprobó.
    op.alter_column("opportunities", "platform", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_opportunity_entity_nit", table_name="opportunities")
    op.drop_index("ix_opportunity_source_dataset", table_name="opportunities")
    op.drop_index("ix_opportunity_group_key", table_name="opportunities")
    op.drop_column("opportunities", "group_key")
    op.drop_column("opportunities", "amount")
    op.drop_column("opportunities", "entity_nit")
    op.drop_column("opportunities", "platform")
