from flask import Flask, request, jsonify, session, Response
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
import uuid
import json
import time
import logging
import logging.handlers
import os
from datetime import timedelta
from alembic.config import Config
from alembic import command
from sqlalchemy.exc import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG for detailed logging

# Console handler (for kubectl logs)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# File handler with rotation
os.makedirs('/app/logs', exist_ok=True)  # Create logs directory
file_handler = logging.handlers.RotatingFileHandler(
    '/app/logs/app.log',
    maxBytes=10*1024*1024,  # 10MB per file
    backupCount=5  # Keep 5 backup files
)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

app = Flask(__name__)

PG_USERNAME = os.environ.get('PG_USERNAME')
PG_PASSWORD = os.environ.get('PG_PASSWORD')
PG_HOST     = os.environ.get('PG_HOST')
PG_PORT     = os.environ.get('PG_PORT')
PG_DB       = os.environ.get('PG_DB')
REDIS_HOST  = os.environ.get('REDIS_HOST')
REDIS_PORT  = os.environ.get('REDIS_PORT')
REDIS_DB    = os.environ.get('REDIS_DB')

SQLALCHEMY_URL = f'postgresql://{PG_USERNAME}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}'
logger.debug(f'SQL_ALCHEMY_URL: {SQLALCHEMY_URL}')
os.environ['SQLALCHEMY_URL'] = SQLALCHEMY_URL  # Set for alembic.ini
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'super-secret-key'
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = Redis(host=REDIS_HOST, port=int(REDIS_PORT), db=int(REDIS_DB))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

db = SQLAlchemy(app)
redis_client = Redis(host=REDIS_HOST, port=int(REDIS_PORT), db=int(REDIS_DB))

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
    try:
        logger.debug("Starting Alembic migrations")
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully")
    except Exception as e:
        logger.error(f"Failed to apply migrations: {str(e)}")
        raise

# Проверка токена и роли
def check_token(token, required_role=None):
    logger.debug(f'Checking token for role {required_role}, token: {token}')
    if not token or not isinstance(token, str):
        logger.warning("Invalid or missing token")
        return None
    try:
        logger.debug(f"Fetching token data from Redis for token: {token}")
        token_data = redis_client.get(f'token:{token}')
        if not token_data:
            logger.warning(f"Token {token} not found in Redis")
            return None
        token_data = json.loads(token_data)
        user_id = token_data.get('user_id')
        role = token_data.get('role')
        logger.debug(f"Token data: user_id={user_id}, role={role}")
        if required_role and role != required_role:
            logger.warning(f"User {user_id} does not have required role {required_role}")
            return None
        return user_id
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in check_token: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error in check_token: {str(e)}")
        return None

# Регистрация пользователя
@app.route('/register', methods=['POST'])
def register():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        logger.info(f'Requested register for {username}')
        logger.debug(f"Checking if username {username} exists")
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'User already exists'}), 400
        user = User(username=username, password=password, role='user')
        db.session.add(user)
        logger.debug(f"Committing new user {username} to database")
        db.session.commit()
        return jsonify({'message': 'User registered successfully'}), 201
    except OperationalError as e:
        logger.error(f"Database error in register: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except Exception as e:
        logger.error(f"Error in register: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Авторизация и генерация токена
@app.route('/login', methods=['POST'])
def login():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        logger.info(f'Requested login for {username}')
        logger.debug(f"Querying user {username}")
        user = User.query.filter_by(username=username, password=password).first()
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        token = str(uuid.uuid4())
        logger.debug(f"Storing token {token} in Redis for user {user.id}")
        redis_client.setex(f'token:{token}', 3600, json.dumps({'user_id': user.id, 'role': user.role}))
        return jsonify({'token': token, 'role': user.role}), 200
    except OperationalError as e:
        logger.error(f"Database error in login: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in login: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in login: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# CRUD: Создание товара (только для админа)
@app.route('/products', methods=['POST'])
def create_product():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token, required_role='admin')
        logger.info(f'Requested product addition for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized or not an admin'}), 401
        data = request.get_json()
        name = data.get('name')
        price = data.get('price')
        stock = data.get('stock')
        logger.debug(f"Product data: name={name}, price={price}, stock={stock}")
        if not all([name, price, stock]):
            return jsonify({'error': 'Missing required fields'}), 400
        product = Product(name=name, price=price, stock=stock)
        db.session.add(product)
        logger.debug("Committing new product to database")
        db.session.commit()
        redis_client.delete('products')
        return jsonify({'message': 'Product created', 'id': product.id}), 201
    except OperationalError as e:
        logger.error(f"Database error in create_product: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in create_product: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in create_product: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# CRUD: Получение одного товара
@app.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        logger.info(f'Requested product {product_id}')
        logger.debug(f"Checking Redis cache for product:{product_id}")
        cached = redis_client.get(f'product:{product_id}')
        if cached:
            logger.debug(f"Cache hit for product {product_id}")
            return jsonify(json.loads(cached)), 200
        logger.debug(f"Querying database for product {product_id}")
        product = db.session.get(Product, product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        product_data = {'id': product.id, 'name': product.name, 'price': product.price, 'stock': product.stock}
        logger.debug(f"Caching product {product_id} in Redis")
        redis_client.setex(f'product:{product_id}', 300, json.dumps(product_data))
        return jsonify(product_data), 200
    except OperationalError as e:
        logger.error(f"Database error in get_product: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in get_product: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in get_product: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# CRUD: Обновление товара (только для админа)
@app.route('/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token, required_role='admin')
        logger.info(f'Requested product edit for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized or not an admin'}), 401
        logger.debug(f"Querying database for product {product_id}")
        product = db.session.get(Product, product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        data = request.get_json()
        product.name = data.get('name', product.name)
        product.price = data.get('price', product.price)
        product.stock = data.get('stock', product.stock)
        logger.debug(f"Committing updated product {product_id} to database")
        db.session.commit()
        redis_client.delete('products')
        redis_client.delete(f'product:{product_id}')
        return jsonify({'message': 'Product updated'}), 200
    except OperationalError as e:
        logger.error(f"Database error in update_product: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in update_product: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in update_product: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# CRUD: Удаление товара (только для админа)
@app.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token, required_role='admin')
        logger.info(f'Requested product removal for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized or not an admin'}), 401
        logger.debug(f"Querying database for product {product_id}")
        product = db.session.get(Product, product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        db.session.delete(product)
        logger.debug(f"Committing deletion of product {product_id}")
        db.session.commit()
        redis_client.delete('products')
        redis_client.delete(f'product:{product_id}')
        return jsonify({'message': 'Product deleted'}), 200
    except OperationalError as e:
        logger.error(f"Database error in delete_product: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in delete_product: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in delete_product: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Получение каталога товаров
@app.route('/products', methods=['GET'])
def get_products():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        logger.info('Requested products')
        logger.debug("Checking Redis cache for products")
        cached = redis_client.get('products')
        if cached:
            logger.debug("Cache hit for products")
            return jsonify(json.loads(cached)), 200
        logger.debug("Querying database for all products")
        products = Product.query.all()
        product_list = [{'id': p.id, 'name': p.name, 'price': p.price, 'stock': p.stock} for p in products]
        logger.debug("Caching products in Redis")
        redis_client.setex('products', 300, json.dumps(product_list))
        return jsonify(product_list), 200
    except OperationalError as e:
        logger.error(f"Database error in get_products: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in get_products: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in get_products: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Получение содержимого корзины
@app.route('/cart', methods=['GET'])
def get_cart():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token)
        logger.info(f'Requested cart for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        cart_key = f'cart:{user_id}'
        logger.debug(f"Fetching cart from Redis: {cart_key}")
        cart = redis_client.get(cart_key)
        cart = json.loads(cart) if cart else {}
        return jsonify({'cart': cart}), 200
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in get_cart: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in get_cart: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Очистка корзины
@app.route('/cart', methods=['DELETE'])
def delete_cart():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token)
        logger.info(f'Requested cart removal for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        cart_key = f'cart:{user_id}'
        logger.debug(f"Deleting cart from Redis: {cart_key}")
        redis_client.delete(cart_key)
        return jsonify({'message': 'Cart deleted'}), 200
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in delete_cart: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in delete_cart: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Добавление товара в корзину
@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token)
        logger.info(f'Requested product addition in cart for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 1))
        logger.debug(f"Querying database for product {product_id}")
        product = db.session.get(Product, product_id)
        if product is None:
            return jsonify({'error': f'Product {product_id} not found'}), 404
        cart_key = f'cart:{user_id}'
        logger.debug(f"Fetching cart from Redis: {cart_key}")
        cart = redis_client.get(cart_key)
        cart = json.loads(cart) if cart else {}
        cart[str(product_id)] = cart.get(str(product_id), 0) + quantity
        logger.debug(f"Updating cart in Redis: {cart_key}")
        redis_client.setex(cart_key, 86400, json.dumps(cart))
        return jsonify({'message': 'Added to cart'}), 200
    except OperationalError as e:
        logger.error(f"Database error in add_to_cart: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in add_to_cart: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in add_to_cart: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Оформление заказа
@app.route('/order', methods=['POST'])
def create_order():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token)
        logger.info(f'Requested order for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        cart_key = f'cart:{user_id}'
        logger.debug(f"Fetching cart from Redis: {cart_key}")
        cart = redis_client.get(cart_key)
        if not cart:
            return jsonify({'error': 'Cart is empty'}), 400
        cart = json.loads(cart)
        order = Order(user_id=user_id, status='Pending')
        db.session.add(order)
        logger.debug("Committing new order to database")
        db.session.commit()
        for product_id, quantity in cart.items():
            order_item = OrderItem(order_id=order.id, product_id=int(product_id), quantity=quantity)
            db.session.add(order_item)
        logger.debug("Committing order items to database")
        db.session.commit()
        redis_client.delete(cart_key)
        # Store and publish notification for the user
        notification = json.dumps({
            'order_id': order.id,
            'status': 'Pending',
            'timestamp': int(time.time()),
            'message': f'Order {order.id} created with status Pending'
        })
        logger.debug(f"Storing notification in Redis: notifications:{user_id}")
        redis_client.lpush(f'notifications:{user_id}', notification)
        redis_client.ltrim(f'notifications:{user_id}', 0, 99)  # Keep last 100 notifications
        redis_client.publish(f'user_notifications:{user_id}', notification)
        redis_client.publish('orders', notification)
        return jsonify({'message': 'Order created', 'order_id': order.id}), 201
    except OperationalError as e:
        logger.error(f"Database error in create_order: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in create_order: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in create_order: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Обновление статуса заказа (только для админа)
@app.route('/order/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token, required_role='admin')
        logger.info(f'Requested order status edit for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized or not an admin'}), 401
        data = request.get_json()
        new_status = data.get('status')
        logger.debug(f"Querying database for order {order_id}")
        order = db.session.get(Order, order_id)
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        order.status = new_status
        logger.debug(f"Committing updated order status {new_status} for order {order_id}")
        db.session.commit()
        # Store and publish notification for the order's user
        notification = json.dumps({
            'order_id': order_id,
            'status': new_status,
            'timestamp': int(time.time()),
            'message': f'Order {order_id} status updated to {new_status}'
        })
        logger.debug(f"Storing notification in Redis: notifications:{order.user_id}")
        redis_client.lpush(f'notifications:{order.user_id}', notification)
        redis_client.ltrim(f'notifications:{order.user_id}', 0, 99)  # Keep last 100 notifications
        redis_client.publish(f'user_notifications:{order.user_id}', notification)
        redis_client.publish('orders', notification)
        return jsonify({'message': 'Status updated'}), 200
    except OperationalError as e:
        logger.error(f"Database error in update_order_status: {str(e)}")
        return jsonify({'error': 'Database connection error'}), 500
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in update_order_status: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in update_order_status: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Получение исторических уведомлений
@app.route('/notifications', methods=['GET'])
def notifications():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token)
        logger.info(f'Requested notifications for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        notifications_key = f'notifications:{user_id}'
        logger.debug(f"Fetching notifications from Redis: {notifications_key}")
        notifications = redis_client.lrange(notifications_key, 0, -1)
        if not notifications:
            return jsonify({'notifications': []}), 200
        notifications = [json.loads(notification) for notification in notifications]
        return jsonify({'notifications': notifications}), 200
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in notifications: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in notifications: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Подписка на уведомления через Pub/Sub
@app.route('/notifications/sub', methods=['GET'])
def notifications_sub():
    try:
        logger.debug(f"Received {request.method} request to {request.url}")
        token = request.headers.get('Authorization')
        user_id = check_token(token)
        logger.info(f'Requested notifications subscription for user {user_id}')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        def stream():
            logger.debug(f"Subscribing to user_notifications:{user_id}")
            pubsub = redis_client.pubsub()
            pubsub.subscribe(f'user_notifications:{user_id}')
            timeout = 30
            start_time = time.time()
            yield 'data: {"message": "Subscribed to notifications"}\n\n'
            while time.time() - start_time < timeout:
                message = pubsub.get_message(timeout=1)
                if message and message['type'] == 'message':
                    data = json.loads(message['data'])
                    logger.debug(f"Received notification: {data}")
                    yield f'data: {json.dumps(data)}\n\n'
                time.sleep(0.1)
            yield 'data: {"message": "Subscription timed out"}\n\n'
            logger.debug("Closing Pub/Sub subscription")
            pubsub.close()

        return Response(stream(), mimetype='text/event-stream')
    except RedisConnectionError as e:
        logger.error(f"Redis connection error in notifications_sub: {str(e)}")
        return jsonify({'error': 'Redis connection error'}), 500
    except Exception as e:
        logger.error(f"Error in notifications_sub: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    try:
        logger.debug("Starting application")
        with app.app_context():
            apply_migrations()  # Применяем миграции при старте
        logger.info("Application starting on 0.0.0.0:5000")
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        raise