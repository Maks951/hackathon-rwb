"""Manual storage smoke check; creates a clearly marked demo file and ZIP."""
import os
import tempfile
from pathlib import Path
from uuid import UUID
from app.db import get_session_factory
from app.repositories.artifacts import artifact_path, package_run, register_artifact


def main():
    run_id = UUID(input('ID запуска: ').strip())
    target = artifact_path(run_id, 'storage-check.txt')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=target.parent, suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            output.write('Проверка хранилища. Это тестовый файл, не результат Qwen.\n')
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
    with get_session_factory()() as session:
        item = register_artifact(session, run_id=run_id, path='storage-check.txt')
        print('Artifact ID:', item.id)
    with get_session_factory()() as session:
        package_run(session, run_id=run_id)
    print('Готово: GET /runs/{run_id}/artifacts и /download в Swagger')


if __name__ == '__main__':
    main()
