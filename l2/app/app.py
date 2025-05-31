from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
import uuid
import json
import time
from datetime import timedelta
from alembic.config import Config
from alembic import command

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin123@localhost:5432/db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'super-secret-key'
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = Redis(host='localhost', port=6380, db=0)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

db = SQLAlchemy(app)
redis_client = Redis(host='localhost', port=6380, db=0)

# Модель для пользователя
class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = {'schema': 'lab2'}
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')

# Модель для товара
class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = {'schema': 'lab2'}
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)

# Модель для заказа
class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = {'schema': 'lab2'}
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('lab2.users.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Pending')
    items = db.relationship('OrderItem', backref='order', lazy=True)

# Модель для элементов заказа
class OrderItem(db.Model):
    __tablename__ = 'order_items'
    __table_args__ = {'schema': 'lab2'}
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('lab2.orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('lab2.products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

# Применение миграций при старте приложения
def apply_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

# Регистрация пользователя
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'User already exists'}), 400
    user = User(username=username, password=password, role='user')
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully'}), 201

# Авторизация и генерация токена
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username=username, password=password).first()
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    token = str(uuid.uuid4())
    redis_client.setex(f'token:{token}', 3600, json.dumps({'user_id': user.id, 'role': user.role}))
    return jsonify({'token': token, 'role': user.role}), 200

# Проверка токена и роли
def check_token(token, required_role=None):
    token_data = redis_client.get(f'token:{token}')
    if not token_data:
        return None
    token_data = json.loads(token_data)
    user_id = token_data.get('user_id')
    role = token_data.get('role')
    if required_role and role != required_role:
        return None
    return user_id

# CRUD: Создание товара (только для админа)
@app.route('/products', methods=['POST'])
def create_product():
    token = request.headers.get('Authorization')
    user_id = check_token(token, required_role='admin')
    if not user_id:
        return jsonify({'error': 'Unauthorized or not an admin'}), 401
    data = request.get_json()
    name = data.get('name')
    price = data.get('price')
    stock = data.get('stock')
    if not all([name, price, stock]):
        return jsonify({'error': 'Missing required fields'}), 400
    product = Product(name=name, price=price, stock=stock)
    db.session.add(product)
    db.session.commit()
    redis_client.delete('products')
    return jsonify({'message': 'Product created', 'id': product.id}), 201

# CRUD: Получение одного товара
@app.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    cached = redis_client.get(f'product:{product_id}')
    if cached:
        return jsonify(json.loads(cached)), 200
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    product_data = {'id': product.id, 'name': product.name, 'price': product.price, 'stock': product.stock}
    redis_client.setex(f'product:{product_id}', 300, json.dumps(product_data))
    return jsonify(product_data), 200

# CRUD: Обновление товара (только для админа)
@app.route('/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    token = request.headers.get('Authorization')
    user_id = check_token(token, required_role='admin')
    if not user_id:
        return jsonify({'error': 'Unauthorized or not an admin'}), 401
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    data = request.get_json()
    product.name = data.get('name', product.name)
    product.price = data.get('price', product.price)
    product.stock = data.get('stock', product.stock)
    db.session.commit()
    redis_client.delete('products')
    redis_client.delete(f'product:{product_id}')
    return jsonify({'message': 'Product updated'}), 200

# CRUD: Удаление товара (только для админа)
@app.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    token = request.headers.get('Authorization')
    user_id = check_token(token, required_role='admin')
    if not user_id:
        return jsonify({'error': 'Unauthorized or not an admin'}), 401
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    db.session.delete(product)
    db.session.commit()
    redis_client.delete('products')
    redis_client.delete(f'product:{product_id}')
    return jsonify({'message': 'Product deleted'}), 200

# Получение каталога товаров
@app.route('/products', methods=['GET'])
def get_products():
    cached = redis_client.get('products')
    if cached:
        return jsonify(json.loads(cached)), 200
    products = Product.query.all()
    product_list = [{'id': p.id, 'name': p.name, 'price': p.price, 'stock': p.stock} for p in products]
    redis_client.setex('products', 300, json.dumps(product_list))
    return jsonify(product_list), 200

# Получение содержимого корзины
@app.route('/cart', methods=['GET'])
def get_cart():
    token = request.headers.get('Authorization')
    user_id = check_token(token)
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    cart_key = f'cart:{user_id}'
    cart = redis_client.get(cart_key)
    cart = json.loads(cart) if cart else {}
    return jsonify({'cart': cart}), 200

# Очистка корзины
@app.route('/cart', methods=['DELETE'])
def delete_cart():
    token = request.headers.get('Authorization')
    user_id = check_token(token)
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    cart_key = f'cart:{user_id}'
    redis_client.delete(cart_key)
    return jsonify({'message': 'Cart deleted'}), 200

# Добавление товара в корзину
@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    token = request.headers.get('Authorization')
    user_id = check_token(token)
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({'error': f'Product {product_id} not found'}), 404
    cart_key = f'cart:{user_id}'
    cart = redis_client.get(cart_key)
    cart = json.loads(cart) if cart else {}
    cart[str(product_id)] = cart.get(str(product_id), 0) + quantity
    redis_client.setex(cart_key, 86400, json.dumps(cart))
    return jsonify({'message': 'Added to cart'}), 200

# Оформление заказа
@app.route('/order', methods=['POST'])
def create_order():
    token = request.headers.get('Authorization')
    user_id = check_token(token)
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    cart_key = f'cart:{user_id}'
    cart = redis_client.get(cart_key)
    if not cart:
        return jsonify({'error': 'Cart is empty'}), 400
    cart = json.loads(cart)
    order = Order(user_id=user_id, status='Pending')
    db.session.add(order)
    db.session.commit()
    for product_id, quantity in cart.items():
        order_item = OrderItem(order_id=order.id, product_id=int(product_id), quantity=quantity)
        db.session.add(order_item)
    db.session.commit()
    redis_client.delete(cart_key)
    # Store notification for the user
    notification = json.dumps({
        'order_id': order.id,
        'status': 'Pending',
        'timestamp': int(time.time()),
        'message': f'Order {order.id} created with status Pending'
    })
    redis_client.lpush(f'notifications:{user_id}', notification)
    redis_client.ltrim(f'notifications:{user_id}', 0, 99)  # Keep last 100 notifications
    redis_client.publish('orders', notification)
    return jsonify({'message': 'Order created', 'order_id': order.id}), 201

# Обновление статуса заказа (только для админа)
@app.route('/order/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    token = request.headers.get('Authorization')
    user_id = check_token(token, required_role='admin')
    if not user_id:
        return jsonify({'error': 'Unauthorized or not an admin'}), 401
    data = request.get_json()
    new_status = data.get('status')
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    order.status = new_status
    db.session.commit()
    # Store notification for the order's user
    notification = json.dumps({
        'order_id': order_id,
        'status': new_status,
        'timestamp': int(time.time()),
        'message': f'Order {order_id} status updated to {new_status}'
    })
    redis_client.lpush(f'notifications:{order.user_id}', notification)
    redis_client.ltrim(f'notifications:{order.user_id}', 0, 99)  # Keep last 100 notifications
    redis_client.publish('orders', notification)
    return jsonify({'message': 'Status updated'}), 200

# Получение уведомлений
@app.route('/notifications', methods=['GET'])
def notifications():
    token = request.headers.get('Authorization')
    user_id = check_token(token)
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    notifications_key = f'notifications:{user_id}'
    notifications = redis_client.lrange(notifications_key, 0, -1)
    if not notifications:
        return jsonify({'notifications': []}), 200
    notifications = [json.loads(notification) for notification in notifications]
    return jsonify({'notifications': notifications}), 200

if __name__ == '__main__':
    with app.app_context():
        apply_migrations()  # Применяем миграции при старте
    app.run(host='0.0.0.0', port=5000)