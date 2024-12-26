import mysql.connector
from mysql.connector import Error
from fastapi import HTTPException
from .config import get_settings

settings = get_settings()

def get_db_config():
    return {
        'host': settings.DB_HOST,
        'port': settings.DB_PORT,
        'user': settings.DB_USERNAME,
        'password': settings.DB_PASSWORD,
        'database': settings.DB_DATABASE
    }

def get_db_connection():
    try:
        connection = mysql.connector.connect(**get_db_config())
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")

def init_db():
    """Initialize database tables if they don't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Create audio_processing_records table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audio_processing_records (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            process_id VARCHAR(10) NOT NULL,
            chat_id VARCHAR(100) NOT NULL,
            user_id VARCHAR(100) NOT NULL,
            audio_link TEXT NOT NULL,
            audio_text TEXT,
            text_summary TEXT,
            processed_at DATETIME NOT NULL,
            status VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_chat_user (chat_id, user_id)
        )
        """)

        # Create narrative_records table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS narrative_records (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            visit_id VARCHAR(100) NOT NULL,
            chat_id VARCHAR(100) NOT NULL,
            user_id VARCHAR(100) NOT NULL,
            narrative TEXT,
            status VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_visit (visit_id),
            INDEX idx_chat_user (chat_id, user_id)
        )
        """)
        
        conn.commit()
        print("Database tables initialized successfully")
        
    except Error as e:
        print(f"Error initializing database: {e}")
        raise HTTPException(status_code=500, detail="Database initialization error")
        
    finally:
        cursor.close()
        conn.close()