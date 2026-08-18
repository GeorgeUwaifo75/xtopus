# routers/payments.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime, timedelta
import logging
import uuid
import os
import requests
import json
import hmac
import hashlib

router = APIRouter()
logger = logging.getLogger(__name__)

from database import db
from security import security

# ============================================
# ENVIRONMENT VARIABLES (Read from .env or Render environment)
# ============================================
# Paystack Configuration - Read from environment variables
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY')
PAYSTACK_API_URL = 'https://api.paystack.co'

# EmailJS Configuration
EMAILJS_SERVICE_ID = os.getenv('EMAILJS_SERVICE_ID')
EMAILJS_TEMPLATE_ID = os.getenv('EMAILJS_TEMPLATE_ID')
EMAILJS_PUBLIC_KEY = os.getenv('EMAILJS_PUBLIC_KEY')
EMAILJS_API_URL = 'https://api.emailjs.com/api/v1.0/email/send'

# Log configuration status
logger.info(f"Paystack Public Key configured: {bool(PAYSTACK_PUBLIC_KEY)}")
logger.info(f"Paystack Secret Key configured: {bool(PAYSTACK_SECRET_KEY)}")
logger.info(f"EmailJS configured: {all([EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, EMAILJS_PUBLIC_KEY])}")

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_current_user(request: Request):
    """Get current user from session token"""
    token = request.cookies.get("session_token")
    if not token:
        return None
    user_data = security.get_current_user(token)
    if not user_data:
        return None
    return user_data

def send_emailjs_notification(to_email: str, subject: str, body: str, template_params: dict = None) -> bool:
    """Send email notification via EmailJS"""
    try:
        # Check if EmailJS is configured
        if not all([EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, EMAILJS_PUBLIC_KEY]):
            logger.warning("EmailJS credentials not configured. Email not sent.")
            return False
        
        params = {
            'service_id': EMAILJS_SERVICE_ID,
            'template_id': EMAILJS_TEMPLATE_ID,
            'user_id': EMAILJS_PUBLIC_KEY,
            'template_params': {
                'seller_email': to_email,
                'to_name': 'User',
                'name': 'Xtopus Property Management',
                'email': 'geocorpsys@gmail.com',
                'message': body,
                'subject': subject,
                'product_name': 'Xtopus'
            }
        }
        
        if template_params:
            for key, value in template_params.items():
                if key in ['seller_email', 'to_name', 'name', 'email', 'message', 'subject', 'product_name']:
                    params['template_params'][key] = value
                else:
                    params['template_params'][key] = value
        
        response = requests.post(
            EMAILJS_API_URL,
            json=params,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Email sent successfully to {to_email}")
            return True
        else:
            logger.error(f"❌ EmailJS Error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ EmailJS Exception: {e}")
        return False

def create_notification(user_id: str, notification_type: str, message: str, related_data: dict = None):
    """Create a notification for a user"""
    data = db.get_data()
    if "notifications" not in data:
        data["notifications"] = []
    
    notification = {
        "_id": f"notif_{int(datetime.now().timestamp())}_{user_id}_{uuid.uuid4().hex[:6]}",
        "user_id": user_id,
        "type": notification_type,
        "message": message,
        "related_data": related_data or {},
        "read": False,
        "created_at": datetime.now().isoformat()
    }
    data["notifications"].append(notification)
    db.update_data(data)
    return True

def verify_paystack_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify the Paystack webhook signature"""
    if not PAYSTACK_SECRET_KEY:
        logger.warning("Paystack secret key not configured, skipping signature verification")
        return True
    
    try:
        computed_signature = hmac.new(
            PAYSTACK_SECRET_KEY.encode('utf-8'),
            body,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(computed_signature, signature)
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False


# ============================================
# PAYMENT ENDPOINTS
# ============================================

# ============================================
# INITIALIZE PAYMENT (Paystack)
# ============================================
@router.post("/initialize_payment")
async def initialize_payment(request: Request):
    """
    Initialize a Paystack payment
    Payment types:
    - 'plan_upgrade': Administrator upgrading from free to paid (₦15,000/month or ₦162,000/year)
    - 'rent': Tenant paying rent
    """
    try:
        # Check if Paystack is configured
        if not PAYSTACK_SECRET_KEY or not PAYSTACK_PUBLIC_KEY:
            logger.error("Paystack credentials not configured")
            return JSONResponse(
                status_code=503,
                content={"success": False, "detail": "Payment service is not configured. Please contact support."}
            )
        
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        body = await request.json()
        payment_type = body.get("payment_type")  # 'plan_upgrade' or 'rent'
        amount = body.get("amount")
        email = body.get("email")
        user_id = body.get("user_id")
        property_id = body.get("property_id")
        payment_plan = body.get("payment_plan", "monthly")  # 'monthly' or 'annual' for plan upgrade
        callback_url = body.get("callback_url")
        
        # Validate required fields
        if not payment_type or not amount or not email:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Missing required fields: payment_type, amount, email"}
            )
        
        # Validate payment type
        if payment_type not in ["plan_upgrade", "rent"]:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Invalid payment_type. Must be 'plan_upgrade' or 'rent'"}
            )
        
        # Validate amount
        try:
            amount = float(amount)
            if amount <= 0:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": "Amount must be greater than 0"}
                )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Invalid amount format"}
            )
        
        # Generate a unique reference
        reference = f"XTOPUS-{payment_type.upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        
        # Prepare metadata
        metadata = {
            "payment_type": payment_type,
            "user_id": user_id or current_user.get("user_id"),
            "payment_plan": payment_plan,
            "customer_email": email
        }
        
        if property_id:
            metadata["property_id"] = property_id
        
        # Prepare Paystack request
        paystack_data = {
            "email": email,
            "amount": int(amount * 100),  # Convert to kobo
            "reference": reference,
            "metadata": metadata,
            "channels": ["card", "bank_transfer", "ussd", "qr", "mobile_money", "bank"]
        }
        
        if callback_url:
            paystack_data["callback_url"] = callback_url
        
        # Make Paystack API call
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Initializing {payment_type} payment: {reference} - ₦{amount}")
        
        response = requests.post(
            f"{PAYSTACK_API_URL}/transaction/initialize",
            json=paystack_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status"):
                # Save the transaction in the database
                transaction = {
                    "_id": f"txn_{int(datetime.now().timestamp())}",
                    "reference": reference,
                    "user_id": current_user.get("user_id"),
                    "amount": amount,
                    "payment_type": payment_type,
                    "payment_plan": payment_plan,
                    "status": "pending",
                    "metadata": metadata,
                    "authorization_url": result["data"]["authorization_url"],
                    "access_code": result["data"]["access_code"],
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                # Save to database
                db.add_to_collection("transactions", transaction)
                
                logger.info(f"✅ Payment initialized: {reference}")
                
                return JSONResponse({
                    "success": True,
                    "message": "Payment initialized successfully",
                    "data": {
                        "authorization_url": result["data"]["authorization_url"],
                        "reference": reference,
                        "access_code": result["data"]["access_code"],
                        "amount": amount
                    }
                })
            else:
                logger.error(f"Paystack error: {result.get('message')}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False, 
                        "detail": f"Paystack error: {result.get('message')}"
                    }
                )
        else:
            logger.error(f"Paystack API error: {response.status_code} - {response.text}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Payment initialization failed. Please try again."}
            )
            
    except Exception as e:
        logger.error(f"Error initializing payment: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# VERIFY PAYMENT (Webhook)
# ============================================
@router.post("/webhook")
async def paystack_webhook(request: Request):
    """
    Paystack webhook endpoint for payment verification
    """
    try:
        # Get the raw body and signature
        body = await request.body()
        signature = request.headers.get("x-paystack-signature")
        
        # Verify the signature if secret key is configured
        if PAYSTACK_SECRET_KEY:
            if not verify_paystack_webhook_signature(body, signature):
                logger.warning("Invalid webhook signature received")
                return JSONResponse(status_code=401, content={"success": False, "detail": "Invalid signature"})
        
        # Parse the event
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook body")
            return JSONResponse(status_code=400, content={"success": False, "detail": "Invalid JSON"})
        
        # Only process successful charge events
        if event.get("event") == "charge.success":
            data = event.get("data", {})
            reference = data.get("reference")
            
            if not reference:
                logger.warning("Webhook received without reference")
                return JSONResponse(status_code=200, content={"success": True})
            
            # Find the transaction
            transactions = db.get_collection("transactions")
            transaction = None
            for t in transactions:
                if t.get("reference") == reference:
                    transaction = t
                    break
            
            if not transaction:
                logger.warning(f"Transaction not found for webhook: {reference}")
                return JSONResponse(status_code=200, content={"success": True})
            
            # Check if already processed
            if transaction.get("status") == "success":
                logger.info(f"Transaction {reference} already processed")
                return JSONResponse(status_code=200, content={"success": True})
            
            # Update transaction status
            amount = data.get("amount", 0) / 100  # Convert from kobo
            metadata = data.get("metadata", {})
            payment_type = metadata.get("payment_type")
            user_id = metadata.get("user_id")
            payment_plan = metadata.get("payment_plan", "monthly")
            
            transaction["status"] = "success"
            transaction["payment_data"] = data
            transaction["updated_at"] = datetime.now().isoformat()
            db.update_collection_item("transactions", transaction.get("_id"), transaction)
            
            logger.info(f"✅ Webhook: Payment verified for {reference}")
            
            # Process based on payment type
            if payment_type == "plan_upgrade":
                await process_plan_upgrade(user_id, reference, amount, payment_plan)
            elif payment_type == "rent":
                await process_rent_payment(user_id, reference, amount, metadata)
            else:
                logger.warning(f"Unknown payment type: {payment_type}")
            
        return JSONResponse(status_code=200, content={"success": True})
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(status_code=500, content={"success": False, "detail": str(e)})


# ============================================
# VERIFY PAYMENT (Manual)
# ============================================
@router.get("/verify_payment/{reference}")
async def verify_payment(request: Request, reference: str):
    """
    Verify a payment by reference (called after Paystack redirect)
    """
    try:
        # Check if Paystack is configured
        if not PAYSTACK_SECRET_KEY:
            return JSONResponse(
                status_code=503,
                content={"success": False, "detail": "Payment service is not configured"}
            )
        
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Check if transaction exists
        transactions = db.get_collection("transactions")
        transaction = None
        for t in transactions:
            if t.get("reference") == reference:
                transaction = t
                break
        
        if not transaction:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Transaction not found"}
            )
        
        # Verify with Paystack
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(
            f"{PAYSTACK_API_URL}/transaction/verify/{reference}",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status"):
                data = result.get("data", {})
                status = data.get("status")
                
                if status == "success":
                    # Update transaction if not already updated
                    if transaction.get("status") != "success":
                        transaction["status"] = "success"
                        transaction["payment_data"] = data
                        transaction["updated_at"] = datetime.now().isoformat()
                        db.update_collection_item("transactions", transaction.get("_id"), transaction)
                        
                        # Process based on payment type
                        metadata = transaction.get("metadata", {})
                        payment_type = metadata.get("payment_type")
                        user_id = metadata.get("user_id")
                        payment_plan = metadata.get("payment_plan", "monthly")
                        amount = data.get("amount", 0) / 100
                        
                        if payment_type == "plan_upgrade":
                            await process_plan_upgrade(user_id, reference, amount, payment_plan)
                        elif payment_type == "rent":
                            await process_rent_payment(user_id, reference, amount, metadata)
                    
                    return JSONResponse({
                        "success": True,
                        "status": "success",
                        "message": "Payment verified successfully"
                    })
                else:
                    return JSONResponse({
                        "success": False,
                        "status": status,
                        "detail": f"Payment status: {status}"
                    })
            else:
                return JSONResponse({
                    "success": False,
                    "detail": "Payment verification failed"
                })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": "Failed to verify payment with Paystack"}
            )
            
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# PROCESS PLAN UPGRADE
# ============================================
async def process_plan_upgrade(user_id: str, reference: str, amount: float, payment_plan: str = "monthly"):
    """Process a plan upgrade payment"""
    try:
        users = db.get_collection("users")
        target_user = None
        for u in users:
            if u.get("user_id") == user_id:
                target_user = u
                break
        
        if not target_user:
            logger.error(f"User not found for plan upgrade: {user_id}")
            return
        
        # Check if already upgraded
        if target_user.get("payment_status") == "paid":
            logger.info(f"User {user_id} already on paid plan, skipping upgrade")
            return
        
        # Update user's payment status
        target_user["payment_status"] = "paid"
        target_user["plan_type"] = payment_plan  # 'monthly' or 'annual'
        target_user["plan_upgraded_at"] = datetime.now().isoformat()
        target_user["payment_reference"] = reference
        target_user["upgrade_amount"] = amount
        
        # Calculate expiry date (1 month or 1 year from now)
        if payment_plan == "monthly":
            target_user["plan_expiry"] = (datetime.now() + timedelta(days=30)).isoformat()
        else:  # annual
            target_user["plan_expiry"] = (datetime.now() + timedelta(days=365)).isoformat()
        
        db.update_collection_item("users", target_user.get("_id"), target_user)
        
        # Record payment
        payment_record = {
            "_id": f"pay_{int(datetime.now().timestamp())}",
            "user_id": user_id,
            "payment_type": "plan_upgrade",
            "payment_plan": payment_plan,
            "amount": amount,
            "reference": reference,
            "status": "verified",
            "created_at": datetime.now().isoformat()
        }
        db.add_to_collection("payments", payment_record)
        
        # Notify the user
        create_notification(
            user_id,
            "plan_upgraded",
            f"🎉 Your plan has been upgraded to PAID ({payment_plan})! You now have unlimited access until {target_user.get('plan_expiry')}."
        )
        
        # Send email
        email_body = f"""
Hello {target_user.get('first_name', 'User')},

🎉 Congratulations! Your Xtopus plan has been upgraded to PAID ({payment_plan}).

Amount Paid: ₦{amount:,.2f}
Reference: {reference}
Expiry Date: {target_user.get('plan_expiry')}

You now have unlimited access to all features:
- Unlimited buildings
- Unlimited properties
- Unlimited tenant assignments
- Priority support

Thank you for upgrading!

Regards,
Xtopus Team
"""
        template_params = {
            'seller_email': target_user.get("email"),
            'to_name': target_user.get('first_name', 'User'),
            'name': 'Xtopus Property Management',
            'email': 'geocorpsys@gmail.com',
            'message': email_body,
            'subject': "Xtopus - Plan Upgrade Confirmed",
            'product_name': "Xtopus Premium Plan"
        }
        send_emailjs_notification(
            target_user.get("email"),
            "Xtopus - Plan Upgrade Confirmed",
            email_body,
            template_params
        )
        
        logger.info(f"✅ Plan upgraded for {user_id} - {payment_plan} plan")
        
    except Exception as e:
        logger.error(f"Error processing plan upgrade: {e}")


# ============================================
# PROCESS RENT PAYMENT
# ============================================
async def process_rent_payment(user_id: str, reference: str, amount: float, metadata: dict):
    """Process a rent payment"""
    try:
        users = db.get_collection("users")
        target_user = None
        for u in users:
            if u.get("user_id") == user_id:
                target_user = u
                break
        
        if not target_user:
            logger.error(f"User not found for rent payment: {user_id}")
            return
        
        property_id = metadata.get("property_id")
        property_name = "Unknown Property"
        
        # Get property details if provided
        if property_id:
            properties = db.get_collection("properties")
            for p in properties:
                if p.get("_id") == property_id or p.get("id") == property_id:
                    property_name = p.get("name", "Unknown Property")
                    break
        
        # Update user's payment status
        target_user["payment_status"] = "paid"
        target_user["payment_reference"] = reference
        target_user["rent_paid_at"] = datetime.now().isoformat()
        target_user["rent_amount_paid"] = amount
        target_user["rent_paid_through"] = "Paystack"
        
        # Update tenant status to active if it was pending_payment
        if target_user.get("tenant_status") == "pending_payment":
            target_user["tenant_status"] = "active"
            target_user["tenant_activated_by"] = "System (Payment)"
            target_user["tenant_activated_at"] = datetime.now().isoformat()
        
        db.update_collection_item("users", target_user.get("_id"), target_user)
        
        # Record payment
        payment_record = {
            "_id": f"pay_{int(datetime.now().timestamp())}",
            "user_id": user_id,
            "property_id": property_id,
            "property_name": property_name,
            "payment_type": "rent",
            "amount": amount,
            "reference": reference,
            "status": "verified",
            "created_at": datetime.now().isoformat()
        }
        db.add_to_collection("payments", payment_record)
        
        # Update property payment status
        if property_id:
            properties = db.get_collection("properties")
            for p in properties:
                if p.get("_id") == property_id or p.get("id") == property_id:
                    p["payment_verified"] = True
                    p["payment_verified_at"] = datetime.now().isoformat()
                    p["payment_reference"] = reference
                    db.update_collection_item("properties", p.get("_id"), p)
                    break
        
        # Notify the tenant
        create_notification(
            user_id,
            "rent_payment_confirmed",
            f"💰 Your rent payment of ₦{amount:,.2f} has been confirmed. Reference: {reference}"
        )
        
        # Notify the agent/administrator who assigned this tenant
        assigned_by = target_user.get("tenant_assigned_by")
        if assigned_by:
            create_notification(
                assigned_by,
                "rent_payment_received",
                f"💰 Rent payment of ₦{amount:,.2f} received from {user_id} for {property_name}. Reference: {reference}",
                {
                    "user_id": user_id,
                    "property_name": property_name,
                    "amount": amount,
                    "reference": reference
                }
            )
        
        # Send email to tenant
        email_body = f"""
Hello {target_user.get('first_name', 'Tenant')},

💰 Your rent payment has been confirmed!

Property: {property_name}
Amount Paid: ₦{amount:,.2f}
Reference: {reference}
Payment Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Your tenancy status has been updated.

Thank you for your payment!

Regards,
Xtopus Team
"""
        template_params = {
            'seller_email': target_user.get("email"),
            'to_name': target_user.get('first_name', 'Tenant'),
            'name': 'Xtopus Property Management',
            'email': 'geocorpsys@gmail.com',
            'message': email_body,
            'subject': "Xtopus - Rent Payment Confirmed",
            'product_name': property_name
        }
        send_emailjs_notification(
            target_user.get("email"),
            "Xtopus - Rent Payment Confirmed",
            email_body,
            template_params
        )
        
        logger.info(f"✅ Rent payment processed for {user_id} - ₦{amount}")
        
    except Exception as e:
        logger.error(f"Error processing rent payment: {e}")


# ============================================
# GET PAYMENT HISTORY
# ============================================
@router.get("/get_payment_history")
async def get_payment_history(request: Request, user_id: Optional[str] = None):
    """Get payment history for a user"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # If no user_id provided, get current user's history
        if not user_id:
            user_id = current_user.get("user_id")
        else:
            # Check if user has permission to view other's history
            category = current_user.get("user_category", "")
            if category not in ["Super Administrator", "Administrator"]:
                if user_id != current_user.get("user_id"):
                    return JSONResponse(
                        status_code=403,
                        content={"success": False, "detail": "Access denied"}
                    )
        
        payments = db.get_collection("payments")
        user_payments = [p for p in payments if p.get("user_id") == user_id]
        
        # Sort by created_at descending
        user_payments.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return JSONResponse({
            "success": True,
            "payments": user_payments,
            "count": len(user_payments)
        })
        
    except Exception as e:
        logger.error(f"Error getting payment history: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET PAYMENT PLANS
# ============================================
@router.get("/get_payment_plans")
async def get_payment_plans(request: Request):
    """Get available payment plans for upgrade"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        # Only show upgrade plans to users on free plan
        payment_status = current_user.get("payment_status", "free")
        user_category = current_user.get("user_category", "")
        
        # Allow Super Administrators, Administrators, and Sub-Administrators to upgrade
        if user_category not in ["Super Administrator", "Administrator", "Sub-Administrator"]:
            return JSONResponse({
                "success": True,
                "plans": {},
                "current_plan": "free",
                "is_paid": False,
                "message": "Plan upgrades are only available for Administrators."
            })
        
        plans = {
            "free": {
                "name": "Free Plan",
                "price": 0,
                "price_display": "Free",
                "features": [
                    "1 Building",
                    "1 Property",
                    "1 Tenant",
                    "Basic Support"
                ],
                "is_free": True
            },
            "monthly": {
                "name": "Monthly Plan",
                "price": 15000,
                "price_display": "₦15,000/month",
                "features": [
                    "Unlimited Buildings",
                    "Unlimited Properties",
                    "Unlimited Tenants",
                    "Priority Support",
                    "Monthly Billing"
                ],
                "is_free": False
            },
            "annual": {
                "name": "Annual Plan",
                "price": 162000,
                "price_display": "₦162,000/year",
                "features": [
                    "Unlimited Buildings",
                    "Unlimited Properties",
                    "Unlimited Tenants",
                    "Priority Support",
                    "Annual Billing",
                    "2 Months Free"
                ],
                "is_free": False,
                "savings": "Save ₦18,000 (2 months free)"
            }
        }
        
        # Only show plans that the user can purchase
        if payment_status != "free":
            # Paid users see their current plan only
            current_plan = current_user.get("plan_type", "monthly")
            return JSONResponse({
                "success": True,
                "plans": {
                    current_plan: plans.get(current_plan, plans["monthly"])
                },
                "current_plan": current_plan,
                "is_paid": True
            })
        
        return JSONResponse({
            "success": True,
            "plans": {
                "monthly": plans["monthly"],
                "annual": plans["annual"]
            },
            "current_plan": "free",
            "is_paid": False
        })
        
    except Exception as e:
        logger.error(f"Error getting payment plans: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET PAYMENT PUBLIC KEY
# ============================================
@router.get("/get_paystack_public_key")
async def get_paystack_public_key(request: Request):
    """Get the Paystack public key for the frontend"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        if not PAYSTACK_PUBLIC_KEY:
            return JSONResponse(
                status_code=503,
                content={"success": False, "detail": "Payment service is not configured"}
            )
        
        return JSONResponse({
            "success": True,
            "public_key": PAYSTACK_PUBLIC_KEY
        })
        
    except Exception as e:
        logger.error(f"Error getting Paystack public key: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )


# ============================================
# GET TRANSACTION STATUS
# ============================================
@router.get("/get_transaction_status/{reference}")
async def get_transaction_status(request: Request, reference: str):
    """Get the status of a transaction"""
    try:
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "detail": "Not authenticated"}
            )
        
        transactions = db.get_collection("transactions")
        transaction = None
        for t in transactions:
            if t.get("reference") == reference:
                transaction = t
                break
        
        if not transaction:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Transaction not found"}
            )
        
        return JSONResponse({
            "success": True,
            "transaction": {
                "reference": transaction.get("reference"),
                "status": transaction.get("status"),
                "amount": transaction.get("amount"),
                "payment_type": transaction.get("payment_type"),
                "created_at": transaction.get("created_at")
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting transaction status: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": str(e)}
        )