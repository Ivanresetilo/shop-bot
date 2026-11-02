import sqlite3
import time
from contextlib import contextmanager
from config import DB_PATH


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                price INTEGER NOT NULL,
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                sold INTEGER DEFAULT 0,
                order_id INTEGER,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                product_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at INTEGER NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            """
        )


def list_products():
    with db() as c:
        return c.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.sold=0) AS cnt "
            "FROM products p WHERE p.active=1 ORDER BY p.id"
        ).fetchall()


def get_product(pid):
    with db() as c:
        return c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()


def add_product(name, description, price):
    with db() as c:
        cur = c.execute(
            "INSERT INTO products (name, description, price) VALUES (?,?,?)",
            (name, description, price),
        )
        return cur.lastrowid


def deactivate_product(pid):
    with db() as c:
        c.execute("UPDATE products SET active=0 WHERE id=?", (pid,))


def add_stock(pid, content):
    with db() as c:
        c.execute("INSERT INTO stock (product_id, content) VALUES (?,?)", (pid, content))


def stock_count(pid):
    with db() as c:
        return c.execute(
            "SELECT COUNT(*) FROM stock WHERE product_id=? AND sold=0", (pid,)
        ).fetchone()[0]


def create_order(user_id, username, product_id):
    with db() as c:
        cur = c.execute(
            "INSERT INTO orders (user_id, username, product_id, created_at) VALUES (?,?,?,?)",
            (user_id, username, product_id, int(time.time())),
        )
        return cur.lastrowid


def get_order(oid):
    with db() as c:
        return c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()


def set_order_status(oid, status):
    with db() as c:
        c.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))


def take_item(pid, oid):
    """Берёт один товар со склада и привязывает к заказу."""
    with db() as c:
        row = c.execute(
            "SELECT id, content FROM stock WHERE product_id=? AND sold=0 LIMIT 1", (pid,)
        ).fetchone()
        if not row:
            return None
        c.execute("UPDATE stock SET sold=1, order_id=? WHERE id=?", (oid, row["id"]))
        return row["content"]


def pending_orders():
    with db() as c:
        return c.execute(
            "SELECT o.*, p.name AS product_name FROM orders o "
            "JOIN products p ON p.id=o.product_id WHERE o.status='pending' ORDER BY o.id"
        ).fetchall()


def stats():
    with db() as c:
        sold = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(p.price),0) FROM orders o "
            "JOIN products p ON p.id=o.product_id WHERE o.status='done'"
        ).fetchone()
        return {"sold": sold[0], "revenue": sold[1]}
