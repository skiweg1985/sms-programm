#!/bin/bash
#
# Uninstallation script for SMS Gateway API systemd service
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SERVICE_NAME="sms-api"

echo -e "${YELLOW}=== SMS Gateway API Service Uninstallation ===${NC}"
echo ""

# Check if running as root/sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run with sudo!${NC}"
    echo "Usage: sudo ./uninstall_service.sh"
    exit 1
fi

# Stop and disable service
if systemctl is-active --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
    echo -e "${YELLOW}Stopping service...${NC}"
    systemctl stop "${SERVICE_NAME}.service"
fi

if systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
    echo -e "${YELLOW}Disabling service...${NC}"
    systemctl disable "${SERVICE_NAME}.service"
fi

# Stop and remove cleanup timer
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}-cleanup.timer"
SERVICE_CLEANUP_FILE="/etc/systemd/system/${SERVICE_NAME}-cleanup.service"

if systemctl is-active --quiet "${SERVICE_NAME}-cleanup.timer" 2>/dev/null; then
    echo -e "${YELLOW}Stopping cleanup timer...${NC}"
    systemctl stop "${SERVICE_NAME}-cleanup.timer"
fi

if systemctl is-enabled --quiet "${SERVICE_NAME}-cleanup.timer" 2>/dev/null; then
    echo -e "${YELLOW}Disabling cleanup timer...${NC}"
    systemctl disable "${SERVICE_NAME}-cleanup.timer"
fi

# Remove service file
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
if [ -f "$SERVICE_FILE" ]; then
    echo -e "${YELLOW}Removing service file...${NC}"
    rm -f "$SERVICE_FILE"
    echo -e "${GREEN}✓ Service file removed${NC}"
fi

# Remove cleanup timer and service
if [ -f "$TIMER_FILE" ] || [ -f "$SERVICE_CLEANUP_FILE" ]; then
    echo -e "${YELLOW}Removing cleanup timer and service...${NC}"
    rm -f "$TIMER_FILE" "$SERVICE_CLEANUP_FILE"
    systemctl daemon-reload
    echo -e "${GREEN}✓ Cleanup timer removed${NC}"
fi

echo ""
echo -e "${GREEN}=== Uninstallation completed! ===${NC}"
echo ""
echo "Note: venv, logs and config.yaml were not removed."
echo "These can be deleted manually if desired."
echo ""
