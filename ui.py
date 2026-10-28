import threading
import tkinter as tk
from tkinter import ttk, messagebox
from database import (
    init_db, is_translation_populated, populate_database, 
    search_verses_db, get_all_books, get_chapters_for_book, get_chapter_verses_db
)
from downloader import BIBLE_SOURCES

class BibleAppUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Sacred Text Explorer")
        self.root.geometry("1000x750")
        
        # Modern Light Theme Palette
        self.bg_color = "#f8f6f0"       # Warm clean parchment cream
        self.card_bg = "#ffffff"        # Crisp white for cards
        self.gold_accent = "#b45309"    # Rich golden amber
        self.text_color = "#1e293b"     # Deep slate readable text
        self.sub_text = "#64748b"       # Muted gray text
        self.border_color = "#e2e8f0"   # Soft border gray

        self.root.config(bg=self.bg_color)
        
        init_db()
        self.current_mode = "search"    # 'search' or 'reader'
        self.create_widgets()
        
        # Load default KJV on startup in background thread
        self.root.after(300, lambda: self.check_and_load("KJV"))

    def create_widgets(self):
        # Header Frame
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=15)
        header_frame.pack(fill=tk.X, padx=30)
        
        title_label = tk.Label(header_frame, text="SACRED TEXT EXPLORER", font=("Georgia", 18, "bold"), fg=self.gold_accent, bg=self.bg_color)
        title_label.pack(anchor="w")
        
        self.status_label = tk.Label(header_frame, text="Ready", font=("Arial", 9), fg=self.sub_text, bg=self.bg_color)
        self.status_label.pack(anchor="w", pady=(2, 0))

        # Mode Selector & Translation Bar
        top_bar = tk.Frame(self.root, bg=self.card_bg, padx=20, pady=12, highlightbackground=self.border_color, highlightthickness=1)
        top_bar.pack(fill=tk.X, padx=30, pady=(0, 15))

        # Mode Buttons
        self.search_mode_btn = tk.Button(top_bar, text="🔍 Corpus Search", command=lambda: self.switch_mode("search"), bg=self.gold_accent, fg="#ffffff", font=("Arial", 10, "bold"), relief=tk.FLAT, padx=15, pady=6, cursor="hand2")
        self.search_mode_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.reader_mode_btn = tk.Button(top_bar, text="📖 Book Reader", command=lambda: self.switch_mode("reader"), bg="#e2e8f0", fg=self.text_color, font=("Arial", 10, "bold"), relief=tk.FLAT, padx=15, pady=6, cursor="hand2")
        self.reader_mode_btn.pack(side=tk.LEFT, padx=(0, 20))

        # Translation Selector (Shared across modes)
        tk.Label(top_bar, text="Translation:", font=("Arial", 9, "bold"), fg=self.sub_text, bg=self.card_bg).pack(side=tk.LEFT, padx=(0, 5))
        self.trans_var = tk.StringVar(value="KJV")
        self.trans_dropdown = ttk.Combobox(top_bar, textvariable=self.trans_var, values=list(BIBLE_SOURCES.keys()), state="readonly", width=8, font=("Arial", 10))
        self.trans_dropdown.pack(side=tk.LEFT)
        self.trans_dropdown.bind("<<ComboboxSelected>>", self.on_translation_switch)

        # Dynamic Content Control Frame (Changes based on mode)
        self.control_container = tk.Frame(self.root, bg=self.bg_color)
        self.control_container.pack(fill=tk.X, padx=30, pady=(0, 15))
        self.setup_search_controls()

        # Results Scrollable Container
        container = tk.Frame(self.root, bg=self.bg_color)
        container.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 30))

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
        for widget in self.control_container.winfo_children():
            widget.destroy()

        if mode == "search":
            self.search_mode_btn.config(bg=self.gold_accent, fg="#ffffff")
            self.reader_mode_btn.config(bg="#e2e8f0", fg=self.text_color)
            self.setup_search_controls()
            self.perform_search()
        else:
            self.reader_mode_btn.config(bg=self.gold_accent, fg="#ffffff")
            self.search_mode_btn.config(bg="#e2e8f0", fg=self.text_color)
            self.setup_reader_controls()
            self.load_chapter_page()

    def setup_search_controls(self):
        frame = tk.Frame(self.control_container, bg=self.card_bg, padx=20, pady=15, highlightbackground=self.border_color, highlightthickness=1)
        frame.pack(fill=tk.X)

        self.search_entry = tk.Entry(frame, font=("Arial", 11), bg="#fcfbf9", fg=self.text_color, insertbackground=self.gold_accent, relief=tk.FLAT)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 15), ipady=8)
        self.search_entry.insert(0, "grace")
        self.search_entry.bind("<Return>", lambda event: self.perform_search())

        self.search_btn = tk.Button(frame, text="Search Verses", command=self.perform_search, bg=self.gold_accent, fg="#ffffff", font=("Arial", 10, "bold"), relief=tk.FLAT, padx=20, pady=8, cursor="hand2")
        self.search_btn.pack(side=tk.LEFT)

    def setup_reader_controls(self):
        frame = tk.Frame(self.control_container, bg=self.card_bg, padx=20, pady=15, highlightbackground=self.border_color, highlightthickness=1)
        frame.pack(fill=tk.X)

        tk.Label(frame, text="Book:", font=("Arial", 10, "bold"), fg=self.text_color, bg=self.card_bg).pack(side=tk.LEFT, padx=(0, 5))
        
        books = get_all_books()
        if not books:
            books = ["Genesis", "John"]

        self.book_var = tk.StringVar(value=books[0])
        self.book_dropdown = ttk.Combobox(frame, textvariable=self.book_var, values=books, state="readonly", width=15, font=("Arial", 10))
        self.book_dropdown.pack(side=tk.LEFT, padx=(0, 20))
        self.book_dropdown.bind("<<ComboboxSelected>>", self.on_book_change)

        tk.Label(frame, text="Chapter:", font=("Arial", 10, "bold"), fg=self.text_color, bg=self.card_bg).pack(side=tk.LEFT, padx=(0, 5))
        
        chapters = get_chapters_for_book(books[0])
        if not chapters:
            chapters = [1]

        self.chap_var = tk.StringVar(value=str(chapters[0]))
        self.chap_dropdown = ttk.Combobox(frame, textvariable=self.chap_var, values=chapters, state="readonly", width=6, font=("Arial", 10))
        self.chap_dropdown.pack(side=tk.LEFT, padx=(0, 20))
        self.chap_dropdown.bind("<<ComboboxSelected>>", lambda e: self.load_chapter_page())

        load_btn = tk.Button(frame, text="Read Chapter Page", command=self.load_chapter_page, bg=self.gold_accent, fg="#ffffff", font=("Arial", 10, "bold"), relief=tk.FLAT, padx=20, pady=8, cursor="hand2")
        load_btn.pack(side=tk.LEFT)

    def on_book_change(self, event):
        book = self.book_var.get()
        chapters = get_chapters_for_book(book)
        self.chap_dropdown['values'] = chapters
        if chapters:
            self.chap_var.set(str(chapters[0]))
        self.load_chapter_page()

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
            self.update_status(f"Downloading {BIBLE_SOURCES[code]['name']} into assets...")
            def background_download():
                success = populate_database(code, self.update_status)
                self.root.after(0, lambda: self.finish_loading(code, success))
            threading.Thread(target=background_download, daemon=True).start()
        else:
            self.update_status(f"Loaded: {BIBLE_SOURCES[code]['name']} (From assets/)")
            if self.current_mode == "search":
                self.perform_search()
            else:
                self.load_chapter_page()

    def finish_loading(self, code, success):
        if success:
            self.update_status(f"Loaded: {BIBLE_SOURCES[code]['name']} (Stored in assets/)")
            if self.current_mode == "search":
                self.perform_search()
            else:
                self.load_chapter_page()
        else:
            messagebox.showerror("Error", f"Failed to download or store {code}.")

    def on_translation_switch(self, event):
        code = self.trans_var.get()
        self.check_and_load(code)

    def perform_search(self):
        query = self.search_entry.get().strip()
        translation = self.trans_var.get()

        for widget in self.results_frame.winfo_children():
            widget.destroy()

        if len(query) < 2:
            messagebox.showwarning("Input Error", "Please enter at least 2 characters to search.")
            return

        results = search_verses_db(query, translation)

        if not results:
            tk.Label(self.results_frame, text="No matching verses found in database assets.", font=("Georgia", 11, "italic"), fg=self.sub_text, bg=self.bg_color).pack(pady=40)
            return

        for res in results:
            card = tk.Frame(self.results_frame, bg=self.card_bg, padx=18, pady=14, highlightbackground=self.border_color, highlightthickness=1)
            card.pack(fill=tk.X, pady=6)
            self.bind_mouse_scroll(card)

            meta_text = f"{res['book']} {res['chapter']}:{res['verse']}  •  {res['translation']}"
            tk.Label(card, text=meta_text, font=("Arial", 10, "bold"), fg=self.gold_accent, bg=self.card_bg).pack(anchor="w")
            
            content_lbl = tk.Label(card, text=res['content'], font=("Georgia", 12), fg=self.text_color, bg=self.card_bg, wraplength=850, justify="left")
            content_lbl.pack(anchor="w", pady=(6, 0))
            self.bind_mouse_scroll(content_lbl)

    def load_chapter_page(self):
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        book = getattr(self, 'book_var', None)
        chap = getattr(self, 'chap_var', None)
        
        book_name = book.get() if book else "Genesis"
        chap_num = int(chap.get()) if chap else 1
        translation = self.trans_var.get()

        verses = get_chapter_verses_db(book_name, chap_num, translation)

        if not verses:
            tk.Label(self.results_frame, text="No verses found for this chapter.", font=("Georgia", 11, "italic"), fg=self.sub_text, bg=self.bg_color).pack(pady=40)
            return

        # Chapter Page Header Container
        page_header = tk.Frame(self.results_frame, bg=self.card_bg, padx=25, pady=20, highlightbackground=self.border_color, highlightthickness=1)
        page_header.pack(fill=tk.X, pady=(0, 15))
        tk.Label(page_header, text=f"{book_name} — Chapter {chap_num}", font=("Georgia", 16, "bold"), fg=self.gold_accent, bg=self.card_bg).pack()

        # Render verses sequentially in Bible-like format
        for v in verses:
            v_card = tk.Frame(self.results_frame, bg=self.card_bg, padx=25, pady=12, highlightbackground=self.border_color, highlightthickness=1)
            v_card.pack(fill=tk.X, pady=4)
            self.bind_mouse_scroll(v_card)

            # Verse number superscript-style indicator with golden text
            verse_num_lbl = tk.Label(v_card, text=f"[{v['verse']}]", font=("Arial", 10, "bold"), fg=self.gold_accent, bg=self.card_bg, width=4, anchor="w")
            verse_num_lbl.pack(side=tk.LEFT, anchor="n")

            verse_text_lbl = tk.Label(v_card, text=v['content'], font=("Georgia", 12), fg=self.text_color, bg=self.card_bg, wraplength=800, justify="left")
            verse_text_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.bind_mouse_scroll(verse_text_lbl)
