#!/usr/bin/env python
import os
import sys


def main() -> None:
    """Executa a tarefa administrativa indicada nos argumentos da linha de comando."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Nao foi possivel importar o Django. Verifique se ele esta instalado e se o "
            "ambiente virtual esta ativo."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
