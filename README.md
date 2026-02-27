# SMS Gateway API

A FastAPI-based web server for sending SMS messages via Teltonika routers.

## Features

- REST API for sending SMS via HTTP GET and POST requests
- API authentication with username/password (configurable in config.yaml)
- Automatic authentication with token caching for router
- Automatic modem detection (uses primary modem)
- Automatic phone number normalization (+49 → 0049, +XX → 00XX)
- Automatic SMS splitting for messages > 160 characters
- URL parameter decoding (UTF-8)
- Health-check endpoint (no authentication required)

## Requirements

- Python 3.7 or higher
- Teltonika router with REST API enabled
- Network access to the router

## Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create configuration:**
   ```bash
   cp config.yaml.example config.yaml
   ```

3. **Adjust configuration file:**
   Open `config.yaml` and set router credentials:
   ```yaml
   router:
     url: "https://your-router.local"
     username: "admin"
     password: "YourPassword"
   
   server:
     port: 8000
     log_retention_days: 30
   ```

## Usage

### Starting the Web Server

```bash
python sms_api.py
```

The web server is accessible at `http://localhost:8000` (or the port configured in `config.yaml`).

### API Documentation

Interactive API documentation:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

## API Endpoints

### Authentication

All API endpoints (except `/health`) require authentication using credentials configured in `config.yaml`:

```yaml
api:
  username: "apiuser"
  password: "apipassword"
```

Credentials must be provided with each request either as:
- **GET requests:** URL parameters `username` and `password`
- **POST requests:** JSON body fields `username` and `password`

### Send SMS

**Endpoint:** `GET /` or `POST /`

**GET Parameters:**
- `username` - API username (required, must match config.yaml)
- `password` - API password (required, must match config.yaml)
- `number` - Recipient phone number (required)
- `text` - SMS text (required, URL-encoded)

**POST Body (JSON):**
```json
{
  "username": "apiuser",
  "password": "apipassword",
  "number": "+491234567890",
  "text": "Hello World"
}
```

**Phone Number Normalization:**
- All numbers are automatically normalized before sending
- `+49...` → `0049...` (and other countries: `+XX` → `00XX`)
- Numbers starting with `+` are converted to `00` prefix

**GET Example:**
```bash
curl "http://localhost:8000/?username=apiuser&password=apipassword&number=%2B491234567890&text=Hello%20World"
```

**POST Example:**
```bash
curl -X POST "http://localhost:8000/" \
  -H "Content-Type: application/json" \
  -d '{"username":"apiuser","password":"apipassword","number":"+491234567890","text":"Hello World"}'
```

**Response:**
```json
{
  "success": true,
  "message": "SMS sent successfully",
  "sms_used": 1,
  "phone_number": "+491234567890",
  "message_length": 11
}
```

**Automatic SMS Splitting:**
- Messages over 160 characters are automatically split into multiple SMS
- Splitting occurs at word boundaries (never in the middle of words)
- Each part includes numbering (e.g. "1/3: ", "2/3: ", "3/3: ")
- Multi-part messages show `"parts": N` in the response

### Health Check

**Endpoint:** `GET /health`

**Note:** This endpoint does not require authentication.

```bash
curl http://localhost:8000/health
```

## Configuration

Router credentials and server settings are stored in `config.yaml`:

```yaml
router:
  url: "https://router.local"
  username: "admin"
  password: "YourPassword"

api:
  username: "apiuser"
  password: "apipassword"

server:
  port: 8000
  log_retention_days: 30
```

**Security Note:** The `config.yaml` file contains sensitive data and is already listed in `.gitignore`.

## Systemd Service Installation

**Automatic installation:**
```bash
chmod +x install_service.sh
sudo ./install_service.sh
```

**Service control:**
```bash
./service.sh start      # Start service
./service.sh stop       # Stop service
./service.sh restart    # Restart service
./service.sh status     # Show status
./service.sh logs       # Show logs
./service.sh logfile    # Show log files and paths
```

**Logging:**
- Application log (stdout + stderr): `logs/sms-api.log`
- Cleanup logs: `logs/cleanup.log`, `logs/cleanup-error.log`
- Legacy file `logs/sms-api-error.log` may still exist from older installations but is no longer actively used
- Uvicorn startup/access logs use the same timestamp format via `uvicorn_logging.yaml`

**Uninstall:**
```bash
sudo ./uninstall_service.sh
```

## CLI Tool

Command-line tool for sending SMS:

```bash
# Send SMS
python send_sms.py +491234567890 "Hello World!"

# List available modems
python send_sms.py --list-modems
```

## Troubleshooting

- **API authentication failed:** Check API credentials in `config.yaml` (api section) and ensure they match the username/password in your request
- **Router authentication failed:** Check router credentials in `config.yaml` (router section)
- **SMS sending failed:** Verify phone number format and modem status
- **Modem not found:** Check available modems with `python send_sms.py --list-modems`
