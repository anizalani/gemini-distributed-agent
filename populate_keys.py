
import os
import psycopg2

def populate_keys():
    """
    Reads API keys from an environment file and populates the api_keys table in the database.
    """
    db_name = "gemini_distributed_agent"
    db_user = "rootuser"
    db_pass = "gvh!qkm0yfd6CFY4kuv"
    db_host = "localhost"
    db_port = "5432"

    keys_file = "/home/ubuntu/countrycat/gemini/credentials/gemini-api-keys.env"

    conn = None  # Initialize conn to None
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_pass,
            host=db_host,
            port=db_port
        )
        cur = conn.cursor()

        with open(keys_file, 'r') as f:
            for line in f:
                if '=' in line:
                    key_name, key_value = line.strip().split('=', 1)
                    # Check if key_name already exists
                    cur.execute("SELECT id FROM api_keys WHERE key_name = %s", (key_name,))
                    if cur.fetchone() is None:
                        cur.execute(
                            "INSERT INTO api_keys (key_name, key_value) VALUES (%s, %s)",
                            (key_name, key_value)
                        )
                        print(f"Inserted key: {key_name}")
                    else:
                        print(f"Key '{key_name}' already exists, skipping.")


        conn.commit()
        cur.close()

    except psycopg2.Error as e:
        print(f"Database error: {e}")

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    populate_keys()
