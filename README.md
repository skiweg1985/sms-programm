# SMS Gateway API

A FastAPI-based web server for sending SMS messages via a Teltonika TRB245 router.

## Features

- REST API for sending SMS via HTTP GET requests
- Automatic authentication with token caching
- Automatic modem detection (uses primary modem)
- Automatic phone number normalization (+49 → 0049, 0151 → 0049151)
- Automatic SMS splitting for messages > 160 characters
- URL parameter decoding (UTF-8)
- Health-check endpoint

## Requirements

- Python 3.7 or higher
- Teltonika TRB245 router with REST API enabled
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

### Send SMS

**Endpoint:** `GET /`

**Parameters:**
- `username` - API username (required)
- `password` - API password (required)
- `number` - Recipient phone number (required)
- `text` - SMS text (required, URL-encoded)

**Phone Number Normalization:**
- All numbers are automatically normalized before sending
- `+49...` → `0049...` (and other countries: `+XX` → `00XX`)
- `0151...` → `0049151...` (German numbers without country code)
- Numbers starting with `0` (but not `00`) are prefixed with `0049`

**Example:**
```bash
curl "http://localhost:8000/?username=user&password=pass&number=%2B491234567890&text=Hello%20World"
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
```

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

- **Authentication failed:** Check router credentials in `config.yaml`
- **SMS sending failed:** Verify phone number format and modem status
- **Modem not found:** Check available modems with `python send_sms.py --list-modems`
