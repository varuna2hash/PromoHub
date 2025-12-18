from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import sqlite3, os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev123")  # change in production

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# ---------- DB helper ----------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

# ---------- Initialize DB ----------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT UNIQUE,
        name TEXT,
        user_type TEXT,
        city TEXT,
        address TEXT,
        bank_name TEXT,
        bank_account TEXT,
        email TEXT,
        whatsapp TEXT,
        default_promo REAL DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id TEXT,
        shop_id TEXT,
        bill_amount REAL,
        promotion_amount REAL,
        transaction_date TEXT
    )""")
    con.commit()
    con.close()

init_db()

# ---------- Helpers ----------
def generate_user_id(user_type):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE user_type=?", (user_type,))
    count = cur.fetchone()[0] + 1
    prefix = "C" if user_type.lower() == "customer" else "S"
    return f"{prefix}{count:05d}"

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

# Register
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name      = request.form["name"].strip()
        email     = request.form.get("email", "").strip()  # optional
        city      = request.form["city"].strip()
        address   = request.form["address"].strip()
        whatsapp  = request.form["whatsapp"].strip()
        user_type = request.form["user_type"].strip()

        if user_type.lower() == "customer":
            bank_name = request.form.get("bank_name", "").strip()
            bank_account = request.form.get("bank_account", "").strip()
            default_promo = 0
        else:  # Shop owner
            bank_name = None
            bank_account = None
            default_promo = float(request.form.get("default_promo", 0))

        uid = generate_user_id(user_type)

        con = get_db()
        cur = con.cursor()
        cur.execute("""
            INSERT INTO users 
            (user_id,name,user_type,city,address,bank_name,bank_account,email,whatsapp,default_promo)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (uid, name, user_type, city, address, bank_name, bank_account, email, whatsapp, default_promo)
        )
        con.commit()
        flash(f"Registered successfully — User ID: {uid}", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# Users list (superadmin only)
@app.route("/users")
def users():
    if session.get("user_type") != "superadmin":
        flash("Only Super Admin can view users.", "danger")
        return redirect(url_for("index"))
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users ORDER BY id DESC")
    rows = cur.fetchall()
    return render_template("users.html", users=rows)

# Edit user (superadmin only)
@app.route("/edit/<user_id>", methods=["GET","POST"])
def edit(user_id):
    if session.get("user_type") != "superadmin":
        flash("Only Super Admin can edit users.", "danger")
        return redirect(url_for("index"))
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cur.fetchone()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("users"))
    if request.method == "POST":
        cur.execute("""
            UPDATE users SET name=?, city=?, address=?, bank_name=?, bank_account=?, email=?, whatsapp=?, default_promo=?
            WHERE user_id=?""",
            (request.form["name"].strip(), request.form.get("city", "").strip(),
             request.form.get("address", "").strip(),
             request.form.get("bank_name"), request.form.get("bank_account"),
             request.form.get("email"), request.form.get("whatsapp"),
             float(request.form.get("default_promo", user["default_promo"])),
             user_id)
        )
        con.commit()
        flash("User updated successfully.", "success")
        return redirect(url_for("users"))
    return render_template("edit.html", user=user)

# Delete user
@app.route("/delete/<user_id>")
def delete(user_id):
    if session.get("user_type") != "superadmin":
        flash("Only Super Admin can delete users.", "danger")
        return redirect(url_for("index"))
    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    con.commit()
    flash("User deleted.", "success")
    return redirect(url_for("users"))

# Login
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        phone = request.form["phone"].strip()
        password = request.form.get("password", "")
        # super admin
        if phone == "suadmin" and password == "suadmin654321":
            session["user_id"] = "SUPERADMIN"
            session["user_name"] = "Super Admin"
            session["user_type"] = "superadmin"
            return redirect(url_for("superadmin_dashboard"))
        # normal user
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE whatsapp=?", (phone,))
        user = cur.fetchone()
        if user:
            session["user_id"] = user["user_id"]
            session["user_name"] = user["name"]
            session["user_type"] = user["user_type"]
            if user["user_type"].lower() == "customer":
                return redirect(url_for("customer_dashboard"))
            else:
                return redirect(url_for("shop_dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

# Customer dashboard
@app.route("/customer_dashboard")
def customer_dashboard():
    if session.get("user_type", "").lower() != "customer":
        return redirect(url_for("login"))
    customer_id = session["user_id"]
    con = get_db()
    cur = con.cursor()
    cur.execute("""SELECT shop_id, bill_amount, promotion_amount, transaction_date
                   FROM transactions WHERE customer_id=? ORDER BY transaction_date DESC""", (customer_id,))
    transactions = cur.fetchall()
    total_transactions = len(transactions)
    total_spent = sum([t["bill_amount"] for t in transactions])
    total_promos = sum([t["promotion_amount"] for t in transactions])
    return render_template("customer_dashboard.html",
                           name=session["user_name"],
                           user_type=session["user_type"],
                           transactions=transactions,
                           total_transactions=total_transactions,
                           total_spent=total_spent,
                           total_promos=total_promos)

# Shop dashboard
@app.route("/shop_dashboard", methods=["GET","POST"])
def shop_dashboard():
    if session.get("user_type", "").lower() != "shop owner":
        return redirect(url_for("login"))
    shop_id = session["user_id"]
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT default_promo FROM users WHERE user_id=?", (shop_id,))
    row = cur.fetchone()
    default_promo = row["default_promo"] if row else 0.0

    if request.method == "POST":
        date = request.form["transaction_date"]
        bill = float(request.form["bill_amount"])
        customer_phone = request.form["customer_phone"].strip()
        cur.execute("SELECT user_id FROM users WHERE whatsapp=? AND user_type='Customer'", (customer_phone,))
        customer = cur.fetchone()
        if customer:
            customer_id = customer["user_id"]
            promo_amount = round(bill * default_promo / 100.0, 2)
            cur.execute("""INSERT INTO transactions
                        (customer_id, shop_id, bill_amount, promotion_amount, transaction_date)
                        VALUES (?, ?, ?, ?, ?)""",
                        (customer_id, shop_id, bill, promo_amount, date))
            con.commit()
            flash(f"Transaction added — Promo {promo_amount} ({default_promo}%) applied to {customer_id}.", "success")
        else:
            flash("Customer phone not found.", "danger")

    cur.execute("""SELECT transaction_date, bill_amount, promotion_amount, customer_id
                   FROM transactions WHERE shop_id=? ORDER BY transaction_date DESC""", (shop_id,))
    transactions = cur.fetchall()
    total_transactions = len(transactions)
    total_sales = sum([t["bill_amount"] for t in transactions])
    total_promos = sum([t["promotion_amount"] for t in transactions])
    return render_template("shop_dashboard.html",
                           name=session["user_name"],
                           user_type=session["user_type"],
                           transactions=transactions,
                           default_promo=default_promo,
                           total_transactions=total_transactions,
                           total_sales=total_sales,
                           total_promos=total_promos)

# Super admin dashboard
@app.route("/superadmin_dashboard")
def superadmin_dashboard():
    if session.get("user_type") != "superadmin":
        return redirect(url_for("login"))
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users ORDER BY id DESC")
    users = cur.fetchall()
    cur.execute("SELECT * FROM transactions ORDER BY id DESC")
    transactions = cur.fetchall()

    cur.execute("SELECT shop_id, COUNT(*), SUM(bill_amount), SUM(promotion_amount) FROM transactions GROUP BY shop_id")
    shop_stats = cur.fetchall()
    cur.execute("SELECT customer_id, COUNT(*), SUM(bill_amount), SUM(promotion_amount) FROM transactions GROUP BY customer_id")
    cust_stats = cur.fetchall()

    return render_template("superadmin_dashboard.html",
                           name=session["user_name"],
                           users=users,
                           transactions=transactions,
                           shop_stats=shop_stats,
                           cust_stats=cust_stats)

# Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
