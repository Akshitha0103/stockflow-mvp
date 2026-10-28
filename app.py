import os
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-this-secret-before-deployment")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "stockflow.db"))
DEFAULT_THRESHOLD = 5

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS organizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        default_threshold INTEGER NOT NULL DEFAULT 5,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        sku TEXT NOT NULL COLLATE NOCASE,
        description TEXT,
        quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
        cost_price REAL,
        selling_price REAL,
        low_stock_threshold INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(organization_id, sku),
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
    );
    """)
    db.commit()
    db.close()

@app.before_request
def ensure_db():
    init_db()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def current_user():
    if not session.get("user_id"):
        return None
    return get_db().execute("""
        SELECT users.id, users.email, users.organization_id, organizations.name AS organization_name,
               organizations.default_threshold
        FROM users JOIN organizations ON organizations.id = users.organization_id
        WHERE users.id = ?
    """, (session["user_id"],)).fetchone()

@app.context_processor
def inject_user():
    return {"current_user": current_user()}

@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        org_name = request.form.get("organization_name", "").strip()
        if not email or "@" not in email or len(email) > 254:
            flash("Enter a valid email address.", "danger")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif not org_name or len(org_name) > 100:
            flash("Organization name is required (maximum 100 characters).", "danger")
        else:
            db = get_db()
            try:
                cur = db.execute("INSERT INTO organizations (name) VALUES (?)", (org_name,))
                org_id = cur.lastrowid
                cur = db.execute(
                    "INSERT INTO users (organization_id, email, password_hash) VALUES (?, ?, ?)",
                    (org_id, email, generate_password_hash(password))
                )
                db.commit()
                session.clear()
                session["user_id"] = cur.lastrowid
                flash("Welcome to StockFlow! Your workspace is ready.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                db.rollback()
                flash("That email is already registered.", "danger")
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("You're signed in.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db, user = get_db(), current_user()
    org_id = user["organization_id"]
    stats = db.execute("""
        SELECT COUNT(*) AS product_count, COALESCE(SUM(quantity), 0) AS total_units,
               COALESCE(SUM(quantity * COALESCE(cost_price, 0)), 0) AS cost_value,
               COALESCE(SUM(quantity * COALESCE(selling_price, 0)), 0) AS retail_value
        FROM products WHERE organization_id = ?
    """, (org_id,)).fetchone()
    low_stock = db.execute("""
        SELECT *, COALESCE(low_stock_threshold, ?) AS effective_threshold
        FROM products WHERE organization_id = ?
        AND quantity <= COALESCE(low_stock_threshold, ?)
        ORDER BY quantity ASC, name ASC LIMIT 8
    """, (user["default_threshold"], org_id, user["default_threshold"])).fetchall()
    recent = db.execute("SELECT * FROM products WHERE organization_id = ? ORDER BY updated_at DESC LIMIT 5",
                        (org_id,)).fetchall()
    return render_template("dashboard.html", stats=stats, low_stock=low_stock, recent=recent)

def parse_product_form():
    name = request.form.get("name", "").strip()
    sku = request.form.get("sku", "").strip()
    description = request.form.get("description", "").strip()
    quantity_raw = request.form.get("quantity", "0").strip()
    cost_raw = request.form.get("cost_price", "").strip()
    selling_raw = request.form.get("selling_price", "").strip()
    threshold_raw = request.form.get("low_stock_threshold", "").strip()
    if not name or len(name) > 120:
        raise ValueError("Product name is required and must be at most 120 characters.")
    if not sku or len(sku) > 60:
        raise ValueError("SKU is required and must be at most 60 characters.")
    try:
        quantity = int(quantity_raw)
        if quantity < 0: raise ValueError()
    except ValueError:
        raise ValueError("Quantity must be a whole number of 0 or more.")
    def price(value, label):
        if not value: return None
        try:
            n = float(value)
            if n < 0: raise ValueError()
            return n
        except ValueError:
            raise ValueError(f"{label} must be a valid non-negative number.")
    cost, selling = price(cost_raw, "Cost price"), price(selling_raw, "Selling price")
    threshold = None
    if threshold_raw:
        try:
            threshold = int(threshold_raw)
            if threshold < 0: raise ValueError()
        except ValueError:
            raise ValueError("Low-stock threshold must be a whole number of 0 or more.")
    return (name, sku, description, quantity, cost, selling, threshold)

@app.route("/products")
@login_required
def products():
    q = request.args.get("q", "").strip()
    org_id = current_user()["organization_id"]
    db = get_db()
    user = current_user()
    rows = db.execute("""
        SELECT *, COALESCE(low_stock_threshold, ?) AS effective_threshold
        FROM products WHERE organization_id = ?
        AND (name LIKE ? OR sku LIKE ?)
        ORDER BY name COLLATE NOCASE
    """, (user["default_threshold"], org_id, f"%{q}%", f"%{q}%")).fetchall()
    return render_template("products.html", products=rows, q=q)

@app.route("/products/new", methods=["GET", "POST"])
@login_required
def product_new():
    if request.method == "POST":
        try:
            values = parse_product_form()
            user = current_user()
            get_db().execute("""
                INSERT INTO products (organization_id, name, sku, description, quantity, cost_price,
                                      selling_price, low_stock_threshold)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user["organization_id"], *values))
            get_db().commit()
            flash("Product created successfully.", "success")
            return redirect(url_for("products"))
        except ValueError as e:
            flash(str(e), "danger")
        except sqlite3.IntegrityError:
            get_db().rollback()
            flash("That SKU already exists in your organization.", "danger")
    return render_template("product_form.html", product=None, page_title="Add product")

@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def product_edit(product_id):
    org_id = current_user()["organization_id"]
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ? AND organization_id = ?",
                         (product_id, org_id)).fetchone()
    if not product:
        flash("Product not found.", "warning")
        return redirect(url_for("products"))
    if request.method == "POST":
        try:
            values = parse_product_form()
            db.execute("""
                UPDATE products SET name=?, sku=?, description=?, quantity=?, cost_price=?, selling_price=?,
                    low_stock_threshold=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND organization_id=?
            """, (*values, product_id, org_id))
            db.commit()
            flash("Product updated.", "success")
            return redirect(url_for("products"))
        except ValueError as e:
            flash(str(e), "danger")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("That SKU already exists in your organization.", "danger")
    return render_template("product_form.html", product=product, page_title="Edit product")

@app.post("/products/<int:product_id>/delete")
@login_required
def product_delete(product_id):
    org_id = current_user()["organization_id"]
    cur = get_db().execute("DELETE FROM products WHERE id = ? AND organization_id = ?", (product_id, org_id))
    get_db().commit()
    flash("Product deleted." if cur.rowcount else "Product not found.", "success" if cur.rowcount else "warning")
    return redirect(url_for("products"))

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = current_user()
    if request.method == "POST":
        try:
            threshold = int(request.form.get("default_threshold", "5"))
            if threshold < 0: raise ValueError()
            get_db().execute("UPDATE organizations SET default_threshold=? WHERE id=?",
                             (threshold, user["organization_id"]))
            get_db().commit()
            flash("Settings saved.", "success")
            return redirect(url_for("settings"))
        except ValueError:
            flash("Default threshold must be a whole number of 0 or more.", "danger")
    return render_template("settings.html", user=current_user())

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404

if __name__ == "__main__":
    init_db()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
