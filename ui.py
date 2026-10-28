import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from database import (
    init_db, is_translation_populated, populate_database, 
    search_verses_db, get_all_books, get_chapters_for_book, 
    get_chapter_verses_db, get_parallel_chapter_db, 
    add_bookmark_db, get_bookmarks_db, remove_bookmark_db, get_cross_references_db
)
from downloader import BIBLE_SOURCES

class BibleAppUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Sacred Text Explorer")
        self.root.geometry("1050x780")
        
        # Modern Light Theme Palette
        self.bg_color = "#f8f6f0"       # Warm clean parchment cream
        self.card_bg = "#ffffff"        # Crisp white for cards
        self.gold_accent = "#b45309"    # Rich golden amber
        self.text_color = "#1e293b"     # Deep slate readable text
        self.sub_text = "#64748b"       # Muted gray text
        self.border_color = "#e2e8f0"   # Soft border gray

        self.root.config(bg=self.bg_color)
        
        init_db()
        self.current_mode = "search"
        self.render_job = None          # Tracks background rendering loops
        self.create_widgets()
        
        # Load default KJV in background thread to keep startup instant
        self.root.after(200, lambda: self.check_and_load("KJV"))

    def create_widgets(self):
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=12)
        header_frame.pack(fill=tk.X, padx=30)
        
        tk.Label(header_frame, text="SACRED TEXT EXPLORER", font=("Georgia", 18, "bold"), fg=self.gold_accent, bg=self.bg_color).pack(anchor="w")
        self.status_label = tk.Label(header_frame, text="Ready", font=("Arial", 9), fg=self.sub_text, bg=self.bg_color)
        self.status_label.pack(anchor="w", pady=(2, 0))

        # Navigation Bar
        top_bar = tk.Frame(self.root, bg=self.card_bg, padx=15, pady=10, highlightbackground=self.border_color, highlightthickness=1)
        top_bar.pack(fill=tk.X, padx=30, pady=(0, 12))

        self.btn_search = tk.Button(top_bar, text="🔍 Search", command=lambda: self.switch_mode("search"), bg=self.gold_accent, fg="#ffffff", font=("Arial", 9, "bold"), relief=tk.FLAT, padx=12, pady=5, cursor="hand2")
        self.btn_search.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_reader = tk.Button(top_bar, text="📖 Reader", command=lambda: self.switch_mode("reader"), bg="#e2e8f0", fg=self.text_color, font=("Arial", 9, "bold"), relief=tk.FLAT, padx=12, pady=5, cursor="hand2")
        self.btn_reader.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_parallel = tk.Button(top_bar, text="⚖️ Parallel View", command=lambda: self.switch_mode("parallel"), bg="#e2e8f0", fg=self.text_color, font=("Arial", 9, "bold"), relief=tk.FLAT, padx=12, pady=5, cursor="hand2")
        self.btn_parallel.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_bookmarks = tk.Button(top_bar, text="⭐ Bookmarks", command=lambda: self.switch_mode("bookmarks"), bg="#e2e8f0", fg=self.text_color, font=("Arial", 9, "bold"), relief=tk.FLAT, padx=12, pady=5, cursor="hand2")
        self.btn_bookmarks.pack(side=tk.LEFT, padx=(0, 20))

        # Translation Selector
        tk.Label(top_bar, text="Translation:", font=("Arial", 9, "bold"), fg=self.sub_text, bg=self.card_bg).pack(side=tk.LEFT, padx=(0, 5))
        self.trans_var = tk.StringVar(value="KJV")
        self.trans_dropdown = ttk.Combobox(top_bar, textvariable=self.trans_var, values=list(BIBLE_SOURCES.keys()), state="readonly", width=8, font=("Arial", 9))
        self.trans_dropdown.pack(side=tk.LEFT)
        self.trans_dropdown.bind("<<ComboboxSelected>>", self.on_translation_switch)

        # Dynamic Controls Container
        self.control_container = tk.Frame(self.root, bg=self.bg_color)
        self.control_container.pack(fill=tk.X, padx=30, pady=(0, 12))
        self.setup_search_controls()

        # Results Scrollable Container
        container = tk.Frame(self.root, bg=self.bg_color)
        container.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 25))

        self.canvas = tk.Canvas(container, bg=self.bg_color, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        
        self.results_frame = tk.Frame(self.canvas, bg=self.bg_color)
        self.results_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas_window = self.canvas.create_window((0, 0), window=self.results_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.bind_mouse_scroll(self.canvas)
        self.bind_mouse_scroll(self.results_frame)

    def switch_mode(self, mode):
        self.current_mode = mode
        for btn, m in [(self.btn_search, "search"), (self.btn_reader, "reader"), (self.btn_parallel, "parallel"), (self.btn_bookmarks, "bookmarks")]:
            btn.config(bg=self.gold_accent if m == mode else "#e2e8f0", fg="#ffffff" if m == mode else self.text_color)

        for widget in self.control_container.winfo_children():
            widget.destroy()

        if mode == "search":
            self.setup_search_controls()
            self.perform_search()
        elif mode == "reader":
            self.setup_reader_controls()
            self.load_chapter_page()
        elif mode == "parallel":
            self.setup_reader_controls()
            self.load_parallel_page()
        elif mode == "bookmarks":
            self.load_bookmarks_page()

    def setup_search_controls(self):
        frame = tk.Frame(self.control_container, bg=self.card_bg, padx=15, pady=12, highlightbackground=self.border_color, highlightthickness=1)
        frame.pack(fill=tk.X)

        self.search_entry = tk.Entry(frame, font=("Arial", 11), bg="#fcfbf9", fg=self.text_color, insertbackground=self.gold_accent, relief=tk.FLAT)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 15), ipady=6)
        self.search_entry.insert(0, "grace")
        self.search_entry.bind("<Return>", lambda event: self.perform_search())

        tk.Button(frame, text="Search", command=self.perform_search, bg=self.gold_accent, fg="#ffffff", font=("Arial", 9, "bold"), relief=tk.FLAT, padx=15, pady=6, cursor="hand2").pack(side=tk.LEFT)

    def setup_reader_controls(self):
        frame = tk.Frame(self.control_container, bg=self.card_bg, padx=15, pady=12, highlightbackground=self.border_color, highlightthickness=1)
        frame.pack(fill=tk.X)

        tk.Label(frame, text="Book:", font=("Arial", 9, "bold"), fg=self.text_color, bg=self.card_bg).pack(side=tk.LEFT, padx=(0, 5))
        books = get_all_books() or ["Genesis", "John"]
        self.book_var = tk.StringVar(value=books[0])
        self.book_dropdown = ttk.Combobox(frame, textvariable=self.book_var, values=books, state="readonly", width=14, font=("Arial", 9))
        self.book_dropdown.pack(side=tk.LEFT, padx=(0, 15))
        self.book_dropdown.bind("<<ComboboxSelected>>", self.on_book_change)

        tk.Label(frame, text="Chapter:", font=("Arial", 9, "bold"), fg=self.text_color, bg=self.card_bg).pack(side=tk.LEFT, padx=(0, 5))
        chapters = get_chapters_for_book(books[0]) or [1]
        self.chap_var = tk.StringVar(value=str(chapters[0]))
        self.chap_dropdown = ttk.Combobox(frame, textvariable=self.chap_var, values=chapters, state="readonly", width=5, font=("Arial", 9))
        self.chap_dropdown.pack(side=tk.LEFT, padx=(0, 15))
        self.chap_dropdown.bind("<<ComboboxSelected>>", lambda e: self.refresh_current_view())

        tk.Button(frame, text="Load", command=self.refresh_current_view, bg=self.gold_accent, fg="#ffffff", font=("Arial", 9, "bold"), relief=tk.FLAT, padx=15, pady=6, cursor="hand2").pack(side=tk.LEFT)

    def on_book_change(self, event):
        chapters = get_chapters_for_book(self.book_var.get())
        self.chap_dropdown['values'] = chapters
        if chapters:
            self.chap_var.set(str(chapters[0]))
        self.refresh_current_view()

    def refresh_current_view(self):
        if self.current_mode == "reader":
            self.load_chapter_page()
        elif self.current_mode == "parallel":
            self.load_parallel_page()

    def bind_mouse_scroll(self, widget):
        widget.bind("<MouseWheel>", self._on_mouse_wheel, add="+")
        widget.bind("<Button-4>", self._on_mouse_wheel, add="+")
        widget.bind("<Button-5>", self._on_mouse_wheel, add="+")

    def _on_mouse_wheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")

    def update_status(self, text):
        self.root.after(0, lambda: self.status_label.config(text=text))

    def check_and_load(self, code):
        if not is_translation_populated(code):
            self.update_status(f"Downloading {BIBLE_SOURCES[code]['name']}...")
            def background_download():
                success = populate_database(code, self.update_status)
                self.root.after(0, lambda: self.finish_loading(code, success))
            threading.Thread(target=background_download, daemon=True).start()
        else:
            self.update_status(f"Loaded: {BIBLE_SOURCES[code]['name']}")
            self.perform_search()

    def finish_loading(self, code, success):
        if success:
            self.update_status(f"Loaded: {BIBLE_SOURCES[code]['name']}")
            self.perform_search()
        else:
            messagebox.showerror("Error", f"Failed to download {code}.")

    def on_translation_switch(self, event):
        self.check_and_load(self.trans_var.get())

    def clear_results(self):
        """Cancels any pending batch rendering jobs and clears the screen instantly."""
        if self.render_job:
            self.root.after_cancel(self.render_job)
            self.render_job = None
        for w in self.results_frame.winfo_children():
            w.destroy()

    def stream_render(self, items, render_func, batch_size=15):
        """Streams items onto the UI in micro-batches to prevent freezing."""
        self.clear_results()
        iterator = iter(items)

        def batch():
            try:
                for _ in range(batch_size):
                    item = next(iterator)
                    render_func(item)
                self.render_job = self.root.after(5, batch)
            except StopIteration:
                self.render_job = None

        self.render_job = self.root.after(1, batch)

    def perform_search(self):
        query = self.search_entry.get().strip()
        if len(query) < 2:
            self.clear_results()
            return

        results = search_verses_db(query, self.trans_var.get())
        if not results:
            self.clear_results()
            tk.Label(self.results_frame, text="No matching verses found.", font=("Georgia", 11, "italic"), fg=self.sub_text, bg=self.bg_color).pack(pady=30)
            return

        self.stream_render(results, lambda res: self.render_verse_card(
            res['book'], res['chapter'], res['verse'], res['content'], res['translation'], res['verse_id']
        ))

    def load_chapter_page(self):
        book = self.book_var.get() if hasattr(self, 'book_var') else "Genesis"
        chap = int(self.chap_var.get()) if hasattr(self, 'chap_var') else 1
        verses = get_chapter_verses_db(book, chap, self.trans_var.get())

        if not verses:
            self.clear_results()
            tk.Label(self.results_frame, text="No verses found for this chapter.", font=("Georgia", 11, "italic"), fg=self.sub_text, bg=self.bg_color).pack(pady=30)
            return

        self.stream_render(verses, lambda v: self.render_verse_card(
            book, chap, v['verse'], v['content'], self.trans_var.get(), v['verse_id']
        ))

    def load_parallel_page(self):
        book = self.book_var.get() if hasattr(self, 'book_var') else "Genesis"
        chap = int(self.chap_var.get()) if hasattr(self, 'chap_var') else 1
        verses = get_parallel_chapter_db(book, chap)

        if not verses:
            self.clear_results()
            tk.Label(self.results_frame, text="No parallel verses available.", font=("Georgia", 11, "italic"), fg=self.sub_text, bg=self.bg_color).pack(pady=30)
            return

        def render_parallel(v):
            card = tk.Frame(self.results_frame, bg=self.card_bg, padx=15, pady=12, highlightbackground=self.border_color, highlightthickness=1)
            card.pack(fill=tk.X, pady=5)
            self.bind_mouse_scroll(card)

            tk.Label(card, text=f"{book} {chap}:{v['verse']}", font=("Arial", 10, "bold"), fg=self.gold_accent, bg=self.card_bg).pack(anchor="w", pady=(0, 4))
            
            for lang, text in [("English (KJV)", v['kjv']), ("Latin (Vulgate)", v['vul']), ("Hebrew (WLC)", v['wlc'])]:
                if text:
                    row = tk.Frame(card, bg=self.card_bg, pady=2)
                    row.pack(fill=tk.X)
                    tk.Label(row, text=f"[{lang}]: ", font=("Arial", 9, "bold"), fg=self.sub_text, bg=self.card_bg, width=15, anchor="w").pack(side=tk.LEFT)
                    tk.Label(row, text=text, font=("Georgia", 11), fg=self.text_color, bg=self.card_bg, wraplength=750, justify="left").pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.stream_render(verses, render_parallel)

    def load_bookmarks_page(self):
        bookmarks = get_bookmarks_db()

        if not bookmarks:
            self.clear_results()
            tk.Label(self.results_frame, text="No bookmarked verses yet.", font=("Georgia", 11, "italic"), fg=self.sub_text, bg=self.bg_color).pack(pady=40)
            return

        def render_bookmark(bm):
            card = tk.Frame(self.results_frame, bg=self.card_bg, padx=15, pady=12, highlightbackground=self.border_color, highlightthickness=1)
            card.pack(fill=tk.X, pady=6)
            self.bind_mouse_scroll(card)

            header_row = tk.Frame(card, bg=self.card_bg)
            header_row.pack(fill=tk.X, pady=(0, 4))
            tk.Label(header_row, text=f"{bm['book']} {bm['chapter']}:{bm['verse']}", font=("Arial", 10, "bold"), fg=self.gold_accent, bg=self.card_bg).pack(side=tk.LEFT)
            
            tk.Button(header_row, text="Remove", command=lambda b_id=bm['bookmark_id']: self.delete_bookmark(b_id), bg="#ef4444", fg="#ffffff", font=("Arial", 8), relief=tk.FLAT, padx=8, pady=2).pack(side=tk.RIGHT)

            tk.Label(card, text=bm['content'], font=("Georgia", 11), fg=self.text_color, bg=self.card_bg, wraplength=800, justify="left").pack(anchor="w", pady=(2, 6))
            if bm['note']:
                tk.Label(card, text=f"Note: {bm['note']}", font=("Arial", 9, "italic"), fg=self.gold_accent, bg=self.card_bg).pack(anchor="w")

        self.stream_render(bookmarks, render_bookmark)

    def render_verse_card(self, book, chapter, verse_num, content, trans, verse_id):
        card = tk.Frame(self.results_frame, bg=self.card_bg, padx=15, pady=12, highlightbackground=self.border_color, highlightthickness=1)
        card.pack(fill=tk.X, pady=5)
        self.bind_mouse_scroll(card)

        top_row = tk.Frame(card, bg=self.card_bg)
        top_row.pack(fill=tk.X, pady=(0, 4))

        tk.Label(top_row, text=f"{book} {chapter}:{verse_num} ({trans})", font=("Arial", 10, "bold"), fg=self.gold_accent, bg=self.card_bg).pack(side=tk.LEFT)

        btn_frame = tk.Frame(top_row, bg=self.card_bg)
        btn_frame.pack(side=tk.RIGHT)

        tk.Button(btn_frame, text="🔗 Cross-Refs", command=lambda v_id=verse_id: self.show_cross_references(v_id), bg="#e2e8f0", fg=self.text_color, font=("Arial", 8), relief=tk.FLAT, padx=6, pady=2).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="⭐ Bookmark", command=lambda v_id=verse_id: self.bookmark_verse(v_id), bg="#e2e8f0", fg=self.text_color, font=("Arial", 8), relief=tk.FLAT, padx=6, pady=2).pack(side=tk.LEFT)

        tk.Label(card, text=content, font=("Georgia", 11), fg=self.text_color, bg=self.card_bg, wraplength=830, justify="left").pack(anchor="w")

    def bookmark_verse(self, verse_id):
        note = simpledialog.askstring("Add Bookmark", "Enter a personal note or reflection (optional):", parent=self.root)
        if note is not None:
            add_bookmark_db(verse_id, note)
            messagebox.showinfo("Success", "Verse bookmarked successfully!")

    def delete_bookmark(self, bookmark_id):
        remove_bookmark_db(bookmark_id)
        self.load_bookmarks_page()

    def show_cross_references(self, verse_id):
        refs = get_cross_references_db(verse_id)
        popup = tk.Toplevel(self.root)
        popup.title("Cross-Reference Explorer")
        popup.geometry("600x400")
        popup.config(bg=self.bg_color)

        tk.Label(popup, text="Connected Cross-References", font=("Georgia", 14, "bold"), fg=self.gold_accent, bg=self.bg_color).pack(pady=10)

        if not refs:
            tk.Label(popup, text="No cross-references found for this verse.", font=("Georgia", 10, "italic"), fg=self.sub_text, bg=self.bg_color).pack(pady=20)
            return

        frame = tk.Frame(popup, bg=self.bg_color)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        for r in refs:
            card = tk.Frame(frame, bg=self.card_bg, padx=10, pady=8, highlightbackground=self.border_color, highlightthickness=1)
            card.pack(fill=tk.X, pady=4)
            tk.Label(card, text=f"{r['book']} {r['chapter']}:{r['verse']} (Weight: {r['weight']})", font=("Arial", 9, "bold"), fg=self.gold_accent, bg=self.card_bg).pack(anchor="w")
            tk.Label(card, text=r['content'], font=("Georgia", 10), fg=self.text_color, bg=self.card_bg, wraplength=530, justify="left").pack(anchor="w")
