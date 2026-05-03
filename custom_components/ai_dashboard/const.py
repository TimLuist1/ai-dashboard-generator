"""Constants for AI Dashboard Generator."""

DOMAIN = "ai_dashboard"
VERSION = "2.0.0"

PLATFORMS: list = []

# Configuration keys
CONF_AI_PROVIDER = "ai_provider"
CONF_AI_MODEL = "ai_model"
CONF_API_KEY = "api_key"
CONF_DASHBOARD_TITLE = "dashboard_title"
CONF_DASHBOARD_URL_PATH = "dashboard_url_path"
CONF_INCLUDE_DOMAINS = "include_domains"
CONF_EXCLUDE_ENTITIES = "exclude_entities"
CONF_THEME = "theme"
CONF_USE_MUSHROOM = "use_mushroom"
CONF_LANGUAGE = "language"

# AI Provider options
AI_PROVIDER_OFFLINE = "offline"
AI_PROVIDER_OPENAI = "openai"
AI_PROVIDER_ANTHROPIC = "anthropic"
AI_PROVIDER_GOOGLE = "google"

AI_PROVIDERS = {
    AI_PROVIDER_OFFLINE: "Offline / Regelbasiert (Keine API nötig)",
    AI_PROVIDER_OPENAI: "OpenAI (GPT-4o-mini / GPT-4o)",
    AI_PROVIDER_ANTHROPIC: "Anthropic (Claude 3.5 Sonnet)",
    AI_PROVIDER_GOOGLE: "Google (Gemini 2.0 Flash)",
}

AI_MODELS = {
    AI_PROVIDER_OPENAI: [
        ("gpt-4o-mini", "GPT-4o Mini (schnell, günstig)"),
        ("gpt-4o", "GPT-4o (beste Qualität)"),
    ],
    AI_PROVIDER_ANTHROPIC: [
        ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku (schnell)"),
        ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet (beste Qualität)"),
    ],
    AI_PROVIDER_GOOGLE: [
        ("gemini-2.0-flash", "Gemini 2.0 Flash (schnell)"),
        ("gemini-2.0-pro", "Gemini 2.0 Pro (beste Qualität)"),
    ],
}

# Default values
DEFAULT_DASHBOARD_TITLE = "AI Dashboard"
DEFAULT_DASHBOARD_URL_PATH = "ai-dashboard"
DEFAULT_THEME = "default"
DEFAULT_AI_PROVIDER = AI_PROVIDER_OFFLINE

# Dashboard URL path used to create the HA dashboard
DASHBOARD_URL_PATH = "ai-dashboard"

# Panel registration
PANEL_COMPONENT_NAME = "ai-dashboard-panel"
PANEL_SIDEBAR_TITLE = "AI Dashboard"
PANEL_SIDEBAR_ICON = "mdi:robot-happy"
PANEL_URL = "ai-dashboard-config"

# Storage
STORAGE_KEY = f"{DOMAIN}_config"
STORAGE_VERSION = 1
STORAGE_KEY_IMAGES = f"{DOMAIN}_images"

# Status values
STATUS_IDLE = "idle"
STATUS_GENERATING = "generating"
STATUS_APPLYING = "applying"
STATUS_DONE = "done"
STATUS_ERROR = "error"

# Entity domains to include by default
DEFAULT_INCLUDE_DOMAINS = [
    "light",
    "switch",
    "sensor",
    "binary_sensor",
    "climate",
    "media_player",
    "cover",
    "camera",
    "alarm_control_panel",
    "fan",
    "vacuum",
    "lock",
    "person",
    "weather",
    "input_boolean",
    "input_number",
    "input_select",
    "number",
    "select",
]

# Entity domains always excluded
ALWAYS_EXCLUDE_DOMAINS = [
    "automation",
    "script",
    "scene",
    "zone",
    "sun",
    "persistent_notification",
    "update",
    "system_log",
    "recorder",
    "homeassistant",
]

# Patterns in entity IDs that indicate non-user-relevant entities
FILTER_PATTERNS = [
    "_rssi",
    "_lqi",
    "_linkquality",
    "_voltage",
    "_current_consumption",
    "_power_consumption",
    "_debug",
    "_raw",
    "_internal",
    "_diagnostic",
    "_firmware",
    "_update_available",
    "_reachable",
    "_last_seen",
    "_uptime",
    "_restart_count",
    "_boot_count",
    "_wifi_signal",
    "_signal_strength",
]

# Sensor device classes that are non-relevant by default
FILTER_DEVICE_CLASSES = [
    "signal_strength",
    "voltage",
]

# Icons for domains
DOMAIN_ICONS = {
    "light": "mdi:lightbulb",
    "switch": "mdi:toggle-switch",
    "sensor": "mdi:chart-line",
    "binary_sensor": "mdi:eye",
    "climate": "mdi:thermometer",
    "media_player": "mdi:television-play",
    "cover": "mdi:window-shutter",
    "camera": "mdi:cctv",
    "alarm_control_panel": "mdi:shield-home",
    "fan": "mdi:fan",
    "vacuum": "mdi:robot-vacuum",
    "lock": "mdi:lock",
    "person": "mdi:account",
    "weather": "mdi:weather-cloudy",
    "input_boolean": "mdi:toggle-switch",
    "input_number": "mdi:numeric",
    "input_select": "mdi:format-list-bulleted",
    "number": "mdi:numeric",
    "select": "mdi:format-list-bulleted",
}

# Sensor device class icons
SENSOR_DEVICE_CLASS_ICONS = {
    "temperature": "mdi:thermometer",
    "humidity": "mdi:water-percent",
    "pressure": "mdi:gauge",
    "illuminance": "mdi:brightness-5",
    "co2": "mdi:molecule-co2",
    "pm25": "mdi:air-filter",
    "pm10": "mdi:air-filter",
    "battery": "mdi:battery",
    "energy": "mdi:lightning-bolt",
    "power": "mdi:flash",
    "current": "mdi:current-ac",
    "wind_speed": "mdi:weather-windy",
    "precipitation": "mdi:weather-rainy",
    "motion": "mdi:motion-sensor",
    "door": "mdi:door",
    "window": "mdi:window-open",
    "smoke": "mdi:smoke-detector",
    "gas": "mdi:gas-cylinder",
    "moisture": "mdi:water",
    "vibration": "mdi:vibrate",
    "sound": "mdi:volume-high",
    "distance": "mdi:ruler",
    "speed": "mdi:speedometer",
    "aqi": "mdi:air-filter",
    "voc": "mdi:air-filter",
}

# Area icons (for common room names)
AREA_ICONS = {
    "wohnzimmer": "mdi:sofa",
    "living": "mdi:sofa",
    "living room": "mdi:sofa",
    "salon": "mdi:sofa",
    "schlafzimmer": "mdi:bed",
    "bedroom": "mdi:bed",
    "chambre": "mdi:bed",
    "master bedroom": "mdi:bed-king",
    "küche": "mdi:chef-hat",
    "kitchen": "mdi:chef-hat",
    "cuisine": "mdi:chef-hat",
    "badezimmer": "mdi:shower",
    "bathroom": "mdi:shower",
    "bad": "mdi:shower",
    "salle de bain": "mdi:shower",
    "gäste wc": "mdi:toilet",
    "guest bathroom": "mdi:toilet",
    "wc": "mdi:toilet",
    "toilet": "mdi:toilet",
    "büro": "mdi:desk",
    "office": "mdi:desk",
    "arbeitszimmer": "mdi:desk",
    "flur": "mdi:door-open",
    "corridor": "mdi:door-open",
    "hallway": "mdi:door-open",
    "eingang": "mdi:door-open",
    "entrance": "mdi:door-open",
    "keller": "mdi:stairs-down",
    "basement": "mdi:stairs-down",
    "dachboden": "mdi:stairs-up",
    "attic": "mdi:stairs-up",
    "garten": "mdi:flower",
    "garden": "mdi:flower",
    "terrasse": "mdi:table-chair",
    "terrace": "mdi:table-chair",
    "balkon": "mdi:balcony",
    "balcony": "mdi:balcony",
    "garage": "mdi:garage",
    "kinderzimmer": "mdi:baby-carriage",
    "kids room": "mdi:baby-carriage",
    "children": "mdi:baby-carriage",
    "esszimmer": "mdi:silverware-fork-knife",
    "dining room": "mdi:silverware-fork-knife",
    "dining": "mdi:silverware-fork-knife",
    "hauswirtschaft": "mdi:washing-machine",
    "laundry": "mdi:washing-machine",
    "utility": "mdi:washing-machine",
    "technik": "mdi:server",
    "server": "mdi:server",
    "gym": "mdi:dumbbell",
    "sport": "mdi:dumbbell",
    "heizung": "mdi:radiator",
    "heating": "mdi:radiator",
    "außen": "mdi:home-outline",
    "outdoor": "mdi:home-outline",
    "outside": "mdi:home-outline",
    "draußen": "mdi:home-outline",
}

DEFAULT_AREA_ICON = "mdi:home-floor-1"

# WebSocket commands
WS_COMMAND_GET_AREAS = f"{DOMAIN}/get_areas"
WS_COMMAND_GET_STATUS = f"{DOMAIN}/get_status"
WS_COMMAND_GENERATE = f"{DOMAIN}/generate"
WS_COMMAND_APPLY = f"{DOMAIN}/apply"
WS_COMMAND_GET_PREVIEW = f"{DOMAIN}/get_preview"
WS_COMMAND_UPLOAD_IMAGE = f"{DOMAIN}/upload_image"
WS_COMMAND_DELETE_IMAGE = f"{DOMAIN}/delete_image"
WS_COMMAND_GET_IMAGES = f"{DOMAIN}/get_images"
WS_COMMAND_UPDATE_SETTINGS = f"{DOMAIN}/update_settings"
WS_COMMAND_GET_SETTINGS = f"{DOMAIN}/get_settings"

# AI Assistant WebSocket commands
WS_COMMAND_ASSISTANT_CHAT = f"{DOMAIN}/assistant_chat"
WS_COMMAND_ASSISTANT_EXECUTE = f"{DOMAIN}/assistant_execute"
WS_COMMAND_ASSISTANT_CLEAR = f"{DOMAIN}/assistant_clear"
WS_COMMAND_ASSISTANT_HISTORY = f"{DOMAIN}/assistant_history"

# Service names
SERVICE_GENERATE_DASHBOARD = "generate_dashboard"
SERVICE_REFRESH_DASHBOARD = "refresh_dashboard"

# HTTP endpoints
HTTP_IMAGE_UPLOAD = f"/api/{DOMAIN}/upload_image"
HTTP_IMAGE_SERVE = f"/api/{DOMAIN}/images"

# AI model options (updated 2026)
AI_MODELS_UPDATED = {
    "openai": [
        ("gpt-4o-mini", "GPT-4o Mini (schnell, günstig)"),
        ("gpt-4o", "GPT-4o (beste Qualität)"),
        ("gpt-4.1-mini", "GPT-4.1 Mini (2026)"),
        ("gpt-4.1", "GPT-4.1 (2026, beste Qualität)"),
    ],
    "anthropic": [
        ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku (schnell)"),
        ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet"),
        ("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet (2025)"),
    ],
    "google": [
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite (schnellste, günstigste)"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash ✅ (empfohlen)"),
        ("gemini-2.5-pro", "Gemini 2.5 Pro (beste Qualität)"),
        ("gemini-3-flash-preview", "Gemini 3 Flash Preview (neueste Generation)"),
    ],
}
