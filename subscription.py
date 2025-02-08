import os
import stripe
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, render_template, url_for, current_app, flash, redirect
from flask_login import login_required, current_user
from models import db, User, Subscription

subscription = Blueprint('subscription', __name__)

# Initialize Stripe with the secret key
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Stripe Price IDs for different plans
STRIPE_PRICES = {
    'premium_monthly': 'price_H5ggYwtDq4fbrJ',  # Replace with your actual price ID
    'premium_yearly': 'price_H5ggYwtDq4fbrK'    # Replace with your actual price ID
}

@subscription.route('/pricing')
def pricing():
    """Display pricing plans"""
    return render_template('subscription/pricing.html')

@subscription.route('/subscribe/<plan_type>')
@login_required
def subscribe(plan_type):
    """Create a Stripe Checkout Session for subscription"""
    try:
        price_id = STRIPE_PRICES.get(plan_type)
        if not price_id:
            flash('Invalid subscription plan.')
            return redirect(url_for('subscription.pricing'))

        # Create or get Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={'user_id': current_user.id}
            )
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1
            }],
            mode='subscription',
            success_url=url_for('subscription.success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('subscription.pricing', _external=True)
        )
        
        return jsonify({'checkoutUrl': checkout_session.url})

    except Exception as e:
        current_app.logger.error(f"Error creating checkout session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@subscription.route('/webhook', methods=['POST'])
def webhook():
    """Handle Stripe webhook events"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ.get('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session(session)
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        handle_subscription_updated(subscription)
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        handle_subscription_deleted(subscription)

    return jsonify({'status': 'success'})

def handle_checkout_session(session):
    """Handle successful checkout session"""
    customer_id = session.get('customer')
    subscription_id = session.get('subscription')
    
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if not user:
        current_app.logger.error(f"User not found for customer {customer_id}")
        return
    
    # Get subscription details from Stripe
    stripe_subscription = stripe.Subscription.retrieve(subscription_id)
    
    # Create subscription record
    subscription = Subscription(
        user_id=user.id,
        stripe_subscription_id=subscription_id,
        stripe_price_id=stripe_subscription.plan.id,
        status='active',
        plan_type='premium',
        amount=stripe_subscription.plan.amount,
        currency=stripe_subscription.plan.currency,
        interval=stripe_subscription.plan.interval,
        start_date=datetime.fromtimestamp(stripe_subscription.current_period_start),
        end_date=datetime.fromtimestamp(stripe_subscription.current_period_end)
    )
    
    # Update user subscription status
    user.subscription_status = 'active'
    user.subscription_end_date = subscription.end_date
    
    db.session.add(subscription)
    db.session.commit()

def handle_subscription_updated(stripe_subscription):
    """Handle subscription update events"""
    subscription = Subscription.query.filter_by(
        stripe_subscription_id=stripe_subscription.id
    ).first()
    
    if subscription:
        subscription.status = stripe_subscription.status
        subscription.end_date = datetime.fromtimestamp(stripe_subscription.current_period_end)
        
        if subscription.user:
            subscription.user.subscription_status = stripe_subscription.status
            subscription.user.subscription_end_date = subscription.end_date
        
        db.session.commit()

def handle_subscription_deleted(stripe_subscription):
    """Handle subscription deletion events"""
    subscription = Subscription.query.filter_by(
        stripe_subscription_id=stripe_subscription.id
    ).first()
    
    if subscription:
        subscription.status = 'cancelled'
        subscription.cancelled_at = datetime.utcnow()
        
        if subscription.user:
            subscription.user.subscription_status = 'cancelled'
        
        db.session.commit()

@subscription.route('/success')
@login_required
def success():
    """Handle successful subscription"""
    session_id = request.args.get('session_id')
    if not session_id:
        flash('Invalid session ID')
        return redirect(url_for('subscription.pricing'))
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return render_template('subscription/success.html')
    except Exception as e:
        flash('Error confirming subscription')
        return redirect(url_for('subscription.pricing'))

@subscription.route('/cancel')
@login_required
def cancel():
    """Cancel subscription"""
    if not current_user.is_premium:
        flash('No active subscription found.')
        return redirect(url_for('subscription.pricing'))
    
    active_subscription = Subscription.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).first()
    
    if not active_subscription:
        flash('No active subscription found.')
        return redirect(url_for('subscription.pricing'))
    
    try:
        # Cancel at period end
        stripe.Subscription.modify(
            active_subscription.stripe_subscription_id,
            cancel_at_period_end=True
        )
        
        flash('Your subscription will be cancelled at the end of the billing period.')
        return redirect(url_for('subscription.pricing'))
    except Exception as e:
        current_app.logger.error(f"Error cancelling subscription: {str(e)}")
        flash('Error cancelling subscription. Please try again.')
        return redirect(url_for('subscription.pricing'))
