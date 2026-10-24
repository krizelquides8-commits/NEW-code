import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import hashlib
import hmac
import secrets
import os
import base64
import io
import csv
import json
import shutil
import time
import importlib
from datetime import datetime, timedelta

# optional libraries, di mag-crash kung wala
try:
    Image = importlib.import_module("PIL.Image")
    ImageDraw = importlib.import_module("PIL.ImageDraw")
    ImageFont = importlib.import_module("PIL.ImageFont")
    ImageTk = importlib.import_module("PIL.ImageTk")
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    qrcode = importlib.import_module("qrcode")
    HAS_QR = True
except ImportError:
    HAS_QR = False

# kunin yung logo galing sa lumang file kung andun
try:
    _login_app = importlib.import_module("cafe_login_app")
    _LOGO_B64 = getattr(_login_app, "_LOGO_B64", None)
except Exception:
    _LOGO_B64 = None

# ---------- settings ----------
SHOP_NAME = "Kapehan ni Bads"
TAGLINE = "Coffee, Pastries, and Sweets"
MAX_CHARS = 20
LOW_STOCK_LEVEL = 5
MAX_TRIES = 5
LOCK_SECS = 30
GCASH_NO = "0912 345 6789"  # palitan mo ng totoong number

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "users.db")
IMG_DIR = os.path.join(HERE, "product_images")
os.makedirs(IMG_DIR, exist_ok=True)

QUESTIONS = [
    "What City Were You Born in?",
    "What Is Your Favorite Color?",
    "What Was The Name of Your First Pet?",
]
BASE_CATEGORIES = ["Coffee", "Pastry", "Tea", "Bread"]

COL = {
    "dark": "#2b1608", "bg": "#f6efe3", "white": "#ffffff", "field": "#faf6ee",
    "orange": "#d9822b", "orange2": "#b96a1a", "line": "#e4d5bd", "text": "#2a1d12",
    "gray": "#8a7a68", "green": "#2e8b57", "green2": "#24764a", "red": "#c0392b",
    "red2": "#9a2f24", "soft": "#efe4d0",
}

FONT = "Segoe UI"
BIG = (FONT, 22, "bold")
MED = (FONT, 14, "bold")
NORMAL = (FONT, 10)
BOLD = (FONT, 10, "bold")
SMALL = (FONT, 9)
ENTRY_FONT = (FONT, 11)
BTN_FONT = (FONT, 11, "bold")


def money(n):
    return "\u20b1{:,.2f}".format(n)


# ---------- password stuff ----------
def hash_text(text, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", text.encode(), bytes.fromhex(salt), 120000)
    return "pbkdf2$" + salt + "$" + h.hex()


def check_hash(text, saved):
    if saved.startswith("pbkdf2$"):
        parts = saved.split("$")
        if len(parts) != 3:
            return False
        return hmac.compare_digest(hash_text(text, parts[1]), saved)
    # old accounts na plain sha256 pa
    return hmac.compare_digest(hashlib.sha256(text.encode()).hexdigest(), saved)


# ---------- images ----------
logo_cache = {}
prod_img_cache = {}
qr_cache = {}


def get_logo(size):
    if not HAS_PIL or not _LOGO_B64:
        return None
    if size not in logo_cache:
        try:
            im = Image.open(io.BytesIO(base64.b64decode(_LOGO_B64)))
            im = im.resize((size, size), Image.LANCZOS)
            logo_cache[size] = ImageTk.PhotoImage(im)
        except Exception:
            logo_cache[size] = None
    return logo_cache[size]


def clean_name(name):
    out = ""
    for ch in name:
        out += ch if ch.isalnum() else "_"
    return out[:20] or "product"


def copy_product_photo(src, name):
    ext = os.path.splitext(src)[1].lower() or ".png"
    fname = "{}_{}{}".format(clean_name(name), int(time.time() * 1000), ext)
    shutil.copy2(src, os.path.join(IMG_DIR, fname))
    return fname


def get_product_img(fname, size=120):
    if not fname or not HAS_PIL:
        return None
    key = (fname, size)
    if key not in prod_img_cache:
        try:
            im = Image.open(os.path.join(IMG_DIR, fname)).convert("RGB")
            prod_img_cache[key] = ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS))
        except Exception:
            prod_img_cache[key] = None
    return prod_img_cache[key]


def make_placeholder(name, category):
    # simpleng picture kung walang photo yung product
    if not HAS_PIL:
        return None
    colors = {
        "Coffee": ("#7a3f1d", "#f3d7b7"),
        "Tea": ("#5b7c4d", "#e3f0d8"),
        "Pastry": ("#c77b36", "#f8e8d0"),
        "Bread": ("#b97c43", "#f4dfc2"),
    }
    bg, accent = colors.get(category, ("#7a3f1d", "#f3d7b7"))
    fname = "{}_{}.png".format(clean_name(name).lower(), int(time.time() * 1000))
    im = Image.new("RGB", (400, 300), bg)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 20, 380, 280), radius=28, fill=accent)
    d.rounded_rectangle((60, 60, 340, 220), radius=22, fill=bg)
    try:
        f = ImageFont.truetype("arial.ttf", 30)
    except Exception:
        f = ImageFont.load_default()
    d.text((200, 140), name[:16], anchor="mm", font=f, fill="white")
    im.save(os.path.join(IMG_DIR, fname))
    return fname


def get_qr(size=170):
    if not HAS_PIL or not HAS_QR:
        return None
    if size not in qr_cache:
        try:
            msg = "GCash Payment - " + SHOP_NAME + " - " + GCASH_NO
            qr_cache[size] = ImageTk.PhotoImage(qrcode.make(msg).resize((size, size)))
        except Exception:
            qr_cache[size] = None
    return qr_cache[size]


# ---------- database ----------
class DB:
    def __init__(self):
        self.con = sqlite3.connect(DB_PATH)
        c = self.con
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'cashier',
            secret_question TEXT NOT NULL,
            secret_answer_hash TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            image_filename TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_datetime TEXT NOT NULL,
            items_json TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            total REAL NOT NULL)""")
        # dagdag columns kung luma pa yung db
        cols = [r[1] for r in c.execute("PRAGMA table_info(orders)")]
        if "cashier" not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN cashier TEXT")
        if "tendered" not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN tendered REAL")
        c.commit()

        # default admin
        n = c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        if n == 0:
            self.add_user("admin", "admin123", "admin", QUESTIONS[0], "manila")

        # default products
        n = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if n == 0:
            starter = [
                ("Caf\u00e9 Latte", "Coffee", 120, 100), ("Espresso", "Coffee", 90, 100),
                ("Iced Mocha", "Coffee", 150, 100), ("Cheese Ensaymada", "Pastry", 65, 100),
                ("Blueberry Muffin", "Pastry", 80, 100), ("Hot Choco", "Tea", 110, 100),
                ("Milk Tea", "Tea", 120, 100), ("Bacon Bread", "Bread", 70, 100),
            ]
            for name, cat, price, stock in starter:
                self.add_product(name, cat, price, stock, make_placeholder(name, cat))

        # lagyan ng picture yung walang picture
        rows = c.execute("SELECT id, name, category FROM products WHERE image_filename IS NULL OR image_filename=''").fetchall()
        for pid, name, cat in rows:
            img = make_placeholder(name, cat)
            if img:
                c.execute("UPDATE products SET image_filename=? WHERE id=?", (img, pid))
        c.commit()

    # users
    def user_exists(self, username):
        return self.con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone() is not None

    def add_user(self, username, pw, role, question, answer):
        self.con.execute(
            "INSERT INTO users (username, password_hash, role, secret_question, secret_answer_hash) VALUES (?,?,?,?,?)",
            (username, hash_text(pw), role, question, hash_text(answer.strip().lower())))
        self.con.commit()

    def login(self, username, pw):
        row = self.con.execute("SELECT role, password_hash FROM users WHERE username=?", (username,)).fetchone()
        if row is None or not check_hash(pw, row[1]):
            return None
        if not row[1].startswith("pbkdf2$"):
            # i-upgrade yung lumang hash
            self.con.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_text(pw), username))
            self.con.commit()
        return row[0]

    def is_admin_password(self, pw):
        rows = self.con.execute("SELECT password_hash FROM users WHERE role='admin'").fetchall()
        for r in rows:
            if check_hash(pw, r[0]):
                return True
        return False

    def get_question(self, username):
        row = self.con.execute("SELECT secret_question FROM users WHERE username=?", (username,)).fetchone()
        if row:
            return row[0]
        return None

    def answer_ok(self, username, answer):
        row = self.con.execute("SELECT secret_answer_hash FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return False
        return check_hash(answer.strip().lower(), row[0])

    def set_password(self, username, new_pw):
        self.con.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_text(new_pw), username))
        self.con.commit()

    # products
    def add_product(self, name, cat, price, stock, img=None):
        self.con.execute("INSERT INTO products (name, category, price, stock, image_filename) VALUES (?,?,?,?,?)",
                         (name, cat, price, stock, img))
        self.con.commit()

    def edit_product(self, pid, name, cat, price, stock, img=None):
        if img:
            self.con.execute("UPDATE products SET name=?, category=?, price=?, stock=?, image_filename=? WHERE id=?",
                             (name, cat, price, stock, img, pid))
        else:
            self.con.execute("UPDATE products SET name=?, category=?, price=?, stock=? WHERE id=?",
                             (name, cat, price, stock, pid))
        self.con.commit()

    def remove_product(self, pid):
        self.con.execute("DELETE FROM products WHERE id=?", (pid,))
        self.con.commit()

    def add_stock(self, pid, qty):
        self.con.execute("UPDATE products SET stock = stock + ? WHERE id=?", (qty, pid))
        self.con.commit()

    def products(self, search="", category="All"):
        sql = "SELECT id, name, category, price, stock, image_filename FROM products WHERE 1=1"
        args = []
        if search:
            sql += " AND name LIKE ?"
            args.append("%" + search + "%")
        if category != "All":
            sql += " AND category=?"
            args.append(category)
        sql += " ORDER BY name"
        return self.con.execute(sql, args).fetchall()

    def product(self, pid):
        return self.con.execute(
            "SELECT id, name, category, price, stock, image_filename FROM products WHERE id=?", (pid,)).fetchone()

    def categories(self):
        found = [r[0] for r in self.con.execute("SELECT DISTINCT category FROM products ORDER BY category")]
        for c in BASE_CATEGORIES:
            if c not in found:
                found.append(c)
        return found

    def low_stock_count(self):
        return self.con.execute("SELECT COUNT(*) FROM products WHERE stock <= ?", (LOW_STOCK_LEVEL,)).fetchone()[0]

    # orders
    def save_order(self, items, method, total, cashier, tendered):
        try:
            # check muna kung kulang stock
            for it in items:
                row = self.con.execute("SELECT name, stock FROM products WHERE id=?", (it["product_id"],)).fetchone()
                if row is None:
                    raise ValueError("'" + it["name"] + "' is no longer in the product list.")
                if row[1] < it["qty"]:
                    raise ValueError("Not enough stock for '{}' (only {} left).".format(row[0], row[1]))
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = self.con.execute(
                "INSERT INTO orders (order_datetime, items_json, payment_method, total, cashier, tendered) VALUES (?,?,?,?,?,?)",
                (now, json.dumps(items), method, total, cashier, tendered))
            for it in items:
                self.con.execute("UPDATE products SET stock = stock - ? WHERE id=?", (it["qty"], it["product_id"]))
            self.con.commit()
            return cur.lastrowid, now
        except Exception:
            self.con.rollback()
            raise

    def orders(self, period="All Time"):
        sql = "SELECT id, order_datetime, items_json, payment_method, total, cashier, tendered FROM orders"
        args = []
        now = datetime.now()
        if period == "Today":
            sql += " WHERE order_datetime >= ?"
            args.append(now.strftime("%Y-%m-%d 00:00:00"))
        elif period == "This Week":
            monday = now - timedelta(days=now.weekday())
            sql += " WHERE order_datetime >= ?"
            args.append(monday.strftime("%Y-%m-%d 00:00:00"))
        elif period == "This Month":
            sql += " WHERE order_datetime >= ?"
            args.append(now.strftime("%Y-%m-01 00:00:00"))
        sql += " ORDER BY order_datetime DESC"
        return self.con.execute(sql, args).fetchall()

    def summary(self, period):
        rows = self.orders(period)
        counts = {}
        total = 0
        for o in rows:
            total += o[4]
            try:
                items = json.loads(o[2])
            except Exception:
                items = []
            for it in items:
                counts[it["name"]] = counts.get(it["name"], 0) + it.get("qty", 0)
        if counts:
            best = max(counts, key=counts.get)
            best_qty = counts[best]
        else:
            best, best_qty = "N/A", 0
        return {"sales": total, "orders": len(rows), "best": best, "best_qty": best_qty}


# ---------- widget helpers ----------
BUTTONS = {
    "primary": (COL["orange"], COL["orange2"], "white"),
    "secondary": ("#ffffff", COL["soft"], COL["text"]),
    "success": (COL["green"], COL["green2"], "white"),
    "danger": (COL["red"], COL["red2"], "white"),
    "ghost": (COL["white"], COL["soft"], COL["orange2"]),
    "nav": ("#4a2c14", "#6a4020", "white"),
}


def make_button(parent, text, cmd=None, kind="primary", font=BOLD, padx=16, pady=8):
    bg, hover, fg = BUTTONS[kind]
    b = tk.Button(parent, text=text, command=cmd, font=font, bg=bg, fg=fg, relief="flat", bd=0,
                  padx=padx, pady=pady, cursor="hand2", activebackground=hover, activeforeground=fg)
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def make_entry(parent, show=None, bg=None):
    return tk.Entry(parent, font=ENTRY_FONT, bg=bg or COL["field"], fg=COL["text"], relief="flat", bd=0,
                    highlightthickness=1, highlightbackground=COL["line"], highlightcolor=COL["orange"],
                    insertbackground=COL["text"], show=show)


def max_chars(entry, n=MAX_CHARS):
    check = entry.register(lambda s: len(s) <= n)
    entry.config(validate="key", validatecommand=(check, "%P"))


def password_box(parent):
    frame = tk.Frame(parent, bg=COL["white"])
    e = make_entry(frame, show="\u2022")
    max_chars(e)
    e.pack(side="left", fill="x", expand=True, ipady=7)
    shown = [False]

    def toggle():
        shown[0] = not shown[0]
        if shown[0]:
            e.config(show="")
            btn.config(text="Hide")
        else:
            e.config(show="\u2022")
            btn.config(text="Show")

    btn = tk.Button(frame, text="Show", command=toggle, relief="flat", bd=0, bg=COL["white"],
                    fg=COL["orange2"], font=(FONT, 9, "bold"), activebackground=COL["white"], cursor="hand2")
    btn.pack(side="left", padx=(8, 0))
    return frame, e


def label(parent, text):
    return tk.Label(parent, text=text, font=BOLD, bg=COL["white"], fg=COL["gray"], anchor="w")


def toggle_row(parent, options, current, on_pick):
    row = tk.Frame(parent, bg=COL["bg"])
    for name in options:
        active = (name == current)
        tk.Button(row, text=name, font=BOLD if active else NORMAL,
                  bg=COL["orange"] if active else "white", fg="white" if active else COL["text"],
                  relief="flat", bd=0, padx=16, pady=7, cursor="hand2",
                  activebackground=COL["orange2"], command=lambda n=name: on_pick(n)).pack(side="left", padx=(0, 6))
    return row


def center_window(win, parent):
    win.update_idletasks()
    top = parent.winfo_toplevel()
    x = top.winfo_rootx() + (top.winfo_width() - win.winfo_width()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - win.winfo_height()) // 2
    win.geometry("+%d+%d" % (max(x, 0), max(y, 0)))


def logo_widget(parent, size, bg):
    img = get_logo(size)
    if img:
        lb = tk.Label(parent, image=img, bg=bg, bd=0)
        lb.image = img
        return lb
    cv = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0)
    cv.create_oval(2, 2, size - 2, size - 2, fill="#f4e3c1", outline=COL["orange"], width=2)
    cv.create_text(size // 2, size // 2, text="\u2615", font=(FONT, int(size * 0.4)))
    return cv


def make_receipt(order_id, when, items, method, total, cashier=None, tendered=None):
    w = 38
    out = [SHOP_NAME.center(w), TAGLINE.center(w), "-" * w,
           "Order #" + str(order_id), "Date : " + when]
    if cashier:
        out.append("Cashier: " + cashier)
    out.append("-" * w)
    for it in items:
        out.append(it["name"][:22])
        left = "   {} x {:.2f}".format(it["qty"], it["price"])
        out.append(left.ljust(w - 12) + "{:>12,.2f}".format(it["qty"] * it["price"]))
    out.append("-" * w)
    out.append("TOTAL".ljust(w - 14) + "{:>14}".format(money(total)))
    out.append("Payment: " + method)
    if tendered:
        out.append("Tendered".ljust(w - 14) + "{:>14}".format(money(tendered)))
        out.append("Change".ljust(w - 14) + "{:>14}".format(money(max(tendered - total, 0))))
    out.append("-" * w)
    out.append("Salamat po! Balik kayo ulit :)".center(w))
    return "\n".join(out)


class ReceiptWindow(tk.Toplevel):
    def __init__(self, parent, text, order_id):
        super().__init__(parent)
        self.title("Receipt #" + str(order_id))
        self.configure(bg=COL["white"])
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.text = text
        box = tk.Text(self, width=40, height=min(text.count("\n") + 2, 32), font=("Consolas", 10),
                      bg="#fffdf7", relief="flat", padx=14, pady=14)
        box.insert("1.0", text)
        box.config(state="disabled")
        box.pack(padx=14, pady=(14, 8))
        row = tk.Frame(self, bg=COL["white"])
        row.pack(pady=(0, 14))
        make_button(row, "Save as .txt", self.save, "secondary").pack(side="left", padx=4)
        make_button(row, "Close", self.destroy, "primary").pack(side="left", padx=4)
        center_window(self, parent)
        self.grab_set()

    def save(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")],
                                            initialfile="receipt.txt", parent=self)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text)


# ---------- base pages ----------
class AuthPage(tk.Frame):
    # parent class ng login, signup, forgot password
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL["bg"])
        self.app = app
        bar = tk.Frame(self, bg=COL["dark"], height=90)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        logo_widget(bar, 58, COL["dark"]).pack(side="left", padx=(40, 15), pady=16)
        box = tk.Frame(bar, bg=COL["dark"])
        box.pack(side="left", pady=16)
        tk.Label(box, text=SHOP_NAME, font=BIG, bg=COL["dark"], fg="white").pack(anchor="w")
        tk.Label(box, text=TAGLINE, font=NORMAL, bg=COL["dark"], fg="#d8c9b0").pack(anchor="w")
        tk.Frame(self, bg=COL["orange"], height=4).pack(side="top", fill="x")
        self.holder = tk.Frame(self, bg=COL["bg"])
        self.holder.place(relx=0.5, rely=0.55, anchor="center")

    def new_card(self):
        for w in self.holder.winfo_children():
            w.destroy()
        border = tk.Frame(self.holder, bg=COL["line"], padx=1, pady=1)
        border.pack()
        card = tk.Frame(border, bg=COL["white"], padx=48, pady=36)
        card.pack()
        return card


class MainPage(tk.Frame):
    # parent class ng mga pages after login (may navbar sa taas)
    def __init__(self, parent, app):
        super().__init__(parent, bg=COL["bg"])
        self.app = app
        self.bar = tk.Frame(self, bg=COL["dark"], height=68)
        self.bar.pack(side="top", fill="x")
        self.bar.pack_propagate(False)
        tk.Frame(self, bg=COL["orange"], height=3).pack(side="top", fill="x")
        self.content = tk.Frame(self, bg=COL["bg"])
        self.content.pack(fill="both", expand=True, padx=28, pady=18)

    def draw_navbar(self):
        for w in self.bar.winfo_children():
            w.destroy()
        logo_widget(self.bar, 42, COL["dark"]).pack(side="left", padx=(24, 10), pady=10)
        box = tk.Frame(self.bar, bg=COL["dark"])
        box.pack(side="left", pady=10)
        tk.Label(box, text=SHOP_NAME, font=(FONT, 14, "bold"), bg=COL["dark"], fg="white").pack(anchor="w")
        tk.Label(box, text=TAGLINE, font=SMALL, bg=COL["dark"], fg="#d8c9b0").pack(anchor="w")

        nav = tk.Frame(self.bar, bg=COL["dark"])
        nav.pack(side="right", padx=22)
        make_button(nav, "Log out", self.app.logout, "primary", font=(FONT, 9, "bold"), pady=6).pack(side="right", padx=(8, 0))
        who = "\U0001F464 {} ({})".format(self.app.username, self.app.role)
        tk.Label(nav, text=who, font=SMALL, bg=COL["dark"], fg="#d8c9b0").pack(side="right", padx=(10, 6))

        if self.app.role == "admin":
            links = [("Dashboard", DashboardPage), ("POS", POSPage), ("Inventory", InventoryPage)]
        else:
            links = [("POS", POSPage)]
        # reversed kasi side=right
        for text, page in reversed(links):
            kind = "primary" if isinstance(self, page) else "nav"
            make_button(nav, text, lambda p=page: self.app.show(p), kind,
                        font=(FONT, 9, "bold"), pady=6).pack(side="right", padx=(6, 0))

    def reset(self):
        self.draw_navbar()
        for w in self.content.winfo_children():
            w.destroy()


# ---------- login ----------
class LoginPage(AuthPage):
    def on_show(self):
        card = self.new_card()
        tk.Label(card, text="Welcome back", font=BIG, bg=COL["white"], fg=COL["text"]).pack(anchor="w")
        tk.Label(card, text="Log in to start your shift", font=NORMAL, bg=COL["white"], fg=COL["gray"]).pack(anchor="w", pady=(0, 20))

        label(card, "Username").pack(fill="x")
        self.user_e = make_entry(card)
        max_chars(self.user_e)
        self.user_e.pack(fill="x", ipady=7, pady=(3, 12))

        label(card, "Password").pack(fill="x")
        pf, self.pw_e = password_box(card)
        pf.pack(fill="x", pady=(3, 6))

        forgot = tk.Label(card, text="Forgot password?", fg=COL["orange2"], bg=COL["white"],
                          cursor="hand2", font=(FONT, 9, "underline"))
        forgot.pack(anchor="e", pady=(0, 16))
        forgot.bind("<Button-1>", lambda e: self.app.show(ForgotPage))

        make_button(card, "Login", self.try_login, "primary", font=BTN_FONT, pady=10).pack(fill="x", pady=(0, 14))

        row = tk.Frame(card, bg=COL["white"])
        row.pack()
        tk.Label(row, text="Don't have an account? ", bg=COL["white"], font=SMALL, fg=COL["gray"]).pack(side="left")
        link = tk.Label(row, text="Sign up", bg=COL["white"], fg=COL["orange2"], font=(FONT, 9, "bold"), cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: self.app.show(SignupPage))

        self.user_e.bind("<Return>", lambda e: self.try_login())
        self.pw_e.bind("<Return>", lambda e: self.try_login())
        self.user_e.focus_set()

    def try_login(self):
        wait = self.app.locked_until - time.time()
        if wait > 0:
            messagebox.showwarning("Too many attempts", "Please wait %d seconds before trying again." % (int(wait) + 1))
            return
        username = self.user_e.get().strip()
        pw = self.pw_e.get()
        role = self.app.db.login(username, pw)
        if role:
            self.app.fails = 0
            self.app.role = role
            self.app.username = username
            self.app.cart = []
            if role == "admin":
                self.app.show(DashboardPage)
            else:
                self.app.show(POSPage)
        else:
            self.app.fails += 1
            if self.app.fails >= MAX_TRIES:
                self.app.locked_until = time.time() + LOCK_SECS
                self.app.fails = 0
                messagebox.showerror("Locked", "Too many wrong attempts. Try again in %d seconds." % LOCK_SECS)
            else:
                messagebox.showerror("Login Failed", "Incorrect username or password.")


# ---------- sign up ----------
class SignupPage(AuthPage):
    def on_show(self):
        card = self.new_card()
        tk.Label(card, text="Create Account", font=BIG, bg=COL["white"], fg=COL["text"]).pack(anchor="w", pady=(0, 14))

        label(card, "Username").pack(fill="x")
        self.user_e = make_entry(card)
        max_chars(self.user_e)
        self.user_e.pack(fill="x", ipady=7, pady=(3, 10))

        label(card, "Password").pack(fill="x")
        pf, self.pw_e = password_box(card)
        pf.pack(fill="x", pady=(3, 2))
        tk.Label(card, text="Max %d characters for username and password" % MAX_CHARS,
                 font=SMALL, fg=COL["gray"], bg=COL["white"]).pack(anchor="w", pady=(0, 10))

        label(card, "Account Type  (admin needs an existing admin's password)").pack(fill="x")
        self.role_var = tk.StringVar(value="cashier")
        ttk.Combobox(card, textvariable=self.role_var, values=["cashier", "admin"],
                     state="readonly", font=ENTRY_FONT).pack(fill="x", ipady=4, pady=(3, 10))

        label(card, "Secret Question").pack(fill="x")
        self.q_var = tk.StringVar()
        ttk.Combobox(card, textvariable=self.q_var, values=QUESTIONS,
                     state="readonly", font=ENTRY_FONT).pack(fill="x", ipady=4, pady=(3, 10))

        label(card, "Your Answer").pack(fill="x")
        self.ans_e = make_entry(card)
        self.ans_e.pack(fill="x", ipady=7, pady=(3, 16))

        make_button(card, "Create Account", self.create, "primary", font=BTN_FONT, pady=10).pack(fill="x", pady=(0, 10))
        back = tk.Label(card, text="Already have an account? Login", bg=COL["white"], fg=COL["orange2"],
                        font=(FONT, 9, "bold"), cursor="hand2")
        back.pack()
        back.bind("<Button-1>", lambda e: self.app.show(LoginPage))
        self.ans_e.bind("<Return>", lambda e: self.create())
        self.user_e.focus_set()

    def create(self):
        username = self.user_e.get().strip()
        pw = self.pw_e.get()
        role = self.role_var.get()
        question = self.q_var.get()
        answer = self.ans_e.get().strip()

        if not username or not pw or not question or not answer:
            messagebox.showwarning("Incomplete", "Please fill in all fields.")
            return
        if len(pw) < 4:
            messagebox.showwarning("Weak password", "Password must be at least 4 characters.")
            return
        if self.app.db.user_exists(username):
            messagebox.showerror("Username Taken", "That username is already registered.")
            return
        if role == "admin":
            admin_pw = simpledialog.askstring("Admin approval", "Enter an existing ADMIN password to continue:",
                                              show="*", parent=self)
            if not admin_pw or not self.app.db.is_admin_password(admin_pw):
                messagebox.showerror("Not allowed", "Wrong admin password. Account not created.")
                return
        self.app.db.add_user(username, pw, role, question, answer)
        messagebox.showinfo("Account Created", "Your account has been created. You can now log in.")
        self.app.show(LoginPage)


# ---------- forgot password ----------
class ForgotPage(AuthPage):
    def on_show(self):
        card = self.new_card()
        tk.Label(card, text="Forgot Password", font=(FONT, 20, "bold"), bg=COL["white"], fg=COL["text"]).pack(anchor="w", pady=(0, 14))

        label(card, "Enter your username").pack(fill="x")
        self.user_e = make_entry(card)
        self.user_e.pack(fill="x", ipady=7, pady=(3, 4))
        make_button(card, "Load Question", self.load_q, "ghost", font=(FONT, 9, "bold"), pady=3).pack(anchor="e", pady=(0, 8))

        label(card, "Secret Question").pack(fill="x")
        self.q_var = tk.StringVar()
        ttk.Combobox(card, textvariable=self.q_var, values=QUESTIONS,
                     state="disabled", font=ENTRY_FONT).pack(fill="x", ipady=4, pady=(3, 10))

        label(card, "Your Answer").pack(fill="x")
        self.ans_e = make_entry(card)
        self.ans_e.config(state="disabled")
        self.ans_e.pack(fill="x", ipady=7, pady=(3, 2))
        self.ans_e.bind("<KeyRelease>", self.check_answer)
        self.status = tk.Label(card, text="", font=SMALL, bg=COL["white"])
        self.status.pack(anchor="w", pady=(0, 8))

        label(card, "New Password").pack(fill="x")
        pf, self.new_pw_e = password_box(card)
        self.new_pw_e.config(state="disabled")
        pf.pack(fill="x", pady=(3, 16))

        make_button(card, "Create new password", self.reset_pw, "primary", font=BTN_FONT, pady=10).pack(fill="x")
        back = tk.Label(card, text="Back to Login", bg=COL["white"], fg=COL["orange2"], font=(FONT, 9, "bold"), cursor="hand2")
        back.pack(pady=(12, 0))
        back.bind("<Button-1>", lambda e: self.app.show(LoginPage))

        self.user_e.bind("<Return>", lambda e: self.load_q())
        self.new_pw_e.bind("<Return>", lambda e: self.reset_pw())
        self.verified = False
        self.user_e.focus_set()

    def border(self, color):
        self.ans_e.config(highlightbackground=color, highlightcolor=color)

    def load_q(self):
        q = self.app.db.get_question(self.user_e.get().strip())
        if q is None:
            messagebox.showerror("Not Found", "No account found with that username.")
            return
        self.q_var.set(q)
        self.ans_e.config(state="normal")
        self.ans_e.delete(0, tk.END)
        self.status.config(text="")
        self.border(COL["line"])
        self.ans_e.focus_set()

    def check_answer(self, event=None):
        username = self.user_e.get().strip()
        ans = self.ans_e.get()
        if ans == "":
            self.border(COL["line"])
            self.status.config(text="")
            self.verified = False
            self.new_pw_e.config(state="disabled")
        elif self.app.db.answer_ok(username, ans):
            self.border(COL["green"])
            self.status.config(text="\u2714 Correct answer", fg=COL["green"])
            self.verified = True
            self.new_pw_e.config(state="normal")
        else:
            self.border(COL["red"])
            self.status.config(text="\u2716 Incorrect answer", fg=COL["red"])
            self.verified = False
            self.new_pw_e.config(state="disabled")

    def reset_pw(self):
        username = self.user_e.get().strip()
        if not self.verified or not self.app.db.answer_ok(username, self.ans_e.get()):
            messagebox.showwarning("Verify First", "Please answer your secret question correctly first.")
            return
        new_pw = self.new_pw_e.get()
        if len(new_pw) < 4:
            messagebox.showwarning("Weak password", "Password must be at least 4 characters.")
            return
        self.app.db.set_password(username, new_pw)
        messagebox.showinfo("Success", "Password updated. Please log in.")
        self.app.show(LoginPage)


# ---------- POS ----------
class POSPage(MainPage):
    COLS = 4

    def on_show(self):
        self.reset()
        if not hasattr(self, "category"):
            self.category = "All"
        self.search_text = ""

        left = tk.Frame(self.content, bg=COL["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 18))

        # search bar
        sr = tk.Frame(left, bg=COL["bg"])
        sr.pack(fill="x", pady=(0, 10))
        tk.Label(sr, text="\U0001F50D", font=(FONT, 12), bg=COL["bg"]).pack(side="left", padx=(0, 6))
        self.search_e = make_entry(sr, bg="white")
        self.search_e.pack(side="left", fill="x", expand=True, ipady=7)
        self.search_e.bind("<KeyRelease>", lambda e: self.do_search())
        tk.Label(sr, text="Search products", font=SMALL, bg=COL["bg"], fg=COL["gray"]).pack(side="left", padx=8)

        self.cat_holder = tk.Frame(left, bg=COL["bg"])
        self.cat_holder.pack(fill="x", pady=(0, 10))
        self.draw_categories()

        # scrollable grid ng products
        wrap = tk.Frame(left, bg=COL["bg"])
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=COL["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.grid_frame = tk.Frame(self.canvas, bg=COL["bg"])
        self.grid_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self.scroll))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        # cart sa right
        border = tk.Frame(self.content, bg=COL["line"], padx=1, pady=1, width=330)
        border.pack(side="right", fill="y")
        border.pack_propagate(False)
        right = tk.Frame(border, bg="white")
        right.pack(fill="both", expand=True)

        tk.Label(right, text="\U0001F6D2  Your cart", font=MED, bg="white", fg=COL["text"]).pack(anchor="w", padx=16, pady=(16, 0))
        self.cart_box = tk.Frame(right, bg="white")
        self.cart_box.pack(fill="both", expand=True, padx=16, pady=10)
        tk.Frame(right, bg=COL["line"], height=1).pack(fill="x", padx=16)
        self.total_lbl = tk.Label(right, text="Total: \u20b10.00", font=(FONT, 15, "bold"), bg="white", fg=COL["text"])
        self.total_lbl.pack(pady=(12, 8))
        make_button(right, "Checkout", self.checkout, "primary", font=BTN_FONT, pady=11).pack(fill="x", padx=16, pady=(0, 6))
        make_button(right, "Clear cart", self.clear, "ghost", font=SMALL, pady=4).pack(pady=(0, 14))

        self.draw_products()
        self.draw_cart()

    def scroll(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def draw_categories(self):
        for w in self.cat_holder.winfo_children():
            w.destroy()
        names = ["All"] + self.app.db.categories()
        toggle_row(self.cat_holder, names, self.category, self.pick_category).pack(anchor="w")

    def pick_category(self, name):
        self.category = name
        self.draw_categories()
        self.draw_products()

    def do_search(self):
        self.search_text = self.search_e.get().strip()
        self.draw_products()

    def draw_products(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        items = self.app.db.products(self.search_text, self.category)
        for i, p in enumerate(items):
            pid, name, cat, price, stock, img_file = p
            border = tk.Frame(self.grid_frame, bg=COL["line"], padx=1, pady=1)
            border.grid(row=i // self.COLS, column=i % self.COLS, padx=7, pady=7)
            card = tk.Frame(border, bg="white", width=176, height=236)
            card.pack()
            card.pack_propagate(False)

            img = get_product_img(img_file, 120)
            if img:
                lb = tk.Label(card, image=img, bg="white")
                lb.image = img
                lb.pack(pady=(10, 4))
            else:
                ph = tk.Frame(card, bg=COL["soft"], width=120, height=96)
                ph.pack(pady=(10, 4))
                ph.pack_propagate(False)
                tk.Label(ph, text="\u2615", font=(FONT, 30), bg=COL["soft"], fg=COL["orange2"]).pack(expand=True)

            tk.Label(card, text=name, font=BOLD, bg="white", fg=COL["text"], wraplength=160).pack()
            tk.Label(card, text=money(price), font=(FONT, 11, "bold"), bg="white", fg=COL["orange2"]).pack()

            if stock <= 0:
                txt, color = "Sold out", COL["red"]
            elif stock <= LOW_STOCK_LEVEL:
                txt, color = "Only %d left" % stock, COL["orange2"]
            else:
                txt, color = "%d in stock" % stock, COL["gray"]
            tk.Label(card, text=txt, font=(FONT, 8), bg="white", fg=color).pack()

            if stock > 0:
                make_button(card, "Add to cart", lambda r=p: self.add(r), "primary",
                            font=(FONT, 9, "bold"), pady=5).pack(fill="x", padx=12, pady=(4, 10))
            else:
                tk.Button(card, text="Sold out", state="disabled", font=(FONT, 9, "bold"), relief="flat",
                          bg="#d6d0c4", pady=5).pack(fill="x", padx=12, pady=(4, 10))

        if len(items) == 0:
            tk.Label(self.grid_frame, text="No products found.", font=ENTRY_FONT, bg=COL["bg"], fg=COL["gray"]).grid(row=0, column=0, pady=30, padx=10)

    def add(self, row):
        self.app.add_to_cart(row)
        self.draw_cart()

    def draw_cart(self):
        for w in self.cart_box.winfo_children():
            w.destroy()
        if len(self.app.cart) == 0:
            tk.Label(self.cart_box, text="Cart is empty.\nTap a product to add it.", font=NORMAL,
                     bg="white", fg=COL["gray"], justify="center").pack(pady=30)
        for it in self.app.cart:
            pid = it["product_id"]
            row = tk.Frame(self.cart_box, bg="white")
            row.pack(fill="x", pady=5)
            top = tk.Frame(row, bg="white")
            top.pack(fill="x")
            tk.Label(top, text=it["name"], font=BOLD, bg="white", anchor="w", fg=COL["text"]).pack(side="left")
            tk.Button(top, text="\u2715", font=(FONT, 9, "bold"), bg="white", fg=COL["red"], relief="flat", bd=0,
                      cursor="hand2", command=lambda p=pid: self.delete_item(p)).pack(side="right")
            bot = tk.Frame(row, bg="white")
            bot.pack(fill="x", pady=(2, 0))
            tk.Button(bot, text="\u2212", width=2, font=BOLD, bg=COL["soft"], relief="flat", cursor="hand2",
                      command=lambda p=pid: self.minus(p)).pack(side="left")
            tk.Label(bot, text=str(it["qty"]), font=BOLD, bg="white", width=3).pack(side="left")
            tk.Button(bot, text="+", width=2, font=BOLD, bg=COL["soft"], relief="flat", cursor="hand2",
                      command=lambda p=pid: self.plus(p)).pack(side="left")
            tk.Label(bot, text=money(it["price"] * it["qty"]), font=NORMAL, bg="white").pack(side="right")
        self.total_lbl.config(text="Total: " + money(self.app.cart_total()))

    def plus(self, pid):
        p = self.app.db.product(pid)
        if p:
            self.app.add_to_cart(p)
        self.draw_cart()

    def minus(self, pid):
        self.app.minus_from_cart(pid)
        self.draw_cart()

    def delete_item(self, pid):
        self.app.cart = [i for i in self.app.cart if i["product_id"] != pid]
        self.draw_cart()

    def clear(self):
        if self.app.cart and messagebox.askyesno("Clear cart", "Remove all items from the cart?"):
            self.app.cart = []
            self.draw_cart()

    def checkout(self):
        if not self.app.cart:
            messagebox.showwarning("Empty Cart", "Add at least one item before checking out.")
            return
        self.app.show(CheckoutPage)


# ---------- checkout ----------
class CheckoutPage(MainPage):
    def on_show(self):
        self.reset()
        left = tk.Frame(self.content, bg=COL["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 18))
        tk.Label(left, text="Your Order", font=(FONT, 20, "bold"), bg=COL["bg"], fg=COL["text"]).pack(anchor="w", pady=(0, 12))

        self.tree = ttk.Treeview(left, columns=("name", "qty", "price", "sub"), show="headings", height=12)
        for col, text, w, anc in [("name", "Item", 240, "w"), ("qty", "Qty", 70, "center"),
                                  ("price", "Unit Price", 120, "e"), ("sub", "Subtotal", 130, "e")]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor=anc)
        self.tree.pack(fill="both", expand=True)
        for it in self.app.cart:
            self.tree.insert("", "end", values=(it["name"], it["qty"], money(it["price"]), money(it["price"] * it["qty"])))

        border = tk.Frame(self.content, bg=COL["line"], padx=1, pady=1, width=360)
        border.pack(side="right", fill="y")
        border.pack_propagate(False)
        right = tk.Frame(border, bg="white")
        right.pack(fill="both", expand=True)

        tk.Label(right, text="Payment Method", font=MED, bg="white").pack(anchor="w", padx=20, pady=(20, 8))
        self.method = tk.StringVar(value="Cash")
        for m in ("Cash", "GCash", "Card"):
            tk.Radiobutton(right, text=m, variable=self.method, value=m, bg="white", font=ENTRY_FONT,
                           activebackground="white", anchor="w", command=self.draw_payment).pack(anchor="w", padx=20, pady=1)

        self.total = self.app.cart_total()
        tk.Label(right, text="Total: " + money(self.total), font=(FONT, 18, "bold"), bg="white",
                 fg=COL["orange2"]).pack(anchor="w", padx=20, pady=(14, 6))

        self.detail = tk.Frame(right, bg="white")
        self.detail.pack(fill="x", padx=20)
        self.draw_payment()

        make_button(right, "Confirm Order", self.confirm, "success", font=BTN_FONT, pady=11).pack(side="bottom", fill="x", padx=20, pady=(6, 20))
        make_button(right, "Back to Menu", lambda: self.app.show(POSPage), "secondary", pady=9).pack(side="bottom", fill="x", padx=20, pady=(6, 0))

    def draw_payment(self):
        for w in self.detail.winfo_children():
            w.destroy()
        m = self.method.get()
        if m == "Cash":
            tk.Label(self.detail, text="Cash received", font=BOLD, bg="white", fg=COL["gray"]).pack(anchor="w")
            self.cash_e = make_entry(self.detail)
            self.cash_e.pack(fill="x", ipady=7, pady=(3, 4))
            self.cash_e.bind("<KeyRelease>", lambda e: self.show_change())
            self.cash_e.bind("<Return>", lambda e: self.confirm())
            self.change_lbl = tk.Label(self.detail, text="Change: \u20b10.00", font=(FONT, 13, "bold"), bg="white", fg=COL["green"])
            self.change_lbl.pack(anchor="w", pady=(2, 8))
            quick = tk.Frame(self.detail, bg="white")
            quick.pack(anchor="w")
            make_button(quick, "Exact", lambda: self.fill_cash(self.total), "ghost", font=SMALL, pady=3, padx=10).pack(side="left", padx=(0, 4))
            for amt in (100, 200, 500, 1000):
                make_button(quick, str(amt), lambda a=amt: self.fill_cash(a), "ghost", font=SMALL, pady=3, padx=8).pack(side="left", padx=2)
            self.cash_e.focus_set()
        elif m == "GCash":
            qr = get_qr(170)
            if qr:
                lb = tk.Label(self.detail, image=qr, bg="white")
                lb.image = qr
                lb.pack(pady=(0, 4))
            else:
                box = tk.Frame(self.detail, bg=COL["soft"], width=170, height=170)
                box.pack(pady=(0, 4))
                box.pack_propagate(False)
                tk.Label(box, text="QR\n(pip install\nqrcode pillow)", bg=COL["soft"], fg=COL["gray"], font=SMALL).pack(expand=True)
            tk.Label(self.detail, text="GCash: " + GCASH_NO, font=BOLD, bg="white").pack()
            tk.Label(self.detail, text="Confirm only after payment is received.", font=SMALL, bg="white", fg=COL["gray"]).pack()
        else:
            tk.Label(self.detail, text="Process the card on your terminal,\nthen press Confirm.", font=NORMAL,
                     bg="white", fg=COL["gray"], justify="left").pack(anchor="w")

    def fill_cash(self, amount):
        self.cash_e.delete(0, tk.END)
        self.cash_e.insert(0, ("%.2f" % amount).rstrip("0").rstrip("."))
        self.show_change()

    def get_cash(self):
        try:
            return float(self.cash_e.get().replace(",", "").strip())
        except (ValueError, AttributeError):
            return None

    def show_change(self):
        cash = self.get_cash()
        if cash is None:
            self.change_lbl.config(text="Change: \u20b10.00", fg=COL["green"])
        elif cash < self.total:
            self.change_lbl.config(text="Short by " + money(self.total - cash), fg=COL["red"])
        else:
            self.change_lbl.config(text="Change: " + money(cash - self.total), fg=COL["green"])

    def confirm(self):
        if not self.app.cart:
            messagebox.showwarning("Empty Cart", "Add at least one item before checking out.")
            return
        method = self.method.get()
        cash = None
        if method == "Cash":
            cash = self.get_cash()
            if cash is None or cash < self.total:
                messagebox.showwarning("Cash", "Enter the cash received (it must cover the total).")
                return
        items = []
        for i in self.app.cart:
            items.append({"product_id": i["product_id"], "name": i["name"], "qty": i["qty"], "price": i["price"]})
        try:
            order_id, when = self.app.db.save_order(items, method, self.total, self.app.username, cash)
        except ValueError as err:
            messagebox.showerror("Cannot complete order", str(err))
            return
        text = make_receipt(order_id, when, items, method, self.total, self.app.username, cash)
        self.app.cart = []
        self.app.show(POSPage)
        ReceiptWindow(self.app, text, order_id)


# ---------- dashboard ----------
class DashboardPage(MainPage):
    PERIODS = ["Today", "This Week", "This Month", "All Time"]

    def on_show(self):
        self.draw()

    def draw(self):
        self.reset()
        if not hasattr(self, "period"):
            self.period = "Today"

        head = tk.Frame(self.content, bg=COL["bg"])
        head.pack(fill="x", pady=(0, 14))
        tk.Label(head, text="Dashboard", font=(FONT, 24, "bold"), bg=COL["bg"], fg=COL["text"]).pack(side="left")
        toggle_row(head, self.PERIODS, self.period, self.set_period).pack(side="right")

        s = self.app.db.summary(self.period)
        low = self.app.db.low_stock_count()
        cards = tk.Frame(self.content, bg=COL["bg"])
        cards.pack(fill="x")
        stats = [
            ("Total Sales", money(s["sales"]), COL["orange2"]),
            ("Orders", str(s["orders"]), COL["green"]),
            ("Best Seller", s["best"], COL["dark"]),
            ("Units of Best Seller", str(s["best_qty"]), COL["gray"]),
            ("Low / Out of Stock", str(low), COL["red"] if low else COL["green"]),
        ]
        for title, value, color in stats:
            b = tk.Frame(cards, bg=COL["line"], padx=1, pady=1)
            b.pack(side="left", padx=(0, 12), fill="y")
            inner = tk.Frame(b, bg="white", padx=18, pady=14)
            inner.pack(fill="both")
            tk.Label(inner, text=title, bg="white", fg=COL["gray"], font=SMALL).pack(anchor="w")
            tk.Label(inner, text=value, bg="white", fg=color, font=(FONT, 16, "bold")).pack(anchor="w", pady=(4, 0))

        tk.Label(self.content, text="Orders \u2014 %s   (double-click to view receipt)" % self.period,
                 font=MED, bg=COL["bg"], fg=COL["text"]).pack(anchor="w", pady=(18, 8))
        tf = tk.Frame(self.content, bg=COL["bg"])
        tf.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tf, columns=("id", "dt", "cashier", "pay", "total"), show="headings", height=12)
        for col, text, w, anc in [("id", "Order #", 80, "center"), ("dt", "Date / Time", 190, "w"),
                                  ("cashier", "Cashier", 130, "w"), ("pay", "Payment", 110, "center"),
                                  ("total", "Total", 130, "e")]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor=anc)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.order_map = {}
        for o in self.app.db.orders(self.period):
            self.order_map[str(o[0])] = o
            self.tree.insert("", "end", iid=str(o[0]), values=(o[0], o[1], o[5] or "-", o[3], money(o[4])))
        self.tree.bind("<Double-1>", self.open_receipt)

        btns = tk.Frame(self.content, bg=COL["bg"])
        btns.pack(fill="x", pady=(14, 0))
        make_button(btns, "Export CSV", self.export, "success", pady=9).pack(side="left", padx=(0, 10))
        make_button(btns, "Manage Inventory", lambda: self.app.show(InventoryPage), "primary", pady=9).pack(side="left", padx=(0, 10))
        make_button(btns, "Open POS", lambda: self.app.show(POSPage), "secondary", pady=9).pack(side="left")

    def set_period(self, p):
        self.period = p
        self.draw()

    def open_receipt(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        o = self.order_map[sel[0]]
        try:
            items = json.loads(o[2])
        except Exception:
            items = []
        text = make_receipt(o[0], o[1], items, o[3], o[4], o[5], o[6])
        ReceiptWindow(self.app, text, o[0])

    def export(self):
        rows = self.app.db.orders(self.period)
        if not rows:
            messagebox.showinfo("Export", "No orders to export for this period.")
            return
        fname = "sales_%s_%s.csv" % (self.period.replace(" ", "_").lower(), datetime.now().strftime("%Y%m%d"))
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV (Excel)", "*.csv")], initialfile=fname)
        if not path:
            return
        grand = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Order #", "Date/Time", "Cashier", "Payment", "Items", "Total"])
            for o in rows:
                try:
                    names = ", ".join("%s x%s" % (i["name"], i["qty"]) for i in json.loads(o[2]))
                except Exception:
                    names = ""
                w.writerow([o[0], o[1], o[5] or "", o[3], names, "%.2f" % o[4]])
                grand += o[4]
            w.writerow([])
            w.writerow(["", "", "", "", "TOTAL", "%.2f" % grand])
        messagebox.showinfo("Export", "Saved to:\n" + path)


# ---------- add / edit product window ----------
class ProductWindow(tk.Toplevel):
    def __init__(self, parent, db, product=None, after_save=None):
        super().__init__(parent)
        self.db = db
        self.product = product
        self.after_save = after_save
        self.new_image = None
        self.title("Edit Product" if product else "Add Product")
        self.configure(bg=COL["white"], padx=28, pady=22)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())

        tk.Label(self, text=self.title(), font=MED, bg=COL["white"], fg=COL["text"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self.name_e = make_entry(self)
        self.price_e = make_entry(self)
        self.stock_e = make_entry(self)
        self.cat_var = tk.StringVar()
        self.cat_box = ttk.Combobox(self, textvariable=self.cat_var, values=db.categories(), font=ENTRY_FONT, width=28)

        fields = [("Name", self.name_e), ("Category (pwede mag-type ng bago)", self.cat_box),
                  ("Price (\u20b1)", self.price_e), ("Stock", self.stock_e)]
        r = 1
        for text, widget in fields:
            label(self, text).grid(row=r, column=0, columnspan=2, sticky="w")
            pad = 4 if widget is self.cat_box else 6
            widget.grid(row=r + 1, column=0, columnspan=2, sticky="ew", ipady=pad, pady=(2, 10))
            r += 2

        self.img_lbl = tk.Label(self, text="No new image", font=SMALL, bg=COL["white"], fg=COL["gray"])
        make_button(self, "Choose photo\u2026", self.pick_image, "secondary", font=SMALL, pady=5).grid(row=r, column=0, sticky="w")
        self.img_lbl.grid(row=r, column=1, sticky="w", padx=8)
        r += 1
        bar = tk.Frame(self, bg=COL["white"])
        bar.grid(row=r, column=0, columnspan=2, sticky="e", pady=(16, 0))
        make_button(bar, "Cancel", self.destroy, "secondary").pack(side="left", padx=4)
        make_button(bar, "Save", self.save, "primary").pack(side="left", padx=4)

        if product:
            self.name_e.insert(0, product[1])
            self.cat_var.set(product[2])
            self.price_e.insert(0, "%g" % product[3])
            self.stock_e.insert(0, str(product[4]))
            if product[5]:
                self.img_lbl.config(text="Current photo kept unless you pick a new one")
        self.name_e.focus_set()
        center_window(self, parent)
        self.grab_set()

    def pick_image(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")])
        if path:
            self.new_image = path
            self.img_lbl.config(text=os.path.basename(path)[:30])

    def save(self):
        name = self.name_e.get().strip()
        cat = self.cat_var.get().strip()
        if not name or not cat:
            messagebox.showwarning("Required", "Name and category are required.", parent=self)
            return
        try:
            price = float(self.price_e.get().replace(",", ""))
            stock = int(self.stock_e.get())
            if price < 0 or stock < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid", "Price must be a number and stock a whole number (0 or more).", parent=self)
            return

        fname = None
        if self.new_image:
            try:
                fname = copy_product_photo(self.new_image, name)
            except OSError as err:
                messagebox.showerror("Image", "Could not copy image: %s" % err, parent=self)
                return
        elif self.product is None:
            fname = make_placeholder(name, cat)

        if self.product:
            self.db.edit_product(self.product[0], name, cat, price, stock, fname or self.product[5])
        else:
            self.db.add_product(name, cat, price, stock, fname)
        if self.after_save:
            self.after_save()
        self.destroy()


# ---------- inventory ----------
class InventoryPage(MainPage):
    def on_show(self):
        self.reset()
        top = tk.Frame(self.content, bg=COL["bg"])
        top.pack(fill="x", pady=(0, 12))
        tk.Label(top, text="Inventory", font=(FONT, 22, "bold"), bg=COL["bg"], fg=COL["text"]).pack(side="left")
        make_button(top, "+ Add Product", self.add, "primary", pady=9).pack(side="right")
        self.search_e = make_entry(top, bg="white")
        self.search_e.pack(side="right", padx=14, ipady=6)
        self.search_e.bind("<KeyRelease>", lambda e: self.fill_table())
        tk.Label(top, text="Search:", font=SMALL, bg=COL["bg"], fg=COL["gray"]).pack(side="right")

        tf = tk.Frame(self.content, bg=COL["bg"])
        tf.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tf, columns=("id", "name", "category", "price", "stock"), show="headings", height=16)
        for col, text, w, anc in [("id", "ID", 60, "center"), ("name", "Name", 260, "w"), ("category", "Category", 130, "center"),
                                  ("price", "Price", 120, "e"), ("stock", "Stock", 90, "center")]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor=anc)
        self.tree.tag_configure("low", foreground=COL["orange2"])
        self.tree.tag_configure("out", foreground=COL["red"])
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.edit())

        bar = tk.Frame(self.content, bg=COL["bg"])
        bar.pack(fill="x", pady=(12, 0))
        make_button(bar, "Edit Selected", self.edit, "secondary", pady=9).pack(side="left", padx=(0, 10))
        make_button(bar, "Restock Selected", self.restock, "success", pady=9).pack(side="left", padx=(0, 10))
        make_button(bar, "Delete Selected", self.delete, "danger", pady=9).pack(side="left", padx=(0, 10))
        tk.Label(bar, text="Orange = %d or fewer left, red = sold out" % LOW_STOCK_LEVEL, font=SMALL,
                 bg=COL["bg"], fg=COL["gray"]).pack(side="right")
        self.fill_table()

    def fill_table(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        for pid, name, cat, price, stock, _ in self.app.db.products(self.search_e.get().strip()):
            tag = ""
            if stock <= 0:
                tag = "out"
            elif stock <= LOW_STOCK_LEVEL:
                tag = "low"
            self.tree.insert("", "end", values=(pid, name, cat, money(price), stock), tags=(tag,))

    def selected_id(self, action):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a product to %s." % action)
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def add(self):
        ProductWindow(self, self.app.db, after_save=self.fill_table)

    def edit(self):
        pid = self.selected_id("edit")
        if pid:
            ProductWindow(self, self.app.db, self.app.db.product(pid), after_save=self.fill_table)

    def restock(self):
        pid = self.selected_id("restock")
        if not pid:
            return
        qty = simpledialog.askinteger("Restock", "How many units to add?", minvalue=1, parent=self)
        if qty:
            self.app.db.add_stock(pid, qty)
            self.fill_table()

    def delete(self):
        pid = self.selected_id("delete")
        if not pid:
            return
        p = self.app.db.product(pid)
        if messagebox.askyesno("Delete product", "Delete '%s'? This cannot be undone.\n(Past orders are kept.)" % p[1]):
            self.app.db.remove_product(pid)
            self.app.cart = [i for i in self.app.cart if i["product_id"] != pid]
            self.fill_table()


# ---------- main app ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(SHOP_NAME)
        self.geometry("1280x780")
        self.minsize(1050, 700)
        self.configure(bg=COL["bg"])
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                pass
        self.fullscreen = False
        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))

        self.setup_style()
        self.db = DB()
        self.role = None
        self.username = None
        self.cart = []
        self.fails = 0
        self.locked_until = 0.0

        self.pages = {}
        for cls in (LoginPage, SignupPage, ForgotPage, POSPage, CheckoutPage, DashboardPage, InventoryPage):
            page = cls(self, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[cls] = page
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.show(LoginPage)

    def setup_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("Treeview", rowheight=34, font=(FONT, 10), background="white", fieldbackground="white",
                     foreground=COL["text"], borderwidth=0)
        st.configure("Treeview.Heading", font=(FONT, 10, "bold"), background=COL["dark"], foreground="white",
                     relief="flat", padding=(8, 8))
        st.map("Treeview", background=[("selected", COL["orange"])], foreground=[("selected", "white")])
        st.map("Treeview.Heading", background=[("active", "#4a2c14")])
        st.configure("TCombobox", padding=4)
        st.configure("Vertical.TScrollbar", background=COL["soft"], troughcolor=COL["bg"], borderwidth=0)

    def toggle_fullscreen(self, event=None):
        self.fullscreen = not self.fullscreen
        self.attributes("-fullscreen", self.fullscreen)

    def show(self, cls):
        # admin lang sa dashboard at inventory
        if cls in (DashboardPage, InventoryPage) and self.role != "admin":
            if self.role is None:
                cls = LoginPage
            else:
                messagebox.showwarning("Not allowed", "Admin access only.")
                return
        if cls in (POSPage, CheckoutPage) and self.role is None:
            cls = LoginPage
        page = self.pages[cls]
        page.tkraise()
        if hasattr(page, "on_show"):
            page.on_show()

    # cart functions
    def add_to_cart(self, row):
        pid, name, _cat, price, stock, _img = row
        for it in self.cart:
            if it["product_id"] == pid:
                if it["qty"] >= stock:
                    messagebox.showwarning("Stock limit", "Only %d of '%s' available." % (stock, name))
                    return
                it["qty"] += 1
                return
        if stock > 0:
            self.cart.append({"product_id": pid, "name": name, "price": float(price), "qty": 1})

    def minus_from_cart(self, pid):
        for i, it in enumerate(self.cart):
            if it["product_id"] == pid:
                if it["qty"] > 1:
                    it["qty"] -= 1
                else:
                    self.cart.pop(i)
                return

    def cart_total(self):
        total = 0
        for it in self.cart:
            total += it["price"] * it["qty"]
        return total

    def logout(self):
        self.username = None
        self.role = None
        self.cart = []
        self.show(LoginPage)


if __name__ == "__main__":
    App().mainloop()
