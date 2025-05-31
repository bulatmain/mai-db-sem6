from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app import db, User, Product, Order, OrderItem  # Импортируем модели из app.py

config = context.config
fileConfig(config.config_file_name)
connectable = engine_from_config(
    config.get_section(config.config_ini_section),
    prefix='sqlalchemy.',
    poolclass=pool.NullPool)

with connectable.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=db.metadata,
        include_schemas=True,
        include_object=lambda object, name, type_, reflected, compare_to: object.schema == 'lab2'
    )

    with context.begin_transaction():
        context.run_migrations()