from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
import os
import sqlite3
from werkzeug.utils import secure_filename
from functools import wraps

# 🔹 AJOUT FLASK-LOGIN
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required as flask_login_required, current_user

app = Flask(__name__)
app.secret_key = 'votre_cle_secrete'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['PROFILE_PIC_FOLDER'] = 'static/profile_pics'

# 🔹 Config Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROFILE_PIC_FOLDER'], exist_ok=True)

# SUPPRIMER LA BASE DE DONNÉES EXISTANTE
if os.path.exists('pynia.db'):
    os.remove('pynia.db')

# -------------------- BASE DE DONNÉES --------------------

def init_db():
    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            profile_picture TEXT,
            bio TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            text TEXT,
            image TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            author TEXT,
            text TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 🔹 Classe pour Flask-Login
class UserLogin(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return UserLogin(id=user[0], username=user[1])
    return None

# -------------------- FONCTIONS UTILES --------------------

def get_user(username):
    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    return user

def get_user_by_username(username):
    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    c.execute("SELECT username, bio, profile_picture FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    return user

def add_user(username, password, profile_picture=None):
    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, profile_picture, bio) VALUES (?, ?, ?, ?)",
                  (username, password, profile_picture, ""))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_user_profile(username, bio, profile_picture=None):
    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    if profile_picture:
        c.execute("UPDATE users SET bio = ?, profile_picture = ? WHERE username = ?", (bio, profile_picture, username))
    else:
        c.execute("UPDATE users SET bio = ? WHERE username = ?", (bio, username))
    conn.commit()
    conn.close()

def get_posts():
    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    c.execute("SELECT id, author, text, image FROM posts ORDER BY id DESC")
    posts = c.fetchall()
    result = []
    for post in posts:
        c.execute("SELECT profile_picture FROM users WHERE username = ?", (post[1],))
        profile_data = c.fetchone()
        profile_picture = profile_data[0] if profile_data else None

        c.execute("SELECT author, text FROM comments WHERE post_id = ?", (post[0],))
        comments = [{'author': com[0], 'text': com[1]} for com in c.fetchall()]
        result.append({
            'id': post[0],
            'author': post[1],
            'text': post[2],
            'image': post[3],
            'profile_picture': profile_picture,
            'comments': comments
        })
    conn.close()
    return result

def add_post(author, text, image_path):
    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    c.execute("INSERT INTO posts (author, text, image) VALUES (?, ?, ?)", (author, text, image_path))
    conn.commit()
    conn.close()

# ⛔ DEVIENT INUTILE si tu utilises Flask-Login
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapped

def get_current_user():
    if 'username' in session:
        return get_user_by_username(session['username'])
    return None

# -------------------- ROUTES --------------------

@app.route('/')
@flask_login_required
def index():
    posts = get_posts()
    return render_template('index.html', posts=posts, username=current_user.username)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        file = request.files.get('profile_picture')
        filename = None

        if file and file.filename != '':
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['PROFILE_PIC_FOLDER'], filename)
            file.save(filepath)

        if add_user(username, password, filename):
            user_data = get_user(username)
            login_user(UserLogin(id=user_data[0], username=user_data[1]))
            return redirect(url_for('index'))
        else:
            return 'Nom d’utilisateur déjà pris !'
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user(username)
        if user is not None and user[2] == password:
            login_user(UserLogin(id=user[0], username=user[1]))
            return redirect(url_for('index'))
        else:
            return 'Identifiants incorrects !'
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/post', methods=['GET', 'POST'])
@flask_login_required
def post():
    if request.method == 'POST':
        text = request.form['text']
        image = request.files.get('image')

        image_path = None
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)

        add_post(current_user.username, text, image_path)
        return redirect(url_for('index'))

    return render_template('post.html')

@app.route('/api/comment/<int:post_id>', methods=['POST'])
def api_add_comment(post_id):
    if not current_user.is_authenticated:
        return jsonify({'error': 'Non connecté'}), 403

    comment_text = request.json.get('comment_text', '')
    if not comment_text:
        return jsonify({'error': 'Commentaire vide'}), 400

    conn = sqlite3.connect('pynia.db')
    c = conn.cursor()
    c.execute("INSERT INTO comments (post_id, author, text) VALUES (?, ?, ?)",
              (post_id, current_user.username, comment_text))
    conn.commit()
    conn.close()

    return jsonify({
        'author': current_user.username,
        'text': comment_text
    })

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '')
    users = []
    if query:
        conn = sqlite3.connect('pynia.db')
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username LIKE ?", ('%' + query + '%',))
        users = cursor.fetchall()
        conn.close()
    return render_template('search.html', users=users, query=query)

@app.route('/profil/<username>')
def view_profile(username):
    user = get_user_by_username(username)
    if user is not None:
        return render_template('profile.html', user=user)
    return "Profil introuvable", 404

@app.route('/modifier-profil', methods=['GET', 'POST'])
@flask_login_required
def edit_profile():
    user = get_user_by_username(current_user.username)

    if user is None:
        return "Utilisateur introuvable", 404

    if request.method == 'POST':
        bio = request.form['bio']
        file = request.files.get('profile_picture')
        filename = user[2] if len(user) > 2 else None

        if file and file.filename != '':
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['PROFILE_PIC_FOLDER'], filename)
            file.save(filepath)

        update_user_profile(current_user.username, bio, filename)
        return redirect(url_for('view_profile', username=current_user.username))

    return render_template('edit_profile.html', user=user)

@app.route('/modify_account', methods=['GET', 'POST'])
@flask_login_required
def modify_account():
    if request.method == 'POST':
        bio = request.form.get('bio')
        profile_picture_url = request.form.get('profile_picture_url')

        conn = sqlite3.connect('pynia.db')
        conn.execute('UPDATE users SET bio = ?, profile_picture = ? WHERE username = ?', 
                     (bio, profile_picture_url, current_user.username))
        conn.commit()
        conn.close()

        return redirect(url_for('view_profile', username=current_user.username))

    return render_template('modify_account.html', current_user=get_user_by_username(current_user.username))

@app.route('/rec')
def rec_page():
    return render_template('rec.html')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8090, debug=True)
