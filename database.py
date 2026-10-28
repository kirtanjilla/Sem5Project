import os
import sqlite3
from downloader import get_json_filepath, download_translation, BIBLE_SOURCES

DB_PATH = os.path.join("assets", "bible_database.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS languages (
        lang_id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS books (
        book_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        order_index INT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS verses (
        verse_id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INT,
        chapter INT NOT NULL,
        verse_number INT NOT NULL,
        FOREIGN KEY(book_id) REFERENCES books(book_id)
    );

    CREATE TABLE IF NOT EXISTS translations (
        translation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        lang_id INT,
        name TEXT,
        FOREIGN KEY(lang_id) REFERENCES languages(lang_id)
    );

    CREATE TABLE IF NOT EXISTS verse_texts (
        text_id INTEGER PRIMARY KEY AUTOINCREMENT,
        verse_id INT,
        translation_id INT,
        content TEXT NOT NULL,
        FOREIGN KEY(verse_id) REFERENCES verses(verse_id),
        FOREIGN KEY(translation_id) REFERENCES translations(translation_id)
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS verse_search USING fts5(content, verse_id, translation_code, tokenize='unicode61');
    """)
    
    conn.commit()
    conn.close()

def is_translation_populated(code):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM verse_texts vt
        JOIN translations t ON vt.translation_id = t.translation_id
        WHERE t.code = ?
    """, (code,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 100

def populate_database(code, progress_callback):
    if is_translation_populated(code):
        return True

    data = download_translation(code, progress_callback)
    if not data:
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Ensure translation meta exists
    source_info = BIBLE_SOURCES[code]
    cursor.execute("SELECT lang_id FROM languages WHERE code = ?;", (source_info["lang"],))
    lang_row = cursor.fetchone()
    if lang_row:
        cursor.execute("INSERT OR IGNORE INTO translations (code, lang_id, name) VALUES (?, ?, ?);", 
                       (code, lang_row[0], source_info["name"]))

    cursor.execute("SELECT translation_id FROM translations WHERE code = ?;", (code,))
    t_res = cursor.fetchone()
    translation_id = t_res[0]

    progress_callback(f"Storing {code} into SQLite database...")
    cursor.execute("BEGIN TRANSACTION;")

    book_order = 1
    for book_idx, book_data in enumerate(data):
        book_name = book_data.get("name", f"Book {book_idx+1}")
        
        cursor.execute("INSERT OR IGNORE INTO books (name, order_index) VALUES (?, ?);", (book_name, book_order))
        cursor.execute("SELECT book_id FROM books WHERE name = ?;", (book_name,))
        book_id = cursor.fetchone()[0]
        book_order += 1

        chapters = book_data.get("chapters", [])
        for chap_idx, chapter_verses in enumerate(chapters):
            chapter_num = chap_idx + 1
            
            for verse_idx, verse_text in enumerate(chapter_verses):
                verse_num = verse_idx + 1
                if not verse_text:
                    continue
                
                cursor.execute("""
                    INSERT INTO verses (book_id, chapter, verse_number) 
                    SELECT ?, ?, ? 
                    WHERE NOT EXISTS (
                        SELECT 1 FROM verses WHERE book_id = ? AND chapter = ? AND verse_number = ?
                    );
                """, (book_id, chapter_num, verse_num, book_id, chapter_num, verse_num))

                cursor.execute("SELECT verse_id FROM verses WHERE book_id = ? AND chapter = ? AND verse_number = ?;", 
                               (book_id, chapter_num, verse_num))
                v_res = cursor.fetchone()
                if v_res:
                    verse_id = v_res[0]
                    cursor.execute("INSERT OR IGNORE INTO verse_texts (verse_id, translation_id, content) VALUES (?, ?, ?);", 
                                   (verse_id, translation_id, verse_text))
                    cursor.execute("INSERT OR IGNORE INTO verse_search (content, verse_id, translation_code) VALUES (?, ?, ?);", 
                                   (verse_text, verse_id, code))

    conn.commit()
    conn.close()
    progress_callback(f"{code} successfully stored and indexed!")
    return True

def search_verses_db(query, translation_code):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fts_query = f"{query.strip()}*"
    
    sql = """
        SELECT b.name, v.chapter, v.verse_number, vt.content, t.code 
        FROM verse_search vs
        JOIN verse_texts vt ON vs.verse_id = vt.verse_id AND vs.translation_code = t.code
        JOIN translations t ON vt.translation_id = t.translation_id
        JOIN verses v ON vt.verse_id = v.verse_id
        JOIN books b ON v.book_id = b.book_id
        WHERE vs.translation_code = ? AND vs.content MATCH ?
        LIMIT 50;
    """
    try:
        cursor.execute(sql, (translation_code, fts_query))
        results = [{"book": row[0], "chapter": row[1], "verse": row[2], "content": row[3], "translation": row[4]} for row in cursor.fetchall()]
        return results
    except Exception as e:
        return []
    finally:
        conn.close()

def get_all_books():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM books ORDER BY order_index ASC;")
    books = [row[0] for row in cursor.fetchall()]
    conn.close()
    return books

def get_chapters_for_book(book_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT v.chapter FROM verses v
        JOIN books b ON v.book_id = b.book_id
        WHERE b.name = ?
        ORDER BY v.chapter ASC;
    """, (book_name,))
    chapters = [row[0] for row in cursor.fetchall()]
    conn.close()
    return chapters

def get_chapter_verses_db(book_name, chapter_num, translation_code):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    sql = """
        SELECT v.verse_number, vt.content FROM verses v
        JOIN books b ON v.book_id = b.book_id
        JOIN verse_texts vt ON v.verse_id = vt.verse_id
        JOIN translations t ON vt.translation_id = t.translation_id
        WHERE b.name = ? AND v.chapter = ? AND t.code = ?
        ORDER BY v.verse_number ASC;
    """
    cursor.execute(sql, (book_name, chapter_num, translation_code))
    results = [{"verse": row[0], "content": row[1]} for row in cursor.fetchall()]
    conn.close()
    return results
