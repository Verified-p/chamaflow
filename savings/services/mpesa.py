
import base64
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from savings.models import Contribution
from savings.services.contributions import mark_contribution_as_paid


logger = logging.getLogger(__name__)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

def get_mpesa_config():
    """Load M-Pesa credentials and configuration from Django settings."""

    config = {
        "consumer_key": getattr(settings, "MPESA_CONSUMER_KEY", ""),
        "consumer_secret": getattr(settings, "MPESA_CONSUMER_SECRET", ""),
        "shortcode": getattr(settings, "MPESA_SHORTCODE", ""),
        "passkey": getattr(settings, "MPESA_PASSKEY", ""),
        "callback_url": getattr(settings, "MPESA_CALLBACK_URL", ""),
        "environment": getattr(settings, "MPESA_ENVIRONMENT", "sandbox"),
    }

    if config["environment"] == "production":
        config["base_url"] = "https://api.safaricom.co.ke"
    else:
        config["base_url"] = "https://sandbox.safaricom.co.ke"

    return config


def validate_mpesa_config():
    """Ensure all required Daraja credentials are configured."""

    config = get_mpesa_config()

    required = [
        "consumer_key",
        "consumer_secret",
        "shortcode",
        "passkey",
        "callback_url",
    ]

    missing = [
        key for key in required
        if not config[key]
    ]

    if missing:
        raise ValidationError(
            "Missing M-Pesa configuration: "
            + ", ".join(missing)
        )

    if config["environment"] not in ("sandbox", "production"):
        raise ValidationError(
            "MPESA_ENVIRONMENT must be sandbox or production."
        )

    if not config["callback_url"].startswith("https://"):
        raise ValidationError(
            "The M-Pesa callback URL must use HTTPS."
        )

    return config


# --------------------------------------------------
# PHONE NUMBER NORMALIZATION
# --------------------------------------------------

def normalize_phone_number(phone_number):
    """Convert Kenyan phone numbers to the 254XXXXXXXXX format."""

    phone = re.sub(r"\D", "", str(phone_number))

    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]

    elif phone.startswith("254") and len(phone) == 12:
        pass

    else:
        raise ValidationError(
            "Enter a valid Kenyan phone number."
        )

    if not re.fullmatch(r"254[17]\d{8}", phone):
        raise ValidationError(
            "The phone number must be a valid Kenyan mobile number."
        )

    return phone


# --------------------------------------------------
# ACCESS TOKEN
# --------------------------------------------------

def get_access_token():
    """Generate or retrieve a cached Daraja OAuth access token."""

    config = validate_mpesa_config()

    cache_key = (
        f"mpesa_access_token_{config['environment']}"
    )

    access_token = cache.get(cache_key)

    if access_token:
        return access_token

    url = (
        f"{config['base_url']}"
        "/oauth/v1/generate"
        "?grant_type=client_credentials"
    )

    try:
        response = requests.get(
            url,
            auth=(
                config["consumer_key"],
                config["consumer_secret"],
            ),
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()
        access_token = data.get("access_token")

        if not access_token:
            raise ValidationError(
                "M-Pesa did not return an access token."
            )

        expires_in = int(data.get("expires_in", 3600))

        # Refresh before the actual expiry time.
        cache.set(
            cache_key,
            access_token,
            timeout=max(expires_in - 60, 60),
        )

        return access_token

    except requests.RequestException:
        logger.exception("M-Pesa access token request failed.")
        raise ValidationError(
            "Unable to authenticate with M-Pesa. Try again later."
        )


# --------------------------------------------------
# STK PUSH PASSWORD
# --------------------------------------------------

def generate_stk_password(shortcode, passkey, timestamp):
    """Generate the Base64 password required by STK Push."""

    raw_password = (
        f"{shortcode}{passkey}{timestamp}"
    )

    return base64.b64encode(
        raw_password.encode("utf-8")
    ).decode("utf-8")


# --------------------------------------------------
# INITIATE STK PUSH
# --------------------------------------------------

@transaction.atomic
def initiate_stk_push(contribution):
    """
    Send an STK Push request for a pending contribution.

    A successful API response only means the request was accepted.
    It does not confirm that the member has paid.
    """

    contribution = Contribution.objects.select_for_update().get(
        pk=contribution.pk
    )

    if contribution.status not in ("pending", "failed"):
        raise ValidationError(
            "This contribution cannot receive an STK Push."
        )

    config = validate_mpesa_config()

    phone_number = normalize_phone_number(
        contribution.phone_number
    )

    try:
        amount = Decimal(str(contribution.amount))

        if amount <= 0 or amount != amount.to_integral_value():
            raise ValidationError(
                "M-Pesa STK Push requires a positive whole-shilling amount."
            )

    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            "The contribution amount is invalid."
        )

    access_token = get_access_token()

    timestamp = timezone.localtime().strftime(
        "%Y%m%d%H%M%S"
    )

    password = generate_stk_password(
        config["shortcode"],
        config["passkey"],
        timestamp,
    )

    url = (
        f"{config['base_url']}"
        "/mpesa/stkpush/v1/processrequest"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "BusinessShortCode": config["shortcode"],
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": config["shortcode"],
        "PhoneNumber": phone_number,
        "CallBackURL": config["callback_url"],
        "AccountReference": f"CF{contribution.pk}",
        "TransactionDesc": "ChamaFlow Contribution",
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()

    except requests.RequestException:
        logger.exception(
            "STK Push request failed for contribution %s.",
            contribution.pk,
        )
        raise ValidationError(
            "Unable to send the M-Pesa payment request."
        )

    if str(data.get("ResponseCode")) != "0":
        logger.warning(
            "STK Push rejected: %s",
            data,
        )
        raise ValidationError(
            data.get(
                "ResponseDescription",
                "M-Pesa rejected the payment request.",
            )
        )

    checkout_request_id = data.get("CheckoutRequestID")
    merchant_request_id = data.get("MerchantRequestID")

    if not checkout_request_id:
        raise ValidationError(
            "M-Pesa did not return a checkout request ID."
        )

    contribution.phone_number = phone_number
    contribution.status = "processing"
    contribution.checkout_request_id = checkout_request_id
    contribution.merchant_request_id = merchant_request_id

    contribution.save(
        update_fields=[
            "phone_number",
            "status",
            "checkout_request_id",
            "merchant_request_id",
            "updated_at",
        ]
    )

    return data


# --------------------------------------------------
# CALLBACK METADATA
# --------------------------------------------------

def get_callback_metadata(callback):
    """Extract payment metadata from an STK Push callback."""

    metadata = callback.get("CallbackMetadata", {}).get(
        "Item", []
    )

    return {
        item.get("Name"): item.get("Value")
        for item in metadata
        if item.get("Name")
    }


# --------------------------------------------------
# PROCESS STK PUSH CALLBACK
# --------------------------------------------------

@transaction.atomic
def process_stk_callback(callback_data):
    """
    Process a Safaricom STK Push callback.

    Match the callback to an existing contribution using its
    CheckoutRequestID. Successful callbacks are checked against
    the expected amount and phone number before confirmation.
    """

    stk_callback = (
        callback_data
        .get("Body", {})
        .get("stkCallback", {})
    )

    checkout_request_id = stk_callback.get(
        "CheckoutRequestID"
    )

    if not checkout_request_id:
        raise ValidationError(
            "The callback does not contain a checkout request ID."
        )

    contribution = Contribution.objects.select_for_update().filter(
        checkout_request_id=checkout_request_id
    ).first()

    if not contribution:
        raise ValidationError(
            "No contribution matches this M-Pesa transaction."
        )

    result_code = str(stk_callback.get("ResultCode", ""))

    result_description = stk_callback.get(
        "ResultDesc",
        "M-Pesa transaction completed.",
    )

    # Handle unsuccessful or cancelled transactions.
    if result_code != "0":

        if contribution.status == "paid":
            return contribution

        if contribution.status == "processing":
            contribution.status = "failed"
            contribution.result_code = result_code
            contribution.result_description = result_description

            contribution.save(
                update_fields=[
                    "status",
                    "result_code",
                    "result_description",
                    "updated_at",
                ]
            )

        return contribution

    metadata = get_callback_metadata(stk_callback)

    receipt_number = metadata.get("MpesaReceiptNumber")
    callback_amount = metadata.get("Amount")
    callback_phone = metadata.get("PhoneNumber")

    if not receipt_number or callback_amount is None or callback_phone is None:
        raise ValidationError(
            "The successful callback is missing required payment details."
        )

    expected_amount = Decimal(str(contribution.amount))
    received_amount = Decimal(str(callback_amount))

    expected_phone = normalize_phone_number(
        contribution.phone_number
    )

    received_phone = normalize_phone_number(
        callback_phone
    )

    if received_amount != expected_amount:
        raise ValidationError(
            "The callback amount does not match the contribution amount."
        )

    if received_phone != expected_phone:
        raise ValidationError(
            "The callback phone number does not match the contribution phone number."
        )

    if contribution.status == "paid":
        if contribution.mpesa_receipt_number == receipt_number:
            return contribution

        raise ValidationError(
            "This contribution has already been paid with another receipt."
        )

    return mark_contribution_as_paid(
        contribution_id=contribution.pk,
        mpesa_receipt_number=receipt_number,
        result_code=result_code,
        result_description=result_description,
    )


# --------------------------------------------------
# CALLBACK RESPONSE
# --------------------------------------------------

def get_callback_response():
    """Return the standard acknowledgement expected by Daraja."""

    return {
        "ResultCode": 0,
        "ResultDesc": "Accepted",
    }
