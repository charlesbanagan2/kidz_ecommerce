# Kids & Baby E-commerce Platform

A comprehensive e-commerce platform specialized in kids and baby products, built with Flask, Bootstrap, and SQLite.

## Features

### User Roles
- **Buyers**: Browse products, manage cart, place orders
- **Sellers**: Apply for seller status, manage products and orders
- **Admins**: Approve sellers, manage platform, view analytics

### Core Functionality
- User registration and authentication
- Seller application and approval system
- Product catalog with categories
- Shopping cart and checkout
- Order management
- Payment integration (PayMongo)
- Admin dashboard with analytics

## Setup Instructions

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure PayMongo** (Optional)
   - Sign up at [PayMongo Dashboard](https://dashboard.paymongo.com)
   - Get your test API keys
   - Update the keys in `app.py`:
     ```python
     PAYMONGO_PUBLIC_KEY = 'pk_test_your_actual_key'
     PAYMONGO_SECRET_KEY = 'sk_test_your_actual_key'
     ```

3. **Run the Application**
   ```bash
   python app.py
   ```

4. **Access the Platform**
   - Open browser to `http://localhost:5000`
   - The database and default admin user will be created automatically

## Default Admin Credentials
- **Email**: admin@kidscommerce.com
- **Password**: admin123

## Project Structure
```
kids/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── kids_ecommerce.db     # SQLite database (auto-created)
├── templates/            # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── seller_register.html
│   ├── shop.html
│   ├── cart.html
│   ├── checkout.html
│   ├── order_confirmation.html
│   ├── admin/
│   │   ├── dashboard.html
│   │   └── seller_applications.html
│   └── seller/
│       ├── dashboard.html
│       ├── add_product.html
│       └── orders.html
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── main.js
│   └── uploads/          # Product images (auto-created)
```

## Categories
The platform comes with pre-configured categories:
- Baby Clothes & Accessories
- Toys & Games
- Strollers & Gear
- Nursery Furniture
- Safety and Health
- Educational Materials

## User Flows

### Buyer Journey
1. Browse homepage and products
2. Register/Login to add items to cart
3. Proceed to checkout
4. Choose payment method (COD, GCash, Maya, Card)
5. Receive order confirmation

### Seller Journey
1. Apply using "Start Selling" button
2. Wait for admin approval
3. Access seller dashboard upon approval
4. Add products with images
5. Manage orders and track sales

### Admin Journey
1. Login with admin credentials
2. Review seller applications
3. Approve/reject sellers
4. Monitor platform analytics
5. Manage users and products

## Payment Methods
- Cash on Delivery (COD)
- GCash (via PayMongo)
- Maya/PayMaya (via PayMongo)
- Credit/Debit Cards (via PayMongo)

## Database Schema
- **User**: User accounts with roles
- **SellerApplication**: Seller registration requests
- **Category**: Product categories
- **Product**: Product catalog
- **Order**: Customer orders
- **OrderItem**: Individual order items
- **Cart**: Shopping cart items
- **Wishlist**: User wishlists

## Security Notes
⚠️ **Important**: This implementation uses plaintext passwords as requested for development. For production:
- Implement password hashing with bcrypt
- Add CSRF protection
- Use environment variables for secrets
- Enable HTTPS
- Add rate limiting

## Testing
The application includes test mode for PayMongo integration. No real payments will be processed in test mode.

## Future Enhancements
- Email notifications
- Review and rating system
- Advanced search and filtering
- Mobile app API
- Multi-vendor commission system
- Inventory alerts
