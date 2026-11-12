import sqlite3

DB_FILE = "vulnshop.db"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def setup():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS users")
    cur.execute("DROP TABLE IF EXISTS products")
    cur.execute("DROP TABLE IF EXISTS orders")

    cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            token TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            total REAL NOT NULL,
            shipping_address TEXT NOT NULL
        )
    """)

    users = [
        (1, "Goutham", "goutham@example.in", "token-goutham"),
        (2, "Kumar",   "kumar@example.in",   "token-kumar"),
        (3, "Martin",  "martin@example.in",  "token-martin"),
    ]
    cur.executemany("INSERT INTO users VALUES (?, ?, ?, ?)", users)

    products = [
        (1, "Wireless Mouse", 1499.00),
        (2, "Mechanical Keyboard", 4999.00),
        (3, "USB-C Hub", 1899.00),
    ]
    cur.executemany("INSERT INTO products VALUES (?, ?, ?)", products)

    orders = [
        (101, 1, 1, 1499.00, "14 Anna Nagar, Chennai 600040"),
        (102, 2, 2, 4999.00, "27 R.S. Puram, Coimbatore 641002"),
        (103, 3, 3, 1899.00, "8 Bandra West, Mumbai 400050"),
    ]
    cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)

    conn.commit()
    conn.close()
