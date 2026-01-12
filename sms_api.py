#!/usr/bin/env python3
"""
FastAPI SMS Gateway for Teltonika TRB245 Router
Accepts GET requests with URL parameters for sending SMS
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
import urllib.parse
import re
import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from send_sms import TRB245SMS, load_config, normalize_phone_number
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SMS Gateway API",
    description="API for sending SMS via Teltonika TRB245 Router",
    version="1.0.0"
)


# Request-Logging-Middleware
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log incoming request
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"[REQUEST] {request.method} {request.url.path} from {client_ip}")
        if request.query_params:
            # Log query parameters (without password)
            safe_params = dict(request.query_params)
            if 'password' in safe_params:
                safe_params['password'] = '***'
            logger.debug(f"[REQUEST] Query parameters: {safe_params}")
        
        # Process request
        response = await call_next(request)
        
        # Log response
        process_time = time.time() - start_time
        logger.info(f"[RESPONSE] Status {response.status_code} - {process_time:.3f}s")
        
        return response


# Register middleware
app.add_middleware(RequestLoggingMiddleware)


def decode_url_parameter(param: str) -> str:
    """
    Decodes URL parameter (UTF-8) if still encoded.
    FastAPI already decodes query parameters automatically, so we check
    if encoded characters are still present before decoding.
    
    Args:
        param: Parameter (possibly already decoded by FastAPI)
    
    Returns:
        Decoded string (UTF-8)
    """
    if not param:
        return ""
    
    # Check if URL-encoded characters are still present (%XX)
    # FastAPI usually decodes already, but we check for safety
    if '%' in param and re.search(r'%[0-9A-Fa-f]{2}', param):
        try:
            logger.debug(f"Decoding URL parameter (contains encoded characters): {param[:100]}...")
            decoded = urllib.parse.unquote(param, encoding='utf-8')
            logger.debug(f"After decoding: {decoded[:100]}...")
            return decoded
        except Exception as e:
            logger.warning(f"Error in URL decoding: {e}, using original")
            # If decoding fails, return original
            return param
    
    # Already decoded or no encoded characters, return original
    return param


@app.get("/")
async def send_sms(
    username: str = Query(..., description="API username"),
    password: str = Query(..., description="API password"),
    number: str = Query(..., description="Phone number (may contain %SMSNUMBER)"),
    text: str = Query(..., description="SMS text (may contain %SMSTEXT)")
):
    """
    Sends an SMS via the TRB245 router
    
    Parameters are automatically URL-decoded by FastAPI (UTF-8).
    
    Example:
        GET /?username=prtg&password=passw&number=%2B491234567890&text=Hello%20World
        GET /?username=prtg&password=passw&number=%SMSNUMBER&text=%SMSTEXT
    """
    logger.info("=" * 80)
    logger.info("New SMS request received")
    logger.info(f"Username: {username}")
    logger.info(f"Number (raw): {number[:50]}... (length: {len(number)})")
    logger.info(f"Text (raw): {text[:100]}... (length: {len(text)})")
    
    try:
        # Decode URL parameters
        logger.info("Decoding URL parameters...")
        phone_number = decode_url_parameter(number)
        message = decode_url_parameter(text)
        logger.info(f"Number (decoded): {phone_number} (length: {len(phone_number)})")
        logger.info(f"Text (decoded): {message[:100]}... (length: {len(message)})")
        
        # Normalize phone number (converts +49 to 0049, 0151 to 0049151, etc.)
        phone_number_original = phone_number
        phone_number = normalize_phone_number(phone_number)
        if phone_number != phone_number_original:
            logger.info(f"Phone number normalized: {phone_number_original} → {phone_number}")
        
        # Validation
        logger.info("Validating parameters...")
        if not phone_number:
            logger.error("[FASTAPI-SERVER] Validation error: Phone number is empty")
            raise HTTPException(
                status_code=400,
                detail="Phone number (number) is required and must not be empty"
            )
        
        if not message:
            logger.error("[FASTAPI-SERVER] Validation error: Message is empty")
            raise HTTPException(
                status_code=400,
                detail="Message (text) is required and must not be empty"
            )
        
        logger.info("✓ Parameter validation successful")
        
        # Load router configuration
        logger.info("Loading router configuration...")
        config = load_config()
        router_config = config.get("router", {})
        
        # Use router credentials from config or API parameters
        router_url = router_config.get("url")
        router_user = router_config.get("username")
        router_password = router_config.get("password")
        
        # If no router credentials in config, use API credentials
        # (not recommended, but for compatibility)
        if not router_url or not router_user or not router_password:
            logger.error("[FASTAPI-SERVER] Configuration error: Router credentials missing")
            raise HTTPException(
                status_code=500,
                detail="Router configuration missing. Please configure config.yaml."
            )
        
        logger.info(f"Router URL: {router_url}")
        logger.info(f"Router User: {router_user}")
        
        # Initialize SMS class
        logger.info("Initializing SMS class...")
        sms = TRB245SMS(router_url, router_user, router_password)
        
        # Authenticate
        logger.info("Authenticating with router...")
        if not sms.authenticate():
            logger.error("[ROUTER] Authentication failed")
            raise HTTPException(
                status_code=401,
                detail="Authentication with router failed"
            )
        logger.info("✓ Authentication with router successful")
        
        # Find primary modem automatically
        logger.info("Determining available modems...")
        modems = sms.get_modems()
        modem_id = "1-1.4"  # Fallback
        if modems and modems.get("success") and "data" in modems:
            logger.info(f"Available modems: {len(modems['data'])}")
            for modem_info in modems["data"]:
                if modem_info.get("primary"):
                    modem_id = modem_info.get("id", "1-1.4")
                    logger.info(f"✓ Primary modem found: {modem_id}")
                    break
            if modem_id == "1-1.4" and modems["data"]:
                modem_id = modems["data"][0].get("id", "1-1.4")
                logger.info(f"Using first available modem: {modem_id}")
        else:
            logger.warning(f"Could not retrieve modem list, using fallback: {modem_id}")
        
        # Send SMS (automatic splitting for > 160 characters)
        logger.info("=" * 80)
        logger.info(f"[ROUTER] Sending SMS to {phone_number} via modem {modem_id}")
        logger.info(f"Message (first 200 characters): {message[:200]}")
        logger.info(f"Message length: {len(message)} characters")
        
        # Check if message needs to be split
        if len(message) > 160:
            logger.info(f"ℹ Message is longer than 160 characters and will be automatically split")
        
        result = sms.send_sms(phone_number, message, modem_id)
        
        # Log complete router response
        logger.info("=" * 80)
        logger.info("[ROUTER] Response from router:")
        logger.info(f"  Success: {result.get('success')}")
        logger.info(f"  Complete response: {result}")
        
        if result.get("success"):
            sms_used = result.get("data", {}).get("sms_used", 0)
            parts = result.get("data", {}).get("parts", 1)
            
            if parts > 1:
                logger.info(f"✓ SMS sent successfully! ({parts} parts, total {sms_used} SMS)")
            else:
                logger.info(f"✓ SMS sent successfully! (SMS used: {sms_used})")
            logger.info("=" * 80)
            
            response_content = {
                "success": True,
                "message": "SMS sent successfully",
                "sms_used": sms_used,
                "phone_number": phone_number,
                "message_length": len(message)
            }
            
            # Add information about multi-part SMS
            if parts > 1:
                response_content["parts"] = parts
                response_content["message"] = f"SMS sent successfully ({parts} parts)"
            
            return JSONResponse(
                status_code=200,
                content=response_content
            )
        else:
            errors = result.get("errors", [])
            error_msg = "; ".join([e.get("error", "Unknown error") for e in errors])
            logger.error("=" * 80)
            logger.error("[ROUTER] SMS sending failed!")
            logger.error(f"  Error details: {error_msg}")
            logger.error(f"  Complete error objects: {errors}")
            logger.error("=" * 80)
            raise HTTPException(
                status_code=422,
                detail=f"SMS sending failed (error from router): {error_msg}"
            )
    
    except HTTPException as e:
        logger.error("=" * 80)
        logger.error(f"[FASTAPI-SERVER] HTTPException: Status {e.status_code}")
        logger.error(f"  Detail: {e.detail}")
        logger.error("=" * 80)
        raise
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[FASTAPI-SERVER] Unexpected error: {type(e).__name__}")
        logger.error(f"  Error: {str(e)}")
        import traceback
        logger.error(f"  Traceback:\n{traceback.format_exc()}")
        logger.error("=" * 80)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health-check endpoint"""
    logger.debug("Health-check called")
    return {"status": "ok", "service": "SMS Gateway API"}


if __name__ == "__main__":
    import uvicorn
    # Load configuration for port
    config = load_config()
    server_config = config.get("server", {})
    port = server_config.get("port", 8000)
    
    logger.info(f"Starting SMS Gateway API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
