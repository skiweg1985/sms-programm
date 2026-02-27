#!/bin/bash
#
# Installation script for SMS Gateway API as systemd service
# Creates venv, installs dependencies and configures systemd service
#

set -e  # Exit on errors

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project directory (where script is located)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"
SERVICE_NAME="sms-api"
SERVICE_USER="${SUDO_USER:-$USER}"

echo -e "${GREEN}=== SMS Gateway API Service Installation ===${NC}"
echo ""

# Check if running as root/sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run with sudo!${NC}"
    echo "Usage: sudo ./install_service.sh"
    exit 1
fi

# Check if Python3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python3 is not installed!${NC}"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
echo -e "${YELLOW}Python version: ${PYTHON_VERSION}${NC}"

# Check if venv module is available
echo -e "${GREEN}[0/7] Checking venv support...${NC}"

# Test if venv actually works (not just if --help works)
TEST_VENV_DIR="/tmp/test_venv_$$"
if python3 -m venv "$TEST_VENV_DIR" &> /dev/null 2>&1; then
    rm -rf "$TEST_VENV_DIR"
    echo -e "${GREEN}✓ venv module available and functional${NC}"
else
    echo -e "${YELLOW}⚠ venv module not available or not functional, attempting to install...${NC}"
    
    # Check which package manager is available
    if command -v apt-get &> /dev/null; then
        # Debian/Ubuntu
        PYTHON_MAJOR_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f1,2)
        VENV_PACKAGE="python${PYTHON_MAJOR_MINOR}-venv"
        
        echo -e "${YELLOW}Installing ${VENV_PACKAGE} (required for venv on Ubuntu/Debian)...${NC}"
        echo -e "${YELLOW}Running apt-get update...${NC}"
        if apt-get update > /dev/null 2>&1; then
            echo -e "${YELLOW}Installing ${VENV_PACKAGE}...${NC}"
            if apt-get install -y "$VENV_PACKAGE" > /dev/null 2>&1; then
                echo -e "${GREEN}✓ ${VENV_PACKAGE} successfully installed${NC}"
            else
                # Fallback: Try python3-venv
                echo -e "${YELLOW}Trying python3-venv as fallback...${NC}"
                if apt-get install -y python3-venv > /dev/null 2>&1; then
                    echo -e "${GREEN}✓ python3-venv successfully installed${NC}"
                else
                    echo -e "${RED}✗ Error: Could not install venv package${NC}"
                    echo ""
                    echo "Please install manually:"
                    echo "  sudo apt-get update"
                    echo "  sudo apt-get install ${VENV_PACKAGE}"
                    echo "  or:"
                    echo "  sudo apt-get install python3-venv"
                    exit 1
                fi
            fi
        else
            echo -e "${RED}✗ Error: apt-get update failed${NC}"
            echo "Please run manually:"
            echo "  sudo apt-get update"
            echo "  sudo apt-get install ${VENV_PACKAGE}"
            exit 1
        fi
    elif command -v yum &> /dev/null; then
        # RHEL/CentOS
        echo -e "${YELLOW}Installing python3-venv (yum)...${NC}"
        if yum install -y python3-venv > /dev/null 2>&1; then
            echo -e "${GREEN}✓ python3-venv successfully installed${NC}"
        else
            echo -e "${RED}✗ Error: Could not install venv package${NC}"
            echo "Please install manually:"
            echo "  sudo yum install python3-venv"
            exit 1
        fi
    elif command -v dnf &> /dev/null; then
        # Fedora
        echo -e "${YELLOW}Installing python3-venv (dnf)...${NC}"
        if dnf install -y python3-venv > /dev/null 2>&1; then
            echo -e "${GREEN}✓ python3-venv successfully installed${NC}"
        else
            echo -e "${RED}✗ Error: Could not install venv package${NC}"
            echo "Please install manually:"
            echo "  sudo dnf install python3-venv"
            exit 1
        fi
    else
        echo -e "${RED}✗ Error: No supported package manager found${NC}"
        echo "Please install python3-venv manually for your system"
        exit 1
    fi
    
    # Check again if venv works now
    echo -e "${YELLOW}Testing venv after installation...${NC}"
    if python3 -m venv "$TEST_VENV_DIR" &> /dev/null 2>&1; then
        rm -rf "$TEST_VENV_DIR"
        echo -e "${GREEN}✓ venv module now works correctly${NC}"
    else
        rm -rf "$TEST_VENV_DIR" 2>/dev/null
        echo -e "${RED}✗ Error: venv module still not working after installation${NC}"
        echo ""
        echo "Please check:"
        echo "  1. Is the package installed? dpkg -l | grep python.*venv"
        echo "  2. Try restarting the script"
        echo "  3. Or install manually: sudo apt-get install python3.10-venv"
        exit 1
    fi
fi

echo -e "${YELLOW}Project directory: ${PROJECT_DIR}${NC}"
echo -e "${YELLOW}Service name: ${SERVICE_NAME}${NC}"
echo -e "${YELLOW}Service user: ${SERVICE_USER}${NC}"
echo ""

# Change to project directory
cd "$PROJECT_DIR"

# 1. Create venv if not present
echo -e "${GREEN}[1/8] Creating Python Virtual Environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ venv created${NC}"
else
    echo -e "${YELLOW}✓ venv already exists${NC}"
fi

# 2. Activate venv and install dependencies
echo -e "${GREEN}[2/8] Installing dependencies...${NC}"
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠ requirements.txt not found, installing standard dependencies...${NC}"
    pip install fastapi uvicorn[standard] requests pyyaml
    echo -e "${GREEN}✓ Standard dependencies installed${NC}"
fi
deactivate

# 3. Create logs directory
echo -e "${GREEN}[3/8] Creating logs directory...${NC}"
mkdir -p logs
chown "$SERVICE_USER:$SERVICE_USER" logs
chmod 755 logs
echo -e "${GREEN}✓ logs directory created${NC}"

# 4. Load port from config.yaml (if present)
echo -e "${GREEN}[4/8] Loading configuration...${NC}"
PORT=8000  # Default port
if [ -f "$PROJECT_DIR/config.yaml" ]; then
    # Try to extract port from config.yaml (under server.port)
    # Search for "port:" in server section
    CONFIG_PORT=$(grep -A 5 "^server:" "$PROJECT_DIR/config.yaml" 2>/dev/null | grep -E "^\s+port:\s*[0-9]+" | head -1 | sed 's/.*port:\s*\([0-9]*\).*/\1/' || echo "")
    if [ -n "$CONFIG_PORT" ] && [ "$CONFIG_PORT" -gt 0 ] && [ "$CONFIG_PORT" -lt 65536 ] 2>/dev/null; then
        PORT=$CONFIG_PORT
        echo -e "${GREEN}✓ Port read from config.yaml: ${PORT}${NC}"
    else
        echo -e "${YELLOW}⚠ No valid port found in config.yaml, using default: ${PORT}${NC}"
    fi
else
    echo -e "${YELLOW}⚠ config.yaml not found, using default port: ${PORT}${NC}"
fi

# 5. Make log cleanup script executable
echo -e "${GREEN}[5/8] Creating log cleanup script...${NC}"
CLEANUP_SCRIPT="$PROJECT_DIR/cleanup_logs.sh"
if [ -f "$CLEANUP_SCRIPT" ]; then
    chmod +x "$CLEANUP_SCRIPT"
    echo -e "${GREEN}✓ Log cleanup script made executable${NC}"
else
    echo -e "${YELLOW}⚠ cleanup_logs.sh not found${NC}"
fi

# 6. Create systemd service file
echo -e "${GREEN}[6/8] Creating systemd service file...${NC}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=SMS Gateway API - Teltonika TRB245 Router
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PROJECT_DIR/venv/bin/uvicorn sms_api:app --host 0.0.0.0 --port $PORT --log-config $PROJECT_DIR/uvicorn_logging.yaml
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/logs/sms-api.log
StandardError=append:$PROJECT_DIR/logs/sms-api.log

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}✓ Service file created: ${SERVICE_FILE}${NC}"

# 7. Create systemd timer for log cleanup
echo -e "${GREEN}[7/8] Creating systemd timer for log cleanup...${NC}"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}-cleanup.timer"
SERVICE_CLEANUP_FILE="/etc/systemd/system/${SERVICE_NAME}-cleanup.service"

# Cleanup service
cat > "$SERVICE_CLEANUP_FILE" << EOF
[Unit]
Description=SMS Gateway API - Log Cleanup
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/cleanup_logs.sh
StandardOutput=append:$PROJECT_DIR/logs/cleanup.log
StandardError=append:$PROJECT_DIR/logs/cleanup-error.log
EOF

# Cleanup timer (runs daily at 2:00 AM)
cat > "$TIMER_FILE" << EOF
[Unit]
Description=SMS Gateway API - Log Cleanup Timer
Requires=${SERVICE_NAME}-cleanup.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

echo -e "${GREEN}✓ Log cleanup timer created${NC}"

# 8. Reload systemd
echo -e "${GREEN}[8/8] Reloading systemd configuration...${NC}"
systemctl daemon-reload
echo -e "${GREEN}✓ systemd reloaded${NC}"

# 9. Enable and start service
echo -e "${GREEN}[9/9] Enabling and starting services...${NC}"
systemctl enable "${SERVICE_NAME}.service"
systemctl start "${SERVICE_NAME}.service"

# Enable and start cleanup timer
systemctl enable "${SERVICE_NAME}-cleanup.timer" > /dev/null 2>&1
systemctl start "${SERVICE_NAME}-cleanup.timer" > /dev/null 2>&1
echo -e "${GREEN}✓ Log cleanup timer enabled (runs daily at 2:00 AM)${NC}"

# Wait and check status
sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    echo -e "${GREEN}✓ Service successfully started${NC}"
else
    echo -e "${RED}⚠ Service could not be started${NC}"
    echo "Check status with: sudo systemctl status ${SERVICE_NAME}"
    echo "Check logs with: sudo journalctl -u ${SERVICE_NAME} -f"
    exit 1
fi

echo ""
echo -e "${GREEN}=== Installation completed! ===${NC}"
echo ""
echo "Check service status:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo ""
echo "View service logs:"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  or: tail -f ${PROJECT_DIR}/logs/sms-api.log"
echo ""
echo "Control service:"
echo "  sudo systemctl start ${SERVICE_NAME}    # Start"
echo "  sudo systemctl stop ${SERVICE_NAME}     # Stop"
echo "  sudo systemctl restart ${SERVICE_NAME} # Restart"
echo "  sudo systemctl disable ${SERVICE_NAME}  # Disable"
echo ""
echo "Log cleanup timer:"
echo "  sudo systemctl status ${SERVICE_NAME}-cleanup.timer  # Check status"
echo "  sudo systemctl list-timers ${SERVICE_NAME}-cleanup.timer  # Next execution"
echo ""
echo "API is accessible at:"
echo "  http://localhost:${PORT}"
echo "  http://localhost:${PORT}/docs (API documentation)"
echo ""
