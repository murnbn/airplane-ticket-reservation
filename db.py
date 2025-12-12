import mysql.connector

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'project2',
    'port': 3307,
    'auth_plugin': 'mysql_native_password'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        print("✅ Connected successfully!")
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to DB: {err}")
        return None

