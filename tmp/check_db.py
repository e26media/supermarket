
import sqlite3

def check_stock():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, stock_qty FROM products WHERE stock_qty != ROUND(stock_qty);")
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, Name: {row[1]}, Stock: {row[2]}")
    conn.close()

if __name__ == "__main__":
    check_stock()
