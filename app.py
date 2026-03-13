from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import uuid
import json

app = Flask(__name__, instance_relative_config=True)
app.config['SECRET_KEY'] = 'celebrity-management-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///celebrity_booking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(255), default='default.jpg')
    availability = db.Column(db.Text, nullable=False)  # JSON string of available dates
    duration = db.Column(db.String(50), default='1 hour')
    category = db.Column(db.String(50), default='General')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='service', lazy=True)
    reviews = db.relationship('Review', backref='service', lazy=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    booking_time = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, cancelled, completed
    total_amount = db.Column(db.Float, nullable=False)
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, failed, refunded
    payment_method = db.Column(db.String(50))
    gift_card_code = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

class GiftCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Float, nullable=False)
    balance = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    comment = db.Column(db.Text)
    is_approved = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Create admin user and sample data
def create_admin_and_sample_data():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', email='admin@celebrity.com', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        
        # Create sample services
        services = [
            {
                'name': 'VIP Meet & Greet',
                'description': 'An exclusive one-on-one meeting session with the celebrity. Includes photo opportunities, autographs, and a personalized experience. Perfect for fans who want a memorable encounter.',
                'price': 500.00,
                'category': 'Personal Appearance',
                'duration': '30 minutes',
                'availability': json.dumps(generate_availability())
            },
            {
                'name': 'Private Concert',
                'description': 'Book a private concert for your special event. Full band setup with professional sound and lighting. Ideal for corporate events, weddings, and private parties.',
                'price': 5000.00,
                'category': 'Performance',
                'duration': '90 minutes',
                'availability': json.dumps(generate_availability())
            },
            {
                'name': 'Brand Endorsement',
                'description': 'Professional brand endorsement package including social media posts, photo shoots, and public appearances. Comprehensive marketing package for your brand.',
                'price': 10000.00,
                'category': 'Endorsement',
                'duration': '1 day',
                'availability': json.dumps(generate_availability())
            },
            {
                'name': 'Voice Recording Session',
                'description': 'Professional voice recording for commercials, audiobooks, or special projects. Includes studio time and professional production.',
                'price': 2500.00,
                'category': 'Media',
                'duration': '2 hours',
                'availability': json.dumps(generate_availability())
            },
            {
                'name': 'Keynote Speaking',
                'description': 'Inspiring keynote speeches for conferences, corporate events, and educational institutions. Topics include success, motivation, and industry insights.',
                'price': 7500.00,
                'category': 'Speaking',
                'duration': '60 minutes',
                'availability': json.dumps(generate_availability())
            },
            {
                'name': 'Social Media Shoutout',
                'description': 'Personalized video message for birthdays, anniversaries, or special occasions. Delivered within 48 hours via social media.',
                'price': 150.00,
                'category': 'Digital',
                'duration': '1-2 minutes',
                'availability': json.dumps(generate_availability())
            }
        ]
        
        for service_data in services:
            service = Service(**service_data)
            db.session.add(service)
        
        # Create sample gift cards
        gift_cards = [
            GiftCard(code='GIFT100', value=100.00, balance=100.00),
            GiftCard(code='GIFT250', value=250.00, balance=250.00),
            GiftCard(code='GIFT500', value=500.00, balance=500.00),
            GiftCard(code='VIP1000', value=1000.00, balance=1000.00),
        ]
        for gc in gift_cards:
            db.session.add(gc)
        
        db.session.commit()
        print("Admin user and sample data created successfully!")

def generate_availability():
    """Generate availability for the next 60 days"""
    availability = {}
    today = datetime.now().date()
    for i in range(60):
        date = today + timedelta(days=i)
        # Skip Sundays
        if date.weekday() != 6:
            time_slots = ['09:00', '10:00', '11:00', '14:00', '15:00', '16:00', '17:00']
            availability[date.isoformat()] = time_slots
    return availability

# Routes
@app.route('/')
def index():
    services = Service.query.filter_by(is_active=True).all()
    return render_template('index.html', services=services)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    
    services = Service.query.filter_by(is_active=True)
    
    if query:
        services = services.filter(
            db.or_(
                Service.name.ilike(f'%{query}%'),
                Service.description.ilike(f'%{query}%')
            )
        )
    
    if category:
        services = services.filter_by(category=category)
    
    services = services.all()
    categories = db.session.query(Service.category).distinct().all()
    
    return render_template('search.html', services=services, query=query, categories=categories)

@app.route('/service/<int:service_id>')
def service_detail(service_id):
    service = Service.query.get_or_404(service_id)
    reviews = Review.query.filter_by(service_id=service_id, is_approved=True).order_by(Review.created_at.desc()).all()
    return render_template('service_detail.html', service=service, reviews=reviews)

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Welcome back!', 'success')
            next_page = request.args.get('next')
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

# Booking Routes
@app.route('/book/<int:service_id>', methods=['GET', 'POST'])
@login_required
def book_service(service_id):
    service = Service.query.get_or_404(service_id)
    
    if request.method == 'POST':
        booking_date = request.form.get('booking_date')
        booking_time = request.form.get('booking_time')
        payment_method = request.form.get('payment_method')
        gift_card_code = request.form.get('gift_card_code', '')
        notes = request.form.get('notes', '')
        
        # Validate availability
        availability = json.loads(service.availability)
        if booking_date not in availability or booking_time not in availability[booking_date]:
            flash('Selected time slot is not available', 'error')
            return redirect(url_for('book_service', service_id=service_id))
        
        # Check gift card if selected
        if payment_method == 'gift_card':
            gift_card = GiftCard.query.filter_by(code=gift_card_code, is_active=True).first()
            if not gift_card:
                flash('Invalid gift card code', 'error')
                return redirect(url_for('book_service', service_id=service_id))
            if gift_card.balance < service.price:
                flash('Insufficient gift card balance', 'error')
                return redirect(url_for('book_service', service_id=service_id))
            
            # Deduct from gift card
            gift_card.balance -= service.price
            if gift_card.balance <= 0:
                gift_card.is_active = False
        
        # Create booking
        booking = Booking(
            user_id=current_user.id,
            service_id=service_id,
            booking_date=datetime.strptime(booking_date, '%Y-%m-%d').date(),
            booking_time=booking_time,
            total_amount=service.price,
            payment_status='paid' if payment_method == 'gift_card' else 'pending',
            payment_method=payment_method,
            gift_card_code=gift_card_code if payment_method == 'gift_card' else None,
            notes=notes
        )
        
        # Remove booked time slot from availability
        availability[booking_date].remove(booking_time)
        service.availability = json.dumps(availability)
        
        db.session.add(booking)
        db.session.commit()
        
        flash('Booking confirmed successfully!', 'success')
        return redirect(url_for('user_bookings'))
    
    availability = json.loads(service.availability)
    return render_template('book.html', service=service, availability=availability)

@app.route('/my-bookings')
@login_required
def user_bookings():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()
    return render_template('user/bookings.html', bookings=bookings)

# Review Routes
@app.route('/review/<int:service_id>', methods=['POST'])
@login_required
def add_review(service_id):
    rating = request.form.get('rating')
    comment = request.form.get('comment')
    
    # Check if user has booked this service
    booking = Booking.query.filter_by(user_id=current_user.id, service_id=service_id, status='confirmed').first()
    if not booking:
        flash('You can only review services you have booked', 'error')
        return redirect(url_for('service_detail', service_id=service_id))
    
    # Check if already reviewed
    existing_review = Review.query.filter_by(user_id=current_user.id, service_id=service_id).first()
    if existing_review:
        flash('You have already reviewed this service', 'error')
        return redirect(url_for('service_detail', service_id=service_id))
    
    review = Review(
        user_id=current_user.id,
        service_id=service_id,
        rating=int(rating),
        comment=comment
    )
    db.session.add(review)
    db.session.commit()
    
    flash('Review submitted successfully!', 'success')
    return redirect(url_for('service_detail', service_id=service_id))

# Contact Route
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject', '')
        message = request.form.get('message')
        
        contact_msg = ContactMessage(name=name, email=email, subject=subject, message=message)
        db.session.add(contact_msg)
        db.session.commit()
        
        flash('Message sent successfully! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

# Admin Routes
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    total_bookings = Booking.query.count()
    total_revenue = db.session.query(db.func.sum(Booking.total_amount)).filter(Booking.payment_status == 'paid').scalar() or 0
    total_users = User.query.filter_by(is_admin=False).count()
    total_services = Service.query.count()
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html', 
                         total_bookings=total_bookings,
                         total_revenue=total_revenue,
                         total_users=total_users,
                         total_services=total_services,
                         recent_bookings=recent_bookings)

@app.route('/admin/services')
@login_required
def admin_services():
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    services = Service.query.order_by(Service.created_at.desc()).all()
    return render_template('admin/services.html', services=services)

@app.route('/admin/services/add', methods=['GET', 'POST'])
@login_required
def add_service():
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        category = request.form.get('category')
        duration = request.form.get('duration')
        
        # Handle image upload
        image_url = 'default.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add unique identifier to prevent conflicts
                unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                image_url = unique_filename
        
        # Generate availability
        availability = json.dumps(generate_availability())
        
        service = Service(
            name=name,
            description=description,
            price=price,
            category=category,
            duration=duration,
            image_url=image_url,
            availability=availability
        )
        
        db.session.add(service)
        db.session.commit()
        
        flash('Service added successfully!', 'success')
        return redirect(url_for('admin_services'))
    
    categories = ['Personal Appearance', 'Performance', 'Endorsement', 'Media', 'Speaking', 'Digital']
    return render_template('admin/add_service.html', categories=categories)

@app.route('/admin/services/edit/<int:service_id>', methods=['GET', 'POST'])
@login_required
def edit_service(service_id):
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    service = Service.query.get_or_404(service_id)
    
    if request.method == 'POST':
        service.name = request.form.get('name')
        service.description = request.form.get('description')
        service.price = float(request.form.get('price'))
        service.category = request.form.get('category')
        service.duration = request.form.get('duration')
        service.is_active = 'is_active' in request.form
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                service.image_url = unique_filename
        
        db.session.commit()
        flash('Service updated successfully!', 'success')
        return redirect(url_for('admin_services'))
    
    categories = ['Personal Appearance', 'Performance', 'Endorsement', 'Media', 'Speaking', 'Digital']
    return render_template('admin/edit_service.html', service=service, categories=categories)

@app.route('/admin/services/delete/<int:service_id>', methods=['POST'])
@login_required
def delete_service(service_id):
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    service = Service.query.get_or_404(service_id)
    db.session.delete(service)
    db.session.commit()
    
    flash('Service deleted successfully!', 'success')
    return redirect(url_for('admin_services'))

@app.route('/admin/bookings')
@login_required
def admin_bookings():
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    return render_template('admin/bookings.html', bookings=bookings)

@app.route('/admin/bookings/update/<int:booking_id>', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    booking = Booking.query.get_or_404(booking_id)
    status = request.form.get('status')
    booking.status = status
    db.session.commit()
    
    flash('Booking status updated!', 'success')
    return redirect(url_for('admin_bookings'))

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    users = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/messages')
@login_required
def admin_messages():
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template('admin/messages.html', messages=messages)

@app.route('/admin/gift-cards')
@login_required
def admin_gift_cards():
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    gift_cards = GiftCard.query.order_by(GiftCard.created_at.desc()).all()
    return render_template('admin/gift_cards.html', gift_cards=gift_cards)

@app.route('/admin/gift-cards/add', methods=['POST'])
@login_required
def add_gift_card():
    if not current_user.is_admin:
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('index'))
    
    code = request.form.get('code')
    value = float(request.form.get('value'))
    
    if GiftCard.query.filter_by(code=code).first():
        flash('Gift card code already exists', 'error')
        return redirect(url_for('admin_gift_cards'))
    
    gift_card = GiftCard(code=code, value=value, balance=value)
    db.session.add(gift_card)
    db.session.commit()
    
    flash('Gift card created successfully!', 'success')
    return redirect(url_for('admin_gift_cards'))

# API endpoint for checking availability
@app.route('/api/availability/<int:service_id>/<date>')
def get_availability(service_id, date):
    service = Service.query.get_or_404(service_id)
    availability = json.loads(service.availability)
    time_slots = availability.get(date, [])
    return jsonify({'date': date, 'available_slots': time_slots})

with app.app_context():
    db.create_all()
    create_admin_and_sample_data()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=3000)