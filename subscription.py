import os
import stripe
from datetime import datetime
from functools import wraps
from flask import Blueprint, jsonify, request, render_template, url_for, current_app, flash, redirect
from flask_login import login_required, current_user
from models import db, User, Subscription
from extensions import csrf

subscription = Blueprint('subscription', __name__)

# Initialize Stripe with the secret key
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Stripe Price IDs for different plans
STRIPE_PRICES = {
    'premium_monthly': os.environ.get('STRIPE_PREMIUM_MONTHLY_PRICE_ID', 'price_H5ggYwtDq4fbrJ'),
    'premium_yearly': os.environ.get('STRIPE_PREMIUM_YEARLY_PRICE_ID', 'price_H5ggYwtDq4fbrK')
}


def _stripe_prop(obj, key, default=None):
    """Read Stripe objects or dict payloads from webhooks."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _subscription_price_snapshot(stripe_subscription):
    """Resolve price id, amount (cents), currency, interval for legacy ``plan`` or ``items[].price`` APIs."""
    plan = _stripe_prop(stripe_subscription, "plan")
    if plan:
        pid = _stripe_prop(plan, "id")
        if pid:
            amount = _stripe_prop(plan, "amount")
            currency = (_stripe_prop(plan, "currency") or "usd").upper()
            interval = _stripe_prop(plan, "interval") or "month"
            return pid, amount, currency, interval

    items = _stripe_prop(stripe_subscription, "items")
    items_list = _stripe_prop(items, "data") if items is not None else None
    if not items_list:
        raise ValueError("Stripe subscription has no price or items")

    price = _stripe_prop(items_list[0], "price")
    if not price:
        raise ValueError("Stripe subscription item has no price")

    recurring = _stripe_prop(price, "recurring") or {}
    interval = _stripe_prop(recurring, "interval") if recurring else None
    pid = _stripe_prop(price, "id")
    amount = _stripe_prop(price, "unit_amount")
    currency = (_stripe_prop(price, "currency") or "usd").upper()

    return pid, amount, currency, interval or "month"


def is_premium():
    """Check if the current user has an active premium subscription"""
    if not current_user.is_authenticated:
        return False
    return bool(current_user.is_premium)

def premium_required(f):
    """Decorator to restrict access to premium features"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_premium():
            flash('This feature requires a premium subscription', 'warning')
            return redirect(url_for('subscription.pricing'))
        return f(*args, **kwargs)
    return decorated_function

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
@csrf.exempt
def webhook():
    """Handle Stripe webhook events"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ.get('STRIPE_WEBHOOK_SECRET', '')
        )
    except ValueError:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError:
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
    customer_id = _stripe_prop(session, "customer")
    subscription_id = _stripe_prop(session, "subscription")

    if not subscription_id:
        current_app.logger.warning("Checkout session completed without subscription id")
        return

    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if not user:
        current_app.logger.error(f"User not found for customer {customer_id}")
        return

    stripe_subscription = stripe.Subscription.retrieve(subscription_id)

    try:
        price_id, amount, currency, interval = _subscription_price_snapshot(stripe_subscription)
    except ValueError as exc:
        current_app.logger.exception("Could not read Stripe subscription pricing: %s", exc)
        return

    period_start = _stripe_prop(stripe_subscription, "current_period_start")
    period_end = _stripe_prop(stripe_subscription, "current_period_end")

    subscription = Subscription(
        user_id=user.id,
        stripe_subscription_id=subscription_id,
        stripe_price_id=price_id,
        status='active',
        plan_type='premium',
        amount=amount,
        currency=currency or 'USD',
        interval=interval or 'month',
        start_date=datetime.fromtimestamp(int(period_start)) if period_start else datetime.utcnow(),
        end_date=datetime.fromtimestamp(int(period_end)) if period_end else None,
    )

    user.subscription_status = 'active'
    user.subscription_end_date = subscription.end_date

    db.session.add(subscription)
    db.session.commit()

def handle_subscription_updated(stripe_subscription):
    """Handle subscription update events"""
    sub_id = _stripe_prop(stripe_subscription, "id")
    status = _stripe_prop(stripe_subscription, "status")
    period_end = _stripe_prop(stripe_subscription, "current_period_end")

    subscription = Subscription.query.filter_by(
        stripe_subscription_id=sub_id
    ).first()

    if subscription:
        subscription.status = status
        if period_end is not None:
            subscription.end_date = datetime.fromtimestamp(int(period_end))

        if subscription.user:
            subscription.user.subscription_status = status
            subscription.user.subscription_end_date = subscription.end_date

        db.session.commit()

def handle_subscription_deleted(stripe_subscription):
    """Handle subscription deletion events"""
    sub_id = _stripe_prop(stripe_subscription, "id")

    subscription = Subscription.query.filter_by(
        stripe_subscription_id=sub_id
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
    if not is_premium():
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