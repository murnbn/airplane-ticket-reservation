import mysql.connector

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  
    'database': 'project2',
    'port': 3307,
    'auth_plugin': 'mysql_native_password'
}

try:
    conn = mysql.connector.connect(**db_config)
    if conn.is_connected():
        print("✅ Successfully connected to the database!")
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES;")
        print("Tables in project2:", [t[0] for t in cursor.fetchall()])
except mysql.connector.Error as err:
    print(f"Database connection error: {err}")
finally:
    if 'conn' in locals() and conn.is_connected():
        conn.close()
