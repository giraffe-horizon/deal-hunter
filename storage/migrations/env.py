"""Alembic environment configuration."""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# Add project root to path so models can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from storage.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_BASE_DIR = Path(__file__).parent.parent.parent
_DEFAULT_DB = f"sqlite:///{_BASE_DIR / 'state' / 'deals.db'}"


def get_url() -> str:
    return os.environ.get("DATABASE_URL", _DEFAULT_DB)


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()
    db_path = url.replace("sqlite:///", "")
    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connectable = create_engine(url)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
