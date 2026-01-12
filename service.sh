#!/bin/bash
#
# Service control script for SMS Gateway API
# Control of systemd service
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SERVICE_NAME="sms-api"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"
LOG_DIR="$PROJECT_DIR/logs"

# Functions
show_help() {
    echo -e "${BLUE}SMS Gateway API Service Control${NC}"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start      - Start service"
    echo "  stop       - Stop service"
    echo "  restart    - Restart service"
    echo "  status     - Show service status"
    echo "  logs       - Show logs (live)"
    echo "  logfile    - Show log files"
    echo "  enable     - Enable service at boot"
    echo "  disable    - Disable service at boot"
    echo "  reload     - Reload service configuration"
    echo "  help       - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 start"
    echo "  $0 logs"
    echo "  $0 status"
    echo ""
}

check_service_exists() {
    if [ ! -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
        echo -e "${RED}Error: Service is not installed!${NC}"
        echo "Install the service with: sudo ./install_service.sh"
        exit 1
    fi
}

check_sudo() {
    if [ "$EUID" -ne 0 ] && [ "$1" != "status" ] && [ "$1" != "logs" ] && [ "$1" != "logfile" ] && [ "$1" != "help" ]; then
        echo -e "${YELLOW}Note: This command requires sudo privileges.${NC}"
        echo "Trying with sudo..."
        if sudo -n true 2>/dev/null; then
            # sudo is already authenticated
            exec sudo "$0" "$@"
        else
            exec sudo "$0" "$@"
        fi
    fi
}

# Main logic
case "${1:-help}" in
    start)
        check_sudo "$1"
        check_service_exists
        echo -e "${GREEN}Starting service...${NC}"
        systemctl start "${SERVICE_NAME}.service"
        sleep 1
        if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
            echo -e "${GREEN}✓ Service successfully started${NC}"
        else
            echo -e "${RED}✗ Service could not be started${NC}"
            echo "Check logs with: $0 logs"
            exit 1
        fi
        ;;
    
    stop)
        check_sudo "$1"
        check_service_exists
        echo -e "${YELLOW}Stopping service...${NC}"
        systemctl stop "${SERVICE_NAME}.service"
        sleep 1
        if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
            echo -e "${GREEN}✓ Service successfully stopped${NC}"
        else
            echo -e "${RED}✗ Service could not be stopped${NC}"
            exit 1
        fi
        ;;
    
    restart)
        check_sudo "$1"
        check_service_exists
        echo -e "${YELLOW}Restarting service...${NC}"
        systemctl restart "${SERVICE_NAME}.service"
        sleep 1
        if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
            echo -e "${GREEN}✓ Service successfully restarted${NC}"
        else
            echo -e "${RED}✗ Service could not be started${NC}"
            echo "Check logs with: $0 logs"
            exit 1
        fi
        ;;
    
    status)
        check_service_exists
        echo -e "${BLUE}Service status:${NC}"
        echo ""
        systemctl status "${SERVICE_NAME}.service" --no-pager -l
        ;;
    
    logs)
        check_service_exists
        echo -e "${BLUE}Showing service logs (live, Ctrl+C to exit)...${NC}"
        echo ""
        journalctl -u "${SERVICE_NAME}.service" -f
        ;;
    
    logfile)
        echo -e "${BLUE}Log files:${NC}"
        echo ""
        if [ -d "$LOG_DIR" ]; then
            if [ -f "$LOG_DIR/sms-api.log" ]; then
                echo -e "${GREEN}Standard output log:${NC}"
                echo "  $LOG_DIR/sms-api.log"
                echo "  Size: $(du -h "$LOG_DIR/sms-api.log" | cut -f1)"
                echo ""
            fi
            if [ -f "$LOG_DIR/sms-api-error.log" ]; then
                echo -e "${RED}Error log:${NC}"
                echo "  $LOG_DIR/sms-api-error.log"
                echo "  Size: $(du -h "$LOG_DIR/sms-api-error.log" | cut -f1)"
                echo ""
            fi
            echo "View logs:"
            echo "  tail -f $LOG_DIR/sms-api.log"
            echo "  tail -f $LOG_DIR/sms-api-error.log"
        else
            echo -e "${YELLOW}Log directory not found: $LOG_DIR${NC}"
        fi
        ;;
    
    enable)
        check_sudo "$1"
        check_service_exists
        echo -e "${GREEN}Enabling service (starts at boot)...${NC}"
        systemctl enable "${SERVICE_NAME}.service"
        echo -e "${GREEN}✓ Service enabled${NC}"
        ;;
    
    disable)
        check_sudo "$1"
        check_service_exists
        echo -e "${YELLOW}Disabling service (no longer starts at boot)...${NC}"
        systemctl disable "${SERVICE_NAME}.service"
        echo -e "${GREEN}✓ Service disabled${NC}"
        ;;
    
    reload)
        check_sudo "$1"
        check_service_exists
        echo -e "${GREEN}Reloading service configuration...${NC}"
        systemctl daemon-reload
        systemctl restart "${SERVICE_NAME}.service"
        echo -e "${GREEN}✓ Service configuration reloaded${NC}"
        ;;
    
    help|--help|-h)
        show_help
        ;;
    
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
