"""Initial schema for lab2

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-05-31 06:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Создание схемы lab2
    op.execute("CREATE SCHEMA IF NOT EXISTS lab2")

    # Создание таблицы users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password', sa.String(length=120), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        schema='lab2'
    )

    # Создание таблицы products
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('stock', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='lab2'
    )

    # Создание таблицы orders
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='Pending'),
        sa.ForeignKeyConstraint(['user_id'], ['lab2.users.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='lab2'
    )

    # Создание таблицы order_items
    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['lab2.orders.id']),
        sa.ForeignKeyConstraint(['product_id'], ['lab2.products.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='lab2'
    )

    # Вставка начальных данных
    op.execute("""
        INSERT INTO lab2.users (username, password, role) VALUES
        ('admin', 'adminpass', 'admin'),
        ('testuser', 'userpass', 'user');
    """)
    op.execute("""
        INSERT INTO lab2.products (name, price, stock) VALUES
        ('Laptop', 999.99, 10),
        ('Smartphone', 499.99, 20),
        ('Headphones', 79.99, 50);
    """)

def downgrade():
    op.drop_table('order_items', schema='lab2')
    op.drop_table('orders', schema='lab2')
    op.drop_table('products', schema='lab2')
    op.drop_table('users', schema='lab2')
    op.execute("DROP SCHEMA lab2")