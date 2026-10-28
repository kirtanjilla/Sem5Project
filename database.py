import os
import sqlite3
import re
from downloader import get_json_filepath, download_translation, BIBLE_SOURCES

DB_PATH = os.path.join("assets", "bible_database.db")

def init_db():
    """Initializes the SQLite database schema inside the assets folder."""
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

    CREATE TABLE IF NOT EXISTS bookmarks (
        bookmark_id INTEGER PRIMARY KEY AUTOINCREMENT,
        verse_id INT,
        note TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(verse_id) REFERENCES verses(verse_id)
    );

    CREATE TABLE IF NOT EXISTS cross_references (
        ref_id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_verse_id INT,
        target_verse_id INT,
        weight REAL DEFAULT 1.0,
        FOREIGN KEY(source_verse_id) REFERENCES verses(verse_id),
        FOREIGN KEY(target_verse_id) REFERENCES verses(verse_id)
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS verse_search USING fts5(content, verse_id, translation_code, tokenize='unicode61');
    """)
    
    # Insert Languages Meta
    cursor.execute("INSERT OR IGNORE INTO languages (code, name) VALUES ('en', 'English'), ('la', 'Latin'), ('he', 'Hebrew');")
    for code, info in BIBLE_SOURCES.items():
        cursor.execute("SELECT lang_id FROM languages WHERE code = ?;", (info["lang"],))
        lang_res = cursor.fetchone()
        if lang_res:
            cursor.execute("INSERT OR IGNORE INTO translations (code, lang_id, name) VALUES (?, ?, ?);", (code, lang_res[0], info["name"]))

    # Seed sample cross-references if empty (e.g. John 1:1 <-> Genesis 1:1)
    cursor.execute("SELECT COUNT(*) FROM cross_references;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO cross_references (source_verse_id, target_verse_id, weight)
            SELECT v1.verse_id, v2.verse_id, 0.95
            FROM verses v1 JOIN books b1 ON v1.book_id = b1.book_id
            JOIN verses v2 JOIN books b2 ON v2.book_id = b2.book_id
            WHERE b1.name = 'John' AND v1.chapter = 1 AND v1.verse_number = 1
              AND b2.name = 'Genesis' AND v2.chapter = 1 AND v2.verse_number = 1;
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
    """Parses JSON data and populates SQLite database tables using high-speed bulk indexing."""
    if is_translation_populated(code):
        return True

    data = download_translation(code, progress_callback)
    if not data:
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Optimize SQLite settings for fast bulk insertion
    cursor.execute("PRAGMA synchronous = OFF;")
    cursor.execute("PRAGMA journal_mode = MEMORY;")

    source_info = BIBLE_SOURCES[code]
    cursor.execute("SELECT lang_id FROM languages WHERE code = ?;", (source_info["lang"],))
    lang_row = cursor.fetchone()
    if lang_row:
        cursor.execute("INSERT OR IGNORE INTO translations (code, lang_id, name) VALUES (?, ?, ?);", 
                       (code, lang_row[0], source_info["name"]))

    cursor.execute("SELECT translation_id FROM translations WHERE code = ?;", (code,))
    t_row = cursor.fetchone()
    if not t_row:
        conn.close()
        return False
    translation_id = t_row[0]

    progress_callback(f"Storing {code} into SQLite database...")

    # Cache book IDs in memory to avoid repeated lookups
    book_id_map = {}
    cursor.execute("SELECT name, book_id FROM books;")
    for b_name, b_id in cursor.fetchall():
        book_id_map[b_name] = b_id

    book_order = 1
    texts_to_insert = []
    fts_to_insert = []

    for book_idx, book_data in enumerate(data):
        book_name = book_data.get("name", f"Book {book_idx+1}")
        
        if book_name not in book_id_map:
            cursor.execute("INSERT OR IGNORE INTO books (name, order_index) VALUES (?, ?);", (book_name, book_order))
            cursor.execute("SELECT book_id FROM books WHERE name = ?;", (book_name,))
            res = cursor.fetchone()
            if res:
                book_id_map[book_name] = res[0]
            else:
                continue
        
        book_id = book_id_map[book_name]
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
                    texts_to_insert.append((verse_id, translation_id, verse_text))
                    fts_to_insert.append((verse_text, verse_id, code))

    # Fast batch insertions
    cursor.executemany("INSERT OR IGNORE INTO verse_texts (verse_id, translation_id, content) VALUES (?, ?, ?);", texts_to_insert)
    cursor.executemany("INSERT OR IGNORE INTO verse_search (content, verse_id, translation_code) VALUES (?, ?, ?);", fts_to_insert)
    
    conn.commit()

    # Reset PRAGMAs back to normal safety mode
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    conn.close()

    progress_callback(f"{code} successfully stored and indexed!")
    return True

def get_verse_by_coordinate(book_query, chapter, verse_number, translation_code):
    """Fetches an exact verse coordinate (e.g. Genesis 50:1)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    sql = """
        SELECT b.name, v.chapter, v.verse_number, vt.content, t.code, v.verse_id 
        FROM verses v
        JOIN books b ON v.book_id = b.book_id
        JOIN verse_texts vt ON v.verse_id = vt.verse_id
        JOIN translations t ON vt.translation_id = t.translation_id
        WHERE (LOWER(b.name) = LOWER(?) OR LOWER(b.name) LIKE LOWER(?))
          AND v.chapter = ? AND v.verse_number = ? AND t.code = ?;
    """
    cursor.execute(sql, (book_query, f"{book_query}%", chapter, verse_number, translation_code))
    row = cursor.fetchone()
    conn.close()
    if row:
        return [{"book": row[0], "chapter": row[1], "verse": row[2], "content": row[3], "translation": row[4], "verse_id": row[5]}]
    return []

def search_verses_db(query, translation_code):
    query_str = query.strip()
    
    # Check if query matches a coordinate like "Genesis 50:1" or "Gen 50:1"
    coord_match = re.match(r"^([1-3]?\s*[a-zA-Z\s]+?)\s+(\d+):(\d+)$", query_str)
    if coord_match:
        book_name = coord_match.group(1).strip()
        chapter = int(coord_match.group(2))
        verse = int(coord_match.group(3))
        res = get_verse_by_coordinate(book_name, chapter, verse, translation_code)
        if res:
            return res

    # Otherwise, execute high-speed FTS5 prefix search
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fts_query = f"{query_str}*"
    
    sql = """
        SELECT b.name, v.chapter, v.verse_number, vt.content, t.code, v.verse_id 
        FROM verse_search vs
        JOIN verse_texts vt ON vs.verse_id = vt.verse_id AND vs.translation_code = t.code
        JOIN translations t ON vt.translation_id = t.translation_id
        JOIN verses v ON vt.verse_id = v.verse_id
        JOIN books b ON v.book_id = b.book_id
        WHERE vs.translation_code = ? AND vs.content MATCH ?
        LIMIT 40;
    """
    try:
        cursor.execute(sql, (translation_code, fts_query))
        results = [{"book": row[0], "chapter": row[1], "verse": row[2], "content": row[3], "translation": row[4], "verse_id": row[5]} for row in cursor.fetchall()]
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
        SELECT v.verse_number, vt.content, v.verse_id FROM verses v
        JOIN books b ON v.book_id = b.book_id
        JOIN verse_texts vt ON v.verse_id = vt.verse_id
        JOIN translations t ON vt.translation_id = t.translation_id
        WHERE b.name = ? AND v.chapter = ? AND t.code = ?
        ORDER BY v.verse_number ASC;
    """
    cursor.execute(sql, (book_name, chapter_num, translation_code))
    results = [{"verse": row[0], "content": row[1], "verse_id": row[2]} for row in cursor.fetchall()]
    conn.close()
    return results

def get_parallel_chapter_db(book_name, chapter_num):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    sql = """
        SELECT v.verse_number, 
               MAX(CASE WHEN t.code = 'KJV' THEN vt.content END) as kjv,
               MAX(CASE WHEN t.code = 'VUL' THEN vt.content END) as vul,
               MAX(CASE WHEN t.code = 'WLC' THEN vt.content END) as wlc,
               v.verse_id
        FROM verses v
        JOIN books b ON v.book_id = b.book_id
        JOIN verse_texts vt ON v.verse_id = vt.verse_id
        JOIN translations t ON vt.translation_id = t.translation_id
        WHERE b.name = ? AND v.chapter = ?
        GROUP BY v.verse_number, v.verse_id
        ORDER BY v.verse_number ASC;
    """
    cursor.execute(sql, (book_name, chapter_num))
    results = [{"verse": row[0], "kjv": row[1], "vul": row[2], "wlc": row[3], "verse_id": row[4]} for row in cursor.fetchall()]
    conn.close()
    return results

def add_bookmark_db(verse_id, note):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO bookmarks (verse_id, note) VALUES (?, ?);", (verse_id, note))
    conn.commit()
    conn.close()

def get_bookmarks_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    sql = """
        SELECT b.name, v.chapter, v.verse_number, vt.content, bm.note, bm.bookmark_id, v.verse_id
        FROM bookmarks bm
        JOIN verses v ON bm.verse_id = v.verse_id
        JOIN books b ON v.book_id = b.book_id
        JOIN verse_texts vt ON v.verse_id = vt.verse_id
        JOIN translations t ON vt.translation_id = t.translation_id
        WHERE t.code = 'KJV'
        ORDER BY bm.timestamp DESC;
    """
    cursor.execute(sql)
    results = [{"book": row[0], "chapter": row[1], "verse": row[2], "content": row[3], "note": row[4], "bookmark_id": row[5], "verse_id": row[6]} for row in cursor.fetchall()]
    conn.close()
    return results

def remove_bookmark_db(bookmark_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bookmarks WHERE bookmark_id = ?;", (bookmark_id,))
    conn.commit()
    conn.close()

def get_cross_references_db(verse_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    sql = """
        SELECT b.name, v.chapter, v.verse_number, vt.content, cr.weight
        FROM cross_references cr
        JOIN verses v ON cr.target_verse_id = v.verse_id
        JOIN books b ON v.book_id = b.book_id
        JOIN verse_texts vt ON v.verse_id = vt.verse_id
        JOIN translations t ON vt.translation_id = t.translation_id
        WHERE cr.source_verse_id = ? AND t.code = 'KJV'
        UNION
        SELECT b.name, v.chapter, v.verse_number, vt.content, cr.weight
        FROM cross_references cr
        JOIN verses v ON cr.source_verse_id = v.verse_id
        JOIN books b ON v.book_id = b.book_id
        JOIN verse_texts vt ON v.verse_id = vt.verse_id
        JOIN translations t ON vt.translation_id = t.translation_id
        WHERE cr.target_verse_id = ? AND t.code = 'KJV';
    """
    cursor.execute(sql, (verse_id, verse_id))
    results = [{"book": row[0], "chapter": row[1], "verse": row[2], "content": row[3], "weight": row[4]} for row in cursor.fetchall()]
    conn.close()
    return results
