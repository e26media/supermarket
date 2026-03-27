
import sqlite3

def fix_db():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # 1. Identify non-integer values
    cursor.execute("SELECT id, name, stock_qty, min_stock_alert FROM products WHERE stock_qty != ROUND(stock_qty) OR min_stock_alert != ROUND(min_stock_alert);")
    rows = cursor.fetchall()
    
    if not rows:
        print("No non-integer values found in database.")
        conn.close()
        return

    print(f"Found {len(rows)} records with non-integer stock values.")
    
    # 2. Update values to rounded integers
    for row in rows:
        pid, name, stock, alert = row
        new_stock = int(round(float(stock)))
        new_alert = int(round(float(alert)))
        print(f"Fixing ID {pid} ({name}): Stock {stock} -> {new_stock}, Alert {alert} -> {new_alert}")
        cursor.execute("UPDATE products SET stock_qty = ?, min_stock_alert = ? WHERE id = ?;", (new_stock, new_alert, pid))
    
    conn.commit()
    print("Database fix completed successfully.")
    conn.close()

if __name__ == "__main__":
    fix_db()
