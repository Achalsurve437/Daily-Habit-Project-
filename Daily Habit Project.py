from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import sqlite3
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Database setup
def init_db():
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            target_hours REAL DEFAULT 0,
            category TEXT DEFAULT 'General',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            hours REAL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            habit_id INTEGER NOT NULL,
            FOREIGN KEY (habit_id) REFERENCES habits (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Database helper functions
def get_db():
    conn = sqlite3.connect('habits.db')
    conn.row_factory = sqlite3.Row
    return conn

def query_db(query, args=(), one=False):
    conn = get_db()
    cursor = conn.execute(query, args)
    rv = cursor.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if username exists
        existing_user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
        if existing_user:
            flash('Username already exists')
            return render_template('register.html')
        
        # Check if email exists
        existing_email = query_db('SELECT * FROM users WHERE email = ?', [email], one=True)
        if existing_email:
            flash('Email already registered')
            return render_template('register.html')
        
        # Create new user
        conn = get_db()
        conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                    [username, email, generate_password_hash(password)])
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = query_db('SELECT * FROM users WHERE id = ?', [session['user_id']], one=True)
    habits = query_db('SELECT * FROM habits WHERE user_id = ?', [session['user_id']])
    
    # Get recent logs for the last 7 days
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=6)
    
    recent_logs = []
    for habit in habits:
        logs = query_db('''
            SELECT * FROM habit_logs 
            WHERE habit_id = ? AND date >= ? AND date <= ?
        ''', [habit['id'], start_date, end_date])
        
        total_hours = sum(log['hours'] for log in logs)
        recent_logs.append({
            'habit': habit,
            'logs': logs,
            'total_hours': total_hours
        })
    
    return render_template('dashboard.html', user=user, habits=habits, recent_logs=recent_logs)

@app.route('/habits')
def habits():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = query_db('SELECT * FROM users WHERE id = ?', [session['user_id']], one=True)
    habits = query_db('SELECT * FROM habits WHERE user_id = ?', [session['user_id']])
    return render_template('habits.html', habits=habits)

@app.route('/habits/new', methods=['GET', 'POST'])
def new_habit():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        target_hours = float(request.form['target_hours'])
        category = request.form['category']
        
        conn = get_db()
        conn.execute('''
            INSERT INTO habits (name, description, target_hours, category, user_id) 
            VALUES (?, ?, ?, ?, ?)
        ''', [name, description, target_hours, category, session['user_id']])
        conn.commit()
        conn.close()
        
        flash('Habit created successfully!')
        return redirect(url_for('habits'))
    
    return render_template('new_habit.html')

@app.route('/habits/<int:habit_id>/log', methods=['GET', 'POST'])
def log_habit(habit_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    habit = query_db('SELECT * FROM habits WHERE id = ? AND user_id = ?', [habit_id, session['user_id']], one=True)
    if not habit:
        flash('Access denied')
        return redirect(url_for('habits'))
    
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        hours = float(request.form['hours'])
        notes = request.form['notes']
        
        # Check if log already exists for this date
        existing_log = query_db('SELECT * FROM habit_logs WHERE habit_id = ? AND date = ?', [habit_id, date], one=True)
        
        conn = get_db()
        if existing_log:
            conn.execute('UPDATE habit_logs SET hours = ?, notes = ? WHERE habit_id = ? AND date = ?',
                        [hours, notes, habit_id, date])
        else:
            conn.execute('INSERT INTO habit_logs (date, hours, notes, habit_id) VALUES (?, ?, ?, ?)',
                        [date, hours, notes, habit_id])
        
        conn.commit()
        conn.close()
        flash('Habit logged successfully!')
        return redirect(url_for('habits'))
    
    today = datetime.now().date()
    return render_template('log_habit.html', habit=habit, today=today)

@app.route('/api/habits/<int:habit_id>/progress')
def habit_progress(habit_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    habit = query_db('SELECT * FROM habits WHERE id = ? AND user_id = ?', [habit_id, session['user_id']], one=True)
    if not habit:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get logs for the last 30 days
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=29)
    
    logs = query_db('''
        SELECT * FROM habit_logs 
        WHERE habit_id = ? AND date >= ? AND date <= ?
        ORDER BY date
    ''', [habit_id, start_date, end_date])
    
    data = {
        'labels': [],
        'hours': [],
        'target': habit['target_hours']
    }
    
    current_date = start_date
    while current_date <= end_date:
        data['labels'].append(current_date.strftime('%m/%d'))
        log = next((l for l in logs if l['date'] == current_date), None)
        data['hours'].append(log['hours'] if log else 0)
        current_date += timedelta(days=1)
    
    return jsonify(data)

@app.route('/api/dashboard/stats')
def dashboard_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = query_db('SELECT * FROM users WHERE id = ?', [session['user_id']], one=True)
    habits = query_db('SELECT * FROM habits WHERE user_id = ?', [session['user_id']])
    
    # Get today's logs
    today = datetime.now().date()
    today_logs = query_db('''
        SELECT hl.* FROM habit_logs hl
        JOIN habits h ON hl.habit_id = h.id
        WHERE h.user_id = ? AND hl.date = ?
    ''', [session['user_id'], today])
    
    # Get this week's logs
    week_start = today - timedelta(days=today.weekday())
    week_logs = query_db('''
        SELECT hl.* FROM habit_logs hl
        JOIN habits h ON hl.habit_id = h.id
        WHERE h.user_id = ? AND hl.date >= ? AND hl.date <= ?
    ''', [session['user_id'], week_start, today])
    
    stats = {
        'total_habits': len(habits),
        'today_hours': sum(log['hours'] for log in today_logs),
        'week_hours': sum(log['hours'] for log in week_logs),
        'completed_today': len([log for log in today_logs if log['hours'] > 0]),
        'total_target': sum(habit['target_hours'] for habit in habits)
    }
    
    return jsonify(stats)

if __name__ == '__main__':
    init_db()
    app.run(debug=True) 