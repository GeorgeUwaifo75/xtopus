// Navigation toggle for mobile
document.addEventListener('DOMContentLoaded', function() {
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', function() {
            navMenu.classList.toggle('active');
        });
    }
    
    // Close menu when clicking outside
    document.addEventListener('click', function(event) {
        const isClickInside = navToggle?.contains(event.target) || navMenu?.contains(event.target);
        if (!isClickInside && navMenu?.classList.contains('active')) {
            navMenu.classList.remove('active');
        }
    });
});

// Toast notification system
class Toast {
    static show(message, type = 'success', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
                <span>${message}</span>
            </div>
            <button class="toast-close">&times;</button>
        `;
        
        const container = document.getElementById('toast-container') || createToastContainer();
        container.appendChild(toast);
        
        // Auto remove
        setTimeout(() => {
            toast.remove();
        }, duration);
        
        // Close button
        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.remove();
        });
    }
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 9999;
        display: flex;
        flex-direction: column;
        gap: 10px;
    `;
    document.body.appendChild(container);
    return container;
}

// Add toast styles
const style = document.createElement('style');
style.textContent = `
    .toast {
        background: white;
        padding: 1rem 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        display: flex;
        align-items: center;
        justify-content: space-between;
        min-width: 300px;
        max-width: 450px;
        animation: slideIn 0.3s ease;
    }
    
    .toast-success {
        border-left: 4px solid #10B981;
    }
    
    .toast-error {
        border-left: 4px solid #EF4444;
    }
    
    .toast-info {
        border-left: 4px solid #8B5CF6;
    }
    
    .toast-content {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    
    .toast-content i {
        font-size: 1.25rem;
    }
    
    .toast-success i { color: #10B981; }
    .toast-error i { color: #EF4444; }
    .toast-info i { color: #8B5CF6; }
    
    .toast-close {
        background: none;
        border: none;
        font-size: 1.5rem;
        cursor: pointer;
        color: #9CA3AF;
        padding: 0 0 0 1rem;
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

// Form validation helper
class FormValidator {
    static validateEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }
    
    static validatePhone(phone) {
        return /^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$/.test(phone);
    }
    
    static validatePassword(password) {
        return password.length >= 8;
    }
    
    static showError(input, message) {
        const formGroup = input.closest('.form-group');
        const existingError = formGroup?.querySelector('.form-error');
        if (existingError) existingError.remove();
        
        const error = document.createElement('span');
        error.className = 'form-error';
        error.style.cssText = 'color: #EF4444; font-size: 0.875rem; margin-top: 0.25rem; display: block;';
        error.textContent = message;
        formGroup?.appendChild(error);
        
        input.style.borderColor = '#EF4444';
    }
    
    static clearErrors(form) {
        form.querySelectorAll('.form-error').forEach(el => el.remove());
        form.querySelectorAll('.form-control').forEach(el => {
            el.style.borderColor = '';
        });
    }
}

// API Helper
// Update the API class to use the correct base path
class API {
    static async request(endpoint, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include'
        };
        
        const mergedOptions = { ...defaultOptions, ...options };
        
        if (mergedOptions.body && typeof mergedOptions.body === 'object') {
            mergedOptions.body = JSON.stringify(mergedOptions.body);
        }
        
        try {
            // Remove /api prefix as it's already in the endpoint
            const url = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
            const response = await fetch(url, mergedOptions);
            
            // Check if response is a redirect (303)
            if (response.status === 303 || response.redirected) {
                window.location.href = response.url;
                return;
            }
            
            const data = await response.json().catch(() => ({}));
            
            if (!response.ok) {
                throw new Error(data.detail || 'Something went wrong');
            }
            
            return data;
        } catch (error) {
            if (error.message !== 'Failed to fetch') {
                Toast.show(error.message, 'error');
            }
            throw error;
        }
    }
}

// File upload helper
class FileUpload {
    static async uploadToFirebase(file, path) {
        // This would be implemented with Firebase Storage SDK
        // For now, we'll simulate the upload
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                // Simulate upload delay
                setTimeout(() => {
                    resolve({
                        url: e.target.result,
                        name: file.name,
                        size: file.size
                    });
                }, 1000);
            };
            reader.readAsDataURL(file);
        });
    }
}

// Paystack payment integration
class PaymentHandler {
    static async initializePayment(email, amount, metadata = {}) {
        return new Promise((resolve, reject) => {
            const handler = PaystackPop.setup({
                key: 'YOUR_PAYSTACK_PUBLIC_KEY',
                email: email,
                amount: amount * 100, // Convert to kobo
                metadata: metadata,
                callback: function(response) {
                    resolve(response);
                },
                onClose: function() {
                    reject(new Error('Payment window closed'));
                }
            });
            handler.openIframe();
        });
    }
    
    static async processSubscription(userId, plan) {
        const plans = {
            monthly: 15000,
            annually: 162000
        };
        
        const amount = plans[plan];
        if (!amount) {
            throw new Error('Invalid subscription plan');
        }
        
        return this.initializePayment(userId, amount, {
            plan: plan,
            userId: userId
        });
    }
}