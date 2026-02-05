// Quantity Selector Functions
function increaseQuantity() {
    const quantityInput = document.getElementById('quantity');
    const currentValue = parseInt(quantityInput.value);
    const maxValue = parseInt(quantityInput.max);
    
    if (currentValue < maxValue) {
        quantityInput.value = currentValue + 1;
    }
}

function decreaseQuantity() {
    const quantityInput = document.getElementById('quantity');
    const currentValue = parseInt(quantityInput.value);
    const minValue = parseInt(quantityInput.min);
    
    if (currentValue > minValue) {
        quantityInput.value = currentValue - 1;
    }
}

// Thumbnail Gallery Functionality
document.addEventListener('DOMContentLoaded', function() {
    const thumbnails = document.querySelectorAll('.thumbnail');
    const mainImage = document.querySelector('.main-image');
    
    thumbnails.forEach(thumbnail => {
        thumbnail.addEventListener('click', function() {
            // Remove active class from all thumbnails
            thumbnails.forEach(thumb => thumb.classList.remove('active'));
            
            // Add active class to clicked thumbnail
            this.classList.add('active');
            
            // Change main image source
            const thumbnailSrc = this.src;
            const mainImageSrc = thumbnailSrc.replace('/80/80', '/600/600');
            mainImage.src = mainImageSrc;
        });
    });
});

// Add to Cart functionality
document.querySelector('.add-to-cart').addEventListener('click', function() {
    const quantity = document.getElementById('quantity').value;
    const productName = document.querySelector('.product-title').textContent;
    
    // Show success message
    showNotification(`${quantity} × ${productName} added to cart!`);
    
    // Update cart count
    updateCartCount(quantity);
});

// Add to Wishlist functionality
document.querySelector('.add-to-wishlist').addEventListener('click', function() {
    const productName = document.querySelector('.product-title').textContent;
    
    // Toggle wishlist state
    this.classList.toggle('active');
    
    if (this.classList.contains('active')) {
        this.innerHTML = '<i class="fas fa-heart"></i> Added to Wishlist';
        showNotification(`${productName} added to wishlist!`);
    } else {
        this.innerHTML = '<i class="fas fa-heart"></i> Add to Wishlist';
        showNotification(`${productName} removed from wishlist!`);
    }
});

// Update Cart Count
function updateCartCount(quantity) {
    const cartCount = document.querySelector('.cart-count');
    const currentCount = parseInt(cartCount.textContent);
    cartCount.textContent = currentCount + parseInt(quantity);
    
    // Add animation to cart icon
    const cartBtn = document.querySelector('.cart-btn');
    cartBtn.style.transform = 'scale(1.2)';
    setTimeout(() => {
        cartBtn.style.transform = 'scale(1)';
    }, 200);
}

// Show Notification
function showNotification(message) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.textContent = message;
    
    // Style notification
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #4CAF50;
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        z-index: 1000;
        transform: translateX(100%);
        transition: transform 0.3s ease;
        font-weight: 500;
    `;
    
    // Add to body
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Write Review Button
document.querySelector('.write-review-btn').addEventListener('click', function() {
    showNotification('Review form coming soon!');
});

// Social Share functionality
document.querySelectorAll('.social-link').forEach(link => {
    link.addEventListener('click', function(e) {
        e.preventDefault();
        const platform = this.querySelector('i').className;
        
        if (platform.includes('facebook')) {
            showNotification('Share on Facebook coming soon!');
        } else if (platform.includes('twitter')) {
            showNotification('Share on Twitter coming soon!');
        } else if (platform.includes('instagram')) {
            showNotification('Share on Instagram coming soon!');
        }
    });
});

// Review Image Gallery
document.querySelectorAll('.review-images img').forEach(img => {
    img.addEventListener('click', function() {
        // Create lightbox effect
        const lightbox = document.createElement('div');
        lightbox.className = 'lightbox';
        
        const lightboxImg = document.createElement('img');
        lightboxImg.src = this.src.replace('/60/60', '/400/400');
        lightboxImg.alt = 'Review Image';
        
        lightbox.appendChild(lightboxImg);
        document.body.appendChild(lightbox);
        
        // Style lightbox
        lightbox.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            cursor: pointer;
        `;
        
        lightboxImg.style.cssText = `
            max-width: 90%;
            max-height: 90%;
            border-radius: 8px;
        `;
        
        // Close on click
        lightbox.addEventListener('click', function() {
            document.body.removeChild(lightbox);
        });
    });
});

// Search functionality
document.querySelector('.search-btn').addEventListener('click', function() {
    showNotification('Search functionality coming soon!');
});

// Smooth scroll for navigation
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', function(e) {
        e.preventDefault();
        showNotification('Navigation links coming soon!');
    });
});

// Add hover effects for buttons
document.querySelectorAll('.btn').forEach(button => {
    button.addEventListener('mouseenter', function() {
        this.style.transform = 'translateY(-2px)';
    });
    
    button.addEventListener('mouseleave', function() {
        this.style.transform = 'translateY(0)';
    });
});

// Keyboard navigation for quantity selector
document.getElementById('quantity').addEventListener('keydown', function(e) {
    if (e.key === 'ArrowUp') {
        e.preventDefault();
        increaseQuantity();
    } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        decreaseQuantity();
    }
});

// Add loading states
document.querySelectorAll('.btn').forEach(button => {
    button.addEventListener('click', function() {
        const originalText = this.innerHTML;
        this.disabled = true;
        
        if (this.classList.contains('add-to-cart')) {
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Adding...';
        } else if (this.classList.contains('add-to-wishlist')) {
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Updating...';
        }
        
        setTimeout(() => {
            this.disabled = false;
            this.innerHTML = originalText;
        }, 1000);
    });
});

// Add to wishlist active state styling
const style = document.createElement('style');
style.textContent = `
    .add-to-wishlist.active {
        background: #2196F3 !important;
        color: white !important;
    }
    
    .notification {
        animation: slideIn 0.3s ease;
    }
    
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
`;
document.head.appendChild(style);
