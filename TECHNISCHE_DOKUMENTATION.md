# Technische Dokumentation - SMS Gateway API

## Zweck und Umfang
Die SMS Gateway API stellt einen HTTP-basierten Dienst bereit, um SMS ueber einen Teltonika Router (z. B. TRB245) zu versenden. Der Service kapselt Router-Authentifizierung, Token-Handling, Modem-Ermittlung, Telefonnummern-Normalisierung und SMS-Splitting und stellt eine REST-Schnittstelle per FastAPI zur Verfuegung.

## Architekturueberblick
- **API-Server**: `sms_api.py` (FastAPI). Endpunkte fuer GET/POST, Authentifizierung, Health-Check.
- **Router-Client**: `send_sms.py` (TRB245SMS). Kapselt Router-Login, Token-Cache, Modem-Status, SMS-Versand.
- **Service-Betrieb**: `install_service.sh`, `service.sh`, `uninstall_service.sh` (systemd Service + Log-Rotation).
- **Konfiguration**: `config.yaml` / `config.yaml.example`.
- **Logbereinigung**: `cleanup_logs.sh` + systemd Timer.

## Laufzeitumgebung
- **Python**: >= 3.7
- **Abhaengigkeiten**: `requests`, `fastapi`, `uvicorn[standard]`, `pyyaml` (siehe `requirements.txt`).
- **Netzwerk**: Zugriff auf Router REST API (HTTPS, self-signed Zertifikate werden akzeptiert).

## Konfiguration
Die Datei `config.yaml` enthaelt Router- und API-Zugangsdaten sowie Server-Parameter.

Beispielstruktur (Platzhalterwerte):

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

Wichtige Hinweise:
- `config.yaml` enthaelt Zugangsdaten und sollte nicht versioniert werden (bereits in `.gitignore`).
- Der Service liest `server.port` fuer das systemd ExecStart-Argument (Installationsskript).
- `server.log_retention_days` steuert die Logbereinigung.

## API-Schnittstellen
Basis: `sms_api.py`

### Authentifizierung
Alle Endpunkte ausser `/health` erfordern HTTP-Parameter fuer API-Credentials.
- **GET**: `username`, `password` als Query-Parameter
- **POST**: `username`, `password` im JSON-Body

Die Validierung erfolgt gegen `config.yaml` -> `api.username` / `api.password`.

### Endpunkte

#### GET /
Sendet eine SMS per Query-Parametern.

Beispiel:
```bash
curl "http://localhost:8000/?username=apiuser&password=apipassword&number=%2B491234567890&text=Hello%20World"
```

Query-Parameter:
- `username` (required)
- `password` (required)
- `number` (required) Telefonnummer
- `text` (required) Nachrichtentext

#### POST /
Sendet eine SMS per JSON-Body.

Beispiel:
```bash
curl -X POST "http://localhost:8000/" \
  -H "Content-Type: application/json" \
  -d '{"username":"apiuser","password":"apipassword","number":"+491234567890","text":"Hello World"}'
```

JSON-Body:
```json
{
  "username": "apiuser",
  "password": "apipassword",
  "number": "+491234567890",
  "text": "Hello World"
}
```

#### GET /send
Legacy-Endpunkt, ruft intern GET `/` auf, Authentifizierung weiterhin erforderlich.

#### GET /health
Health-Check ohne Authentifizierung.

Beispiel:
```bash
curl http://localhost:8000/health
```

Antwort:
```json
{
  "status": "ok",
  "service": "SMS Gateway API"
}
```

### Response-Format
Erfolgreiche Antwort (Beispiel):
```json
{
  "success": true,
  "message": "SMS sent successfully",
  "sms_used": 1,
  "phone_number": "+491234567890",
  "message_length": 11
}
```

Bei Mehrteiligkeit:
```json
{
  "success": true,
  "message": "SMS sent successfully (2 parts)",
  "sms_used": 2,
  "phone_number": "00491234567890",
  "message_length": 200,
  "parts": 2
}
```

Fehlerantworten:
- `401` bei falschen API-Credentials oder Router-Auth-Fehlern.
- `400` bei fehlenden Parametern.
- `422` bei Router-Rueckgabe mit Fehlern.
- `500` bei internen Fehlern.

## Datenverarbeitung im Request-Flow
1. **Request-Logging**: Loggt Method, Pfad, Client-IP (Passwort maskiert).
2. **URL-Decode**: Query-Parameter werden ggf. erneut URL-decodiert.
3. **Normalisierung**: Telefonnummern `+XX` werden zu `00XX`, Formatierung wird entfernt.
4. **Validierung**: Pflichtfelder auf Nicht-Leer pruefen.
5. **Router-Auth**: Token-basierter Login gegen `/api/login`.
6. **Modemwahl**: Primary-Modem wird bevorzugt, sonst erstes Modem, fallback `1-1.4`.
7. **SMS-Versand**: `/api/messages/actions/send`.
8. **Antwort**: Normalisierte Struktur an Client.

## Telefonnummern-Normalisierung
Implementiert in `send_sms.py`:
- Entfernt Leerzeichen und Trennzeichen (`-`, `(`, `)`, `.`, `/`).
- `+49...` -> `0049...` (generisch `+XX...` -> `00XX...`).

## SMS-Splitting
- Standardlimit: 160 Zeichen.
- Aufteilung erfolgt an Wortgrenzen, optional mit Nummerierung (`1/3: `).
- Mehrteilige Nachrichten werden seriell versendet; Abbruch bei Fehler.

## Router-Authentifizierung und Token-Cache
- Login via `POST /api/login`.
- Token wird im Home-Verzeichnis des Service-Users gecached: `~/.trb245_token_<router>.json`.
- Token wird vor Ablauf (10s Puffer) erneuert.
- TLS-Verifikation wird deaktiviert (self-signed).

## Service-Betrieb (systemd)
Installationsskript `install_service.sh`:
- Erstellt `venv`, installiert Dependencies.
- Legt Log-Verzeichnis `logs/` an.
- Erzeugt systemd Service `sms-api.service` und Log-Cleanup Timer.
- Startet Service und Timer.

Service-Startkommando:
```
ExecStart=<PROJECT_DIR>/venv/bin/uvicorn sms_api:app --host 0.0.0.0 --port <port>
```

Service-Steuerung via `service.sh`:
```bash
./service.sh start|stop|restart|status|logs|logfile|enable|disable|reload
```

## Logging
- Standard-Output: `logs/sms-api.log`
- Fehler-Output: `logs/sms-api-error.log`
- Cleanup-Logs: `logs/cleanup.log`, `logs/cleanup-error.log`

Log-Retention:
- `cleanup_logs.sh` loescht `.log` Dateien aelter als `server.log_retention_days` (Default: 30).
- Timer laeuft taeglich um 02:00 Uhr.

## CLI Tool
`send_sms.py` kann direkt aufgerufen werden:

```bash
python send_sms.py +491234567890 "Hello World!"
python send_sms.py --list-modems
```

Konfigurationsprioritaet:
1. CLI-Argumente
2. Environment-Variablen (`TRB245_ROUTER`, `TRB245_USER`, `TRB245_PASSWORD`)
3. `config.yaml`

## Sicherheit und Betriebshinweise
- `config.yaml` enthaelt Klartext-Passwoerter. Zugriff auf Dateirechte beschraenken.
- TLS-Verifikation ist deaktiviert (self-signed). In produktiven Umgebungen sollte ein gueltiges Zertifikat verwendet werden.
- API-Auth ist Basic-Parameterbasiert (kein Token/Session). Fuer externe Netze Reverse-Proxy mit TLS und IP-Restriktion empfohlen.

## Fehlerbehebung (Kurzcheck)
- **401 API Auth**: `api.username`/`api.password` in `config.yaml` pruefen.
- **401 Router Auth**: `router.*` in `config.yaml` pruefen.
- **SMS sending failed**: Router-Status, Modem-Status, Nummernformat.
- **Modem not found**: `python send_sms.py --list-modems` ausfuehren.
- **Service startet nicht**: `sudo systemctl status sms-api` und `logs/sms-api-error.log` pruefen.

## Dateien und Zustaendigkeiten
- `sms_api.py`: HTTP API, Auth, Request-Flow, Logging.
- `send_sms.py`: Router-Client, Token-Handling, SMS-Splitting.
- `install_service.sh`: systemd Installation, Logs, Timer.
- `service.sh`: Service-Steuerung.
- `cleanup_logs.sh`: Log-Retention.
- `config.yaml.example`: Konfigurationsvorlage.
