/**
 * AI Dashboard Generator - Frontend Panel
 * Modern LitElement-based configuration panel for Home Assistant
 * 
 * Features:
 * - Area/room overview with entity counts
 * - Room image upload
 * - AI settings configuration
 * - Dashboard generation with live progress
 * - Preview generated YAML config
 * - One-click apply
 */

// HA loads custom panel JS as a classic <script> tag (no type="module"),
// so static `import` is forbidden. Dynamic import() works in classic scripts.
// We try to grab Lit from HA's own bundle first (no network needed),
// then fall back to unpkg if unavailable.
(async () => {

let LitElement, html, css, nothing;

try {
  // HA 2023+ bundles Lit and exposes it via this path
  ({ LitElement, html, css, nothing } = await import("/frontend_latest/lit.js"));
} catch (_) {
  try {
    ({ LitElement, html, css, nothing } = await import("https://unpkg.com/lit@3.2.0/index.js?module"));
  } catch (__) {
    // Last resort: derive LitElement from ha-card which HA always defines
    await customElements.whenDefined("ha-card").catch(() => {});
    const HaCard = customElements.get("ha-card");
    if (HaCard) {
      LitElement = Object.getPrototypeOf(Object.getPrototypeOf(HaCard));
      html = LitElement.prototype._$litType$ !== undefined
        ? LitElement.html
        : (strings, ...values) => ({ strings, values, _$litType$: 1 });
    }
  }
}

if (!LitElement) {
  console.error("[AI Dashboard] Could not load Lit – panel cannot be rendered.");
  return;
}

const DOMAIN = "ai_dashboard";

const COLORS = {
  primary: "var(--primary-color, #03a9f4)",
  success: "var(--success-color, #4caf50)",
  warning: "var(--warning-color, #ff9800)",
  error: "var(--error-color, #f44336)",
  background: "var(--card-background-color, #fff)",
  surface: "var(--secondary-background-color, #f5f5f5)",
  text: "var(--primary-text-color, #212121)",
  textSecondary: "var(--secondary-text-color, #727272)",
  divider: "var(--divider-color, #e0e0e0)",
};

// ─────────────────────────────────────────────────────────────
// Main Panel
// ─────────────────────────────────────────────────────────────

class AIDashboardPanel extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      narrow: { type: Boolean },
      route: { type: Object },
      panel: { type: Object },
      // State
      _areas: { type: Array },
      _images: { type: Object },
      _status: { type: String },
      _lastGenerated: { type: String },
      _settings: { type: Object },
      _loading: { type: Boolean },
      _generating: { type: Boolean },
      _applying: { type: Boolean },
      _error: { type: String },
      _success: { type: String },
      _activeTab: { type: String },
      _previewConfig: { type: Object },
      _showPreview: { type: Boolean },
      _uploadingArea: { type: String },
      // Assistant
      _chatMessages: { type: Array },
      _chatInput: { type: String },
      _chatLoading: { type: Boolean },
      _pendingActions: { type: Array },
      _executedActions: { type: Array },
      _autoExecute: { type: Boolean },
    };
  }

  constructor() {
    super();
    this._areas = [];
    this._images = {};
    this._status = "idle";
    this._lastGenerated = null;
    this._settings = {};
    this._loading = true;
    this._generating = false;
    this._applying = false;
    this._error = null;
    this._success = null;
    this._activeTab = "dashboard";
    this._previewConfig = null;
    this._showPreview = false;
    this._uploadingArea = null;
    this._statusInterval = null;
    this._autoApplyAfterGenerate = false;
    // Assistant
    this._chatMessages = [];
    this._chatInput = "";
    this._chatLoading = false;
    this._pendingActions = [];
    this._executedActions = [];
    this._autoExecute = false;
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadData();
    this._loadChatHistory();
    // Poll status during generation
    this._statusInterval = setInterval(() => {
      if (this._generating) this._loadStatus();
    }, 2000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._statusInterval) clearInterval(this._statusInterval);
  }

  async _loadData() {
    this._loading = true;
    try {
      await Promise.all([
        this._loadAreas(),
        this._loadStatus(),
        this._loadSettings(),
        this._loadImages(),
      ]);
    } catch (e) {
      this._error = `Ladefehler: ${e.message || e}`;
    }
    this._loading = false;
  }

  async _loadAreas() {
    try {
      const result = await this.hass.callWS({ type: `${DOMAIN}/get_areas` });
      this._areas = result.areas || [];
    } catch (e) {
      console.error("Failed to load areas:", e);
      this._areas = [];
    }
  }

  async _loadStatus() {
    try {
      const result = await this.hass.callWS({ type: `${DOMAIN}/get_status` });
      const wasGenerating = this._generating;
      this._status = result.status;
      this._lastGenerated = result.last_generated;
      this._generating = result.status === "generating";

      if (wasGenerating && !this._generating) {
        if (result.status === "done") {
          const roomCount = this._areas.filter((a) => a.area_id !== "_unassigned").length;
          if (this._autoApplyAfterGenerate) {
            this._autoApplyAfterGenerate = false;
            this._applying = true;
            try {
              await this.hass.callWS({ type: `${DOMAIN}/apply` });
              this._success = `✅ ${roomCount + 1} Dashboards erstellt & angewendet! Öffne "AI Dashboard" in der Seitenleiste.`;
            } catch (e) {
              this._error = `Anwenden fehlgeschlagen: ${e.message || e}`;
            }
            this._applying = false;
          } else {
            this._success = `Dashboard generiert (1 Haupt + ${roomCount} Räume). Klicke auf "Anwenden".`;
          }
          await this._loadPreview();
        } else if (result.status === "error") {
          this._autoApplyAfterGenerate = false;
          this._error = `Fehler: ${result.error_message || "Unbekannter Fehler"}`;
        }
      }
    } catch (e) {
      console.error("Failed to load status:", e);
    }
  }

  async _loadSettings() {
    try {
      const result = await this.hass.callWS({ type: `${DOMAIN}/get_settings` });
      this._settings = { ...result.data, ...result.options };
    } catch (e) {
      console.error("Failed to load settings:", e);
    }
  }

  async _loadImages() {
    try {
      const result = await this.hass.callWS({ type: `${DOMAIN}/get_images` });
      this._images = result.images || {};
    } catch (e) {
      console.error("Failed to load images:", e);
    }
  }

  async _loadPreview() {
    try {
      const result = await this.hass.callWS({ type: `${DOMAIN}/get_preview` });
      this._previewConfig = result.config;
    } catch (e) {
      console.error("Failed to load preview:", e);
    }
  }

  async _handleGenerate() {
    this._error = null;
    this._success = null;
    this._generating = true;
    this._status = "generating";

    try {
      await this.hass.callWS({ type: `${DOMAIN}/generate`, options: {} });
    } catch (e) {
      this._generating = false;
      this._status = "error";
      this._error = `Generierung fehlgeschlagen: ${e.message || e}`;
    }
  }

  async _handleGenerateAndApply() {
    this._error = null;
    this._success = null;
    this._generating = true;
    this._status = "generating";

    try {
      await this.hass.callWS({ type: `${DOMAIN}/generate`, options: {} });
      // Wait briefly for generation to finish via event, then apply
      // Generation result comes via HA event; _generating is reset in _listenForEvents.
      // We chain apply after done in the event listener by setting a flag.
      this._autoApplyAfterGenerate = true;
    } catch (e) {
      this._generating = false;
      this._status = "error";
      this._error = `Generierung fehlgeschlagen: ${e.message || e}`;
    }
  }

  async _handleApply() {
    this._applying = true;
    this._error = null;
    const roomCount = this._areas.filter((a) => a.area_id !== "_unassigned").length;

    try {
      await this.hass.callWS({ type: `${DOMAIN}/apply` });
      this._success = `✅ ${roomCount + 1} Dashboards angewendet! Haupt-Dashboard + ${roomCount} Raum-Dashboards. Öffne "AI Dashboard" in der Seitenleiste.`;
    } catch (e) {
      this._error = `Anwenden fehlgeschlagen: ${e.message || e}`;
    }
    this._applying = false;
  }

  async _handleRefresh() {
    this._error = null;
    this._success = null;
    this._loading = true;
    await this._loadAreas();
    this._loading = false;
    this._success = "Räume und Entities wurden neu geladen.";
  }

  async _handleImageUpload(event, areaId) {
    const file = event.target.files[0];
    if (!file) return;

    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      this._error = "Nur JPG, PNG und WebP werden unterstützt.";
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      this._error = "Bild darf maximal 5 MB groß sein.";
      return;
    }

    this._uploadingArea = areaId;
    this._error = null;

    try {
      const base64 = await this._fileToBase64(file);
      await this.hass.callWS({
        type: `${DOMAIN}/upload_image`,
        area_id: areaId,
        image_data: base64.split(",")[1],
        filename: file.name,
      });
      await this._loadImages();
      this._success = `Bild für Raum hochgeladen.`;
    } catch (e) {
      this._error = `Bild-Upload fehlgeschlagen: ${e.message || e}`;
    }
    this._uploadingArea = null;
  }

  async _handleDeleteImage(areaId) {
    try {
      await this.hass.callWS({
        type: `${DOMAIN}/delete_image`,
        area_id: areaId,
      });
      await this._loadImages();
    } catch (e) {
      this._error = `Bild löschen fehlgeschlagen: ${e.message || e}`;
    }
  }

  async _handleSaveSettings(settings) {
    try {
      await this.hass.callWS({
        type: `${DOMAIN}/update_settings`,
        settings,
      });
      await this._loadSettings();
      this._success = "Einstellungen gespeichert.";
    } catch (e) {
      this._error = `Einstellungen speichern fehlgeschlagen: ${e.message || e}`;
    }
  }

  _fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────

  render() {
    return html`
      <div class="panel-root">
        <!-- Header -->
        <div class="panel-header">
          <div class="header-left">
            <ha-icon icon="mdi:robot-happy" class="header-icon"></ha-icon>
            <div>
              <h1>AI Dashboard Generator</h1>
              <p class="header-subtitle">Erstellt automatisch moderne Dashboards</p>
            </div>
          </div>
          <div class="header-actions">
            <ha-icon-button
              .label=${"Räume neu laden"}
              @click=${this._handleRefresh}
              ?disabled=${this._loading || this._generating}
            >
              <ha-icon icon="mdi:refresh"></ha-icon>
            </ha-icon-button>
          </div>
        </div>

        <!-- Tabs -->
        <div class="tabs">
          ${["dashboard", "rooms", "assistant", "settings"].map(
            (tab) => html`
              <button
                class="tab ${this._activeTab === tab ? "active" : ""}"
                @click=${() => (this._activeTab = tab)}
              >
                <ha-icon icon=${
                  tab === "dashboard" ? "mdi:view-dashboard"
                  : tab === "rooms" ? "mdi:floor-plan"
                  : tab === "assistant" ? "mdi:robot-happy"
                  : "mdi:cog"
                }></ha-icon>
                ${
                  tab === "dashboard" ? "Dashboard"
                  : tab === "rooms" ? "Räume & Bilder"
                  : tab === "assistant" ? "KI-Assistent"
                  : "Einstellungen"
                }
                ${tab === "assistant" && this._pendingActions.length > 0
                  ? html`<span class="tab-badge">${this._pendingActions.length}</span>`
                  : nothing}
              </button>
            `
          )}
        </div>

        <!-- Messages -->
        ${this._error
          ? html`<div class="message error">
              <ha-icon icon="mdi:alert-circle"></ha-icon>
              <span>${this._error}</span>
              <button class="close-btn" @click=${() => (this._error = null)}>✕</button>
            </div>`
          : nothing}
        ${this._success
          ? html`<div class="message success">
              <ha-icon icon="mdi:check-circle"></ha-icon>
              <span>${this._success}</span>
              <button class="close-btn" @click=${() => (this._success = null)}>✕</button>
            </div>`
          : nothing}

        <!-- Tab Content -->
        <div class="tab-content">
          ${this._loading
            ? html`<div class="loading">
                <ha-circular-progress active></ha-circular-progress>
                <p>Lade Daten...</p>
              </div>`
            : this._activeTab === "dashboard"
            ? this._renderDashboardTab()
            : this._activeTab === "rooms"
            ? this._renderRoomsTab()
            : this._activeTab === "assistant"
            ? this._renderAssistantTab()
            : this._renderSettingsTab()}
        </div>
      </div>
    `;
  }

  _renderDashboardTab() {
    const hasDashboard = this._status === "done" || this._previewConfig;
    const rooms = this._areas.filter((a) => a.area_id !== "_unassigned");
    const roomCount = rooms.length;
    return html`
      <!-- Status Card -->
      <div class="card status-card">
        <div class="card-header">
          <ha-icon icon="mdi:information-outline"></ha-icon>
          <h2>Status</h2>
        </div>
        <div class="status-grid">
          <div class="stat">
            <span class="stat-value">${roomCount}</span>
            <span class="stat-label">Räume</span>
          </div>
          <div class="stat">
            <span class="stat-value">${this._areas.reduce((s, a) => s + a.relevant_entities, 0)}</span>
            <span class="stat-label">Aktive Entities</span>
          </div>
          <div class="stat">
            <span class="stat-value">${this._areas.reduce((s, a) => s + a.total_entities, 0)}</span>
            <span class="stat-label">Gesamt Entities</span>
          </div>
          <div class="stat">
            <span class="stat-value">${Object.keys(this._images).length}</span>
            <span class="stat-label">Raumbilder</span>
          </div>
        </div>
        ${this._lastGenerated
          ? html`<p class="last-generated">
              Zuletzt generiert: ${new Date(this._lastGenerated).toLocaleString("de")}
            </p>`
          : nothing}
      </div>

      <!-- Dashboard Architecture -->
      <div class="card architecture-card">
        <div class="card-header">
          <ha-icon icon="mdi:view-dashboard-variant"></ha-icon>
          <h2>Dashboard-Struktur</h2>
        </div>
        <p class="architecture-desc">
          Die KI erstellt automatisch ein vollständiges Dashboard-System:
        </p>
        <div class="architecture-diagram">
          <!-- Main dashboard -->
          <div class="arch-main">
            <ha-icon icon="mdi:home"></ha-icon>
            <span class="arch-label">Haupt-Dashboard</span>
            <span class="arch-sub">/ai-dashboard</span>
          </div>
          <!-- Arrow -->
          <div class="arch-arrow-down">
            <ha-icon icon="mdi:arrow-down-thin"></ha-icon>
            <span>Navigations-Buttons für jeden Raum</span>
          </div>
          <!-- Room dashboards -->
          <div class="arch-rooms">
            ${roomCount > 0
              ? rooms.slice(0, 6).map(
                  (area) => html`
                    <div class="arch-room">
                      <ha-icon icon=${area.icon || "mdi:home-floor-1"}></ha-icon>
                      <span>${area.name}</span>
                    </div>
                  `
                )
              : html`<div class="arch-room arch-room-placeholder">
                  <ha-icon icon="mdi:home-floor-1"></ha-icon>
                  <span>Raum 1</span>
                </div>
                <div class="arch-room arch-room-placeholder">
                  <ha-icon icon="mdi:home-floor-2"></ha-icon>
                  <span>Raum 2</span>
                </div>
                <div class="arch-room arch-room-placeholder">
                  <ha-icon icon="mdi:home-floor-3"></ha-icon>
                  <span>Raum 3</span>
                </div>`}
            ${roomCount > 6
              ? html`<div class="arch-room arch-room-more">+${roomCount - 6} weitere</div>`
              : nothing}
          </div>
        </div>
      </div>

      <!-- AI Provider Info -->
      <div class="card ai-card">
        <div class="card-header">
          <ha-icon icon="mdi:brain"></ha-icon>
          <h2>KI-Anbieter</h2>
        </div>
        <div class="ai-provider-info">
          <ha-icon icon=${this._getProviderIcon()} class="provider-icon"></ha-icon>
          <div>
            <strong>${this._getProviderName()}</strong>
            <p>${this._getProviderDescription()}</p>
          </div>
        </div>
      </div>

      <!-- Generate Button -->
      <div class="card generate-card">
        <div class="card-header">
          <ha-icon icon="mdi:magic-staff"></ha-icon>
          <h2>${hasDashboard ? "Dashboards neu generieren" : "Dashboards erstellen"}</h2>
        </div>
        <p class="generate-description">
          ${hasDashboard
            ? `Erstellt ${roomCount + 1} neue Dashboards (1 Haupt + ${roomCount} Räume) mit allen aktuellen Entities.`
            : `Analysiert alle Entities und erstellt automatisch 1 Haupt-Dashboard + ${roomCount} Raum-Dashboards.`}
        </p>
        <div class="generate-steps">
          <div class="step ${this._generating ? "active" : hasDashboard ? "done" : ""}">
            <div class="step-icon">
              <ha-icon icon="mdi:magnify"></ha-icon>
            </div>
            <span>Entities analysieren</span>
          </div>
          <div class="step-divider"></div>
          <div class="step ${this._generating && this._status !== "idle" ? "active" : hasDashboard ? "done" : ""}">
            <div class="step-icon">
              <ha-icon icon="mdi:brain"></ha-icon>
            </div>
            <span>KI optimiert</span>
          </div>
          <div class="step-divider"></div>
          <div class="step ${hasDashboard ? "done" : ""}">
            <div class="step-icon">
              <ha-icon icon="mdi:view-dashboard-variant"></ha-icon>
            </div>
            <span>${roomCount + 1} Dashboards erstellt</span>
          </div>
        </div>
        <div class="button-row">
          <!-- One-click: generate + apply -->
          <button
            class="btn btn-primary ${this._generating || this._applying ? "loading" : ""}"
            @click=${this._handleGenerateAndApply}
            ?disabled=${this._generating || this._applying}
          >
            ${this._generating
              ? html`<ha-circular-progress active size="small"></ha-circular-progress>
                  Generiere...`
              : this._applying
              ? html`<ha-circular-progress active size="small"></ha-circular-progress>
                  Anwenden...`
              : html`<ha-icon icon="mdi:creation"></ha-icon>
                  ${hasDashboard ? "Alles neu erstellen & anwenden" : "Alles erstellen & anwenden"}`}
          </button>
        </div>
        <div class="button-row button-row-secondary">
          <!-- Manual: generate only -->
          <button
            class="btn btn-secondary ${this._generating ? "loading" : ""}"
            @click=${this._handleGenerate}
            ?disabled=${this._generating || this._applying}
          >
            ${this._generating
              ? html`<ha-circular-progress active size="small"></ha-circular-progress>
                  Generiere...`
              : html`<ha-icon icon="mdi:magic-staff"></ha-icon>
                  Nur generieren`}
          </button>
          ${hasDashboard
            ? html`<button
                class="btn btn-success ${this._applying ? "loading" : ""}"
                @click=${this._handleApply}
                ?disabled=${this._applying || this._generating}
              >
                ${this._applying
                  ? html`<ha-circular-progress active size="small"></ha-circular-progress>
                      Anwenden...`
                  : html`<ha-icon icon="mdi:check"></ha-icon>
                      Nur anwenden`}
              </button>`
            : nothing}
          ${hasDashboard
            ? html`<button
                class="btn btn-secondary"
                @click=${() => {
                  this._showPreview = !this._showPreview;
                  if (this._showPreview && !this._previewConfig) this._loadPreview();
                }}
              >
                <ha-icon icon="mdi:eye"></ha-icon>
                ${this._showPreview ? "Vorschau verstecken" : "JSON Vorschau"}
              </button>`
            : nothing}
        </div>

        ${hasDashboard
          ? html`
              <div class="dashboard-links">
                <p><strong>Deine Dashboards nach dem Anwenden:</strong></p>
                <div class="link-list">
                  <a href="/ai-dashboard" target="_blank" class="dash-link">
                    <ha-icon icon="mdi:home"></ha-icon>
                    <span>Haupt-Dashboard <em>/ai-dashboard</em></span>
                    <ha-icon icon="mdi:open-in-new"></ha-icon>
                  </a>
                  ${rooms.slice(0, 5).map(
                    (area) => html`
                      <a href="/ai-dashboard-${area.area_id}" target="_blank" class="dash-link dash-link-room">
                        <ha-icon icon=${area.icon || "mdi:home-floor-1"}></ha-icon>
                        <span>${area.name} <em>/ai-dashboard-${area.area_id}</em></span>
                        <ha-icon icon="mdi:open-in-new"></ha-icon>
                      </a>
                    `
                  )}
                  ${rooms.length > 5
                    ? html`<p class="more-links">... und ${rooms.length - 5} weitere Raum-Dashboards</p>`
                    : nothing}
                </div>
              </div>
            `
          : nothing}
      </div>

      <!-- YAML Preview -->
      ${this._showPreview && this._previewConfig
        ? html`<div class="card preview-card">
            <div class="card-header">
              <ha-icon icon="mdi:code-braces"></ha-icon>
              <h2>Generierter Dashboard-Config (JSON)</h2>
            </div>
            <pre class="yaml-preview">${JSON.stringify(this._previewConfig, null, 2)}</pre>
          </div>`
        : nothing}

      <!-- Info Card -->
      <div class="card info-card">
        <div class="card-header">
          <ha-icon icon="mdi:lightbulb-outline"></ha-icon>
          <h2>Hinweise</h2>
        </div>
        <ul class="info-list">
          <li>
            <ha-icon icon="mdi:cards-playing-club-multiple-outline"></ha-icon>
            Für das beste Ergebnis installiere
            <a href="https://github.com/piitaya/lovelace-mushroom" target="_blank">Mushroom Cards</a>
            über HACS.
          </li>
          <li>
            <ha-icon icon="mdi:home-floor-plan"></ha-icon>
            Weise deine Geräte in HA Einstellungen → Bereiche & Zonen den Räumen zu.
          </li>
          <li>
            <ha-icon icon="mdi:refresh"></ha-icon>
            Nach dem Hinzufügen neuer Geräte klicke auf "Alles neu erstellen & anwenden".
          </li>
          <li>
            <ha-icon icon="mdi:image"></ha-icon>
            Lade Raumbilder im Tab "Räume & Bilder" hoch für ein personalisiertes Design.
          </li>
        </ul>
      </div>
    `;
  }

  _renderRoomsTab() {
    const assignedAreas = this._areas.filter((a) => a.area_id !== "_unassigned");
    const unassigned = this._areas.find((a) => a.area_id === "_unassigned");

    return html`
      <div class="rooms-grid">
        ${assignedAreas.map((area) => this._renderAreaCard(area))}
      </div>

      ${unassigned && unassigned.total_entities > 0
        ? html`
            <div class="card unassigned-card">
              <div class="card-header">
                <ha-icon icon="mdi:help-circle"></ha-icon>
                <h2>Nicht zugewiesene Entities (${unassigned.total_entities})</h2>
              </div>
              <p>Diese Entities haben keinen Raum zugewiesen. Weise sie in <strong>Einstellungen → Bereiche & Zonen</strong> zu.</p>
              <div class="entity-list">
                ${unassigned.entities.slice(0, 10).map(
                  (e) => html`
                    <div class="entity-item">
                      <ha-icon icon=${e.suggested_icon || "mdi:help-circle"}></ha-icon>
                      <span class="entity-name">${e.suggested_name || e.friendly_name}</span>
                      <span class="entity-id">${e.entity_id}</span>
                    </div>
                  `
                )}
                ${unassigned.entities.length > 10
                  ? html`<p class="more-items">... und ${unassigned.entities.length - 10} weitere</p>`
                  : nothing}
              </div>
            </div>
          `
        : nothing}
    `;
  }

  _renderAreaCard(area) {
    const image = this._images[area.area_id];
    const isUploading = this._uploadingArea === area.area_id;

    const entityDomains = Object.entries(area.entity_counts || {})
      .filter(([, count]) => count > 0)
      .map(([domain, count]) => ({ domain, count }));

    const domainIcons = {
      light: "mdi:lightbulb",
      switch: "mdi:toggle-switch",
      sensor: "mdi:chart-line",
      binary_sensor: "mdi:eye",
      climate: "mdi:thermometer",
      media_player: "mdi:television-play",
      cover: "mdi:window-shutter",
      camera: "mdi:cctv",
      alarm_control_panel: "mdi:shield-home",
      fan: "mdi:fan",
      vacuum: "mdi:robot-vacuum",
      lock: "mdi:lock",
    };

    return html`
      <div class="area-card card">
        <!-- Area image or placeholder -->
        <div class="area-image-container">
          ${image
            ? html`
                <img src="${image}" class="area-image" alt="${area.name}" />
                <button
                  class="delete-image-btn"
                  @click=${() => this._handleDeleteImage(area.area_id)}
                  title="Bild löschen"
                >
                  <ha-icon icon="mdi:delete"></ha-icon>
                </button>
              `
            : html`
                <div class="area-image-placeholder">
                  <ha-icon icon=${area.icon || "mdi:home-floor-1"}></ha-icon>
                </div>
              `}

          <!-- Upload overlay -->
          <label class="upload-overlay" for="upload-${area.area_id}">
            ${isUploading
              ? html`<ha-circular-progress active></ha-circular-progress>`
              : html`<ha-icon icon="mdi:camera-plus"></ha-icon>
                  <span>${image ? "Bild ändern" : "Bild hochladen"}</span>`}
          </label>
          <input
            type="file"
            id="upload-${area.area_id}"
            accept="image/jpeg,image/png,image/webp"
            style="display:none"
            @change=${(e) => this._handleImageUpload(e, area.area_id)}
          />
        </div>

        <!-- Area info -->
        <div class="area-info">
          <div class="area-name-row">
            <ha-icon icon=${area.icon || "mdi:home-floor-1"} class="area-icon"></ha-icon>
            <h3>${area.name}</h3>
          </div>

          <div class="entity-counts">
            ${entityDomains.slice(0, 5).map(
              ({ domain, count }) => html`
                <div class="entity-count-chip">
                  <ha-icon icon=${domainIcons[domain] || "mdi:help-circle"}></ha-icon>
                  <span>${count}</span>
                </div>
              `
            )}
          </div>

          <div class="area-stats">
            <span class="stat-badge relevant">${area.relevant_entities} Aktiv</span>
            <span class="stat-badge hidden-badge">${area.total_entities - area.relevant_entities} Ausgeblendet</span>
          </div>
        </div>

        <!-- Entity preview -->
        ${area.entities.length > 0
          ? html`
              <details class="entity-details">
                <summary>Entities anzeigen (${area.entities.length})</summary>
                <div class="entity-list">
                  ${area.entities.map(
                    (e) => html`
                      <div class="entity-item">
                        <ha-icon icon=${e.suggested_icon || "mdi:help-circle"}></ha-icon>
                        <div class="entity-info">
                          <span class="entity-name">${e.suggested_name || e.friendly_name}</span>
                          <span class="entity-id">${e.entity_id}</span>
                        </div>
                        <span class="entity-state ${e.state === "on" ? "state-on" : e.state === "off" ? "state-off" : "state-other"}">${e.state}</span>
                      </div>
                    `
                  )}
                  ${area.hidden_entities?.length > 0
                    ? html`
                        <div class="hidden-entities-label">
                          <ha-icon icon="mdi:eye-off"></ha-icon>
                          ${area.hidden_entities.length} ausgeblendete Entities
                        </div>
                      `
                    : nothing}
                </div>
              </details>
            `
          : nothing}
      </div>
    `;
  }

  async _loadChatHistory() {
    try {
      const result = await this.hass.callWS({ type: `${DOMAIN}/assistant_history` });
      const history = result.history || [];
      this._chatMessages = history.map((m) => ({
        role: m.role,
        content: m.content,
        timestamp: null,
      }));
    } catch (e) {
      // Chat history not critical
    }
  }

  async _handleChatSend() {
    const message = this._chatInput.trim();
    if (!message || this._chatLoading) return;

    this._chatInput = "";
    this._chatMessages = [
      ...this._chatMessages,
      { role: "user", content: message, timestamp: new Date().toLocaleTimeString("de") },
    ];
    this._chatLoading = true;
    this._pendingActions = [];
    this._executedActions = [];

    try {
      const result = await this.hass.callWS({
        type: `${DOMAIN}/assistant_chat`,
        message,
        auto_execute: this._autoExecute,
        context_depth: "standard",
      });

      this._chatMessages = [
        ...this._chatMessages,
        {
          role: "assistant",
          content: result.message,
          timestamp: new Date().toLocaleTimeString("de"),
          executed_actions: result.executed_actions || [],
        },
      ];

      this._pendingActions = result.actions || [];
      this._executedActions = result.executed_actions || [];

      if (result.requires_confirmation && this._pendingActions.length > 0) {
        // Scroll to bottom
        this._scrollChatToBottom();
      }
    } catch (e) {
      this._chatMessages = [
        ...this._chatMessages,
        {
          role: "error",
          content: `Fehler: ${e.message || e}`,
          timestamp: new Date().toLocaleTimeString("de"),
        },
      ];
    }
    this._chatLoading = false;
    this._scrollChatToBottom();
  }

  async _handleExecuteActions() {
    if (this._pendingActions.length === 0) return;
    this._chatLoading = true;

    try {
      const result = await this.hass.callWS({
        type: `${DOMAIN}/assistant_execute`,
        actions: this._pendingActions,
      });

      const results = result.results || [];
      const allOk = results.every((r) => r.success);
      const summary = results
        .map((r) => `${r.success ? "✅" : "❌"} ${r.description}`)
        .join("\n");

      this._chatMessages = [
        ...this._chatMessages,
        {
          role: "assistant",
          content: allOk
            ? `Alle Aktionen erfolgreich ausgeführt:\n${summary}`
            : `Einige Aktionen schlugen fehl:\n${summary}`,
          timestamp: new Date().toLocaleTimeString("de"),
          executed_actions: results,
        },
      ];
      this._pendingActions = [];
    } catch (e) {
      this._chatMessages = [
        ...this._chatMessages,
        {
          role: "error",
          content: `Ausführungsfehler: ${e.message || e}`,
          timestamp: new Date().toLocaleTimeString("de"),
        },
      ];
    }
    this._chatLoading = false;
    this._scrollChatToBottom();
  }

  _handleDenyActions() {
    this._chatMessages = [
      ...this._chatMessages,
      {
        role: "assistant",
        content: "Aktionen abgebrochen. Kein Problem, ich habe nichts geändert.",
        timestamp: new Date().toLocaleTimeString("de"),
      },
    ];
    this._pendingActions = [];
  }

  async _handleClearChat() {
    try {
      await this.hass.callWS({ type: `${DOMAIN}/assistant_clear` });
    } catch (e) { /* ignore */ }
    this._chatMessages = [];
    this._pendingActions = [];
    this._executedActions = [];
  }

  _scrollChatToBottom() {
    this.updateComplete.then(() => {
      const chatEl = this.shadowRoot?.querySelector(".chat-messages");
      if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;
    });
  }

  _renderAssistantTab() {
    const provider = this._settings.ai_provider || "groq";

    return html`
      <div class="chat-container card">
        <!-- Chat header -->
        <div class="chat-header">
          <div class="chat-header-left">
            <ha-icon icon="mdi:robot-happy" class="chat-bot-icon"></ha-icon>
            <div>
              <strong>KI-Assistent</strong>
              <span class="chat-provider-badge">${this._getProviderName()}</span>
            </div>
          </div>
          <div class="chat-header-actions">
            <label class="auto-execute-toggle" title="Aktionen direkt ausführen ohne Bestätigung">
              <input
                type="checkbox"
                ?checked=${this._autoExecute}
                @change=${(e) => (this._autoExecute = e.target.checked)}
              />
              <span>Auto-Execute</span>
            </label>
            <button class="btn btn-secondary btn-sm" @click=${this._handleClearChat} title="Chat leeren">
              <ha-icon icon="mdi:delete-sweep"></ha-icon>
            </button>
          </div>
        </div>

        <!-- Messages -->
        <div class="chat-messages" id="chat-messages">
          ${this._chatMessages.length === 0
            ? html`
                <div class="chat-welcome">
                  <ha-icon icon="mdi:robot-happy"></ha-icon>
                  <h3>Hallo! Ich bin dein Home Assistant KI-Assistent.</h3>
                  <p>Ich habe Zugriff auf alle deine Entities, Bereiche und Automationen und kann Änderungen für dich vornehmen.</p>
                  <div class="suggestion-chips">
                    ${[
                      "Was sind meine aktuell eingeschalteten Lichter?",
                      "Erstelle eine Automation: Licht aus wenn niemand zuhause",
                      "Benenne alle Sensoren im Wohnzimmer sauber",
                      "Wie warm ist es in den verschiedenen Räumen?",
                      "Erstelle eine Szene 'Filmabend' im Wohnzimmer",
                      "Generiere ein neues Dashboard",
                    ].map(
                      (s) => html`
                        <button
                          class="suggestion-chip"
                          @click=${() => {
                            this._chatInput = s;
                            this._handleChatSend();
                          }}
                        >${s}</button>
                      `
                    )}
                  </div>
                </div>
              `
            : nothing}

          ${this._chatMessages.map(
            (msg) => html`
              <div class="chat-message ${msg.role}">
                ${msg.role === "user"
                  ? html`
                      <div class="msg-avatar user-avatar">
                        <ha-icon icon="mdi:account"></ha-icon>
                      </div>
                      <div class="msg-body">
                        <div class="msg-bubble user-bubble">${msg.content}</div>
                        ${msg.timestamp ? html`<span class="msg-time">${msg.timestamp}</span>` : nothing}
                      </div>
                    `
                  : msg.role === "error"
                  ? html`
                      <div class="msg-avatar error-avatar">
                        <ha-icon icon="mdi:alert-circle"></ha-icon>
                      </div>
                      <div class="msg-body">
                        <div class="msg-bubble error-bubble">${msg.content}</div>
                      </div>
                    `
                  : html`
                      <div class="msg-avatar bot-avatar">
                        <ha-icon icon="mdi:robot-happy"></ha-icon>
                      </div>
                      <div class="msg-body">
                        <div class="msg-bubble bot-bubble">${this._renderMarkdownish(msg.content)}</div>
                        ${msg.executed_actions && msg.executed_actions.length > 0
                          ? html`
                              <div class="executed-actions">
                                ${msg.executed_actions.map(
                                  (a) => html`
                                    <div class="executed-action ${a.success ? "ok" : "fail"}">
                                      <ha-icon icon=${a.success ? "mdi:check-circle" : "mdi:close-circle"}></ha-icon>
                                      <span>${a.description}</span>
                                    </div>
                                  `
                                )}
                              </div>
                            `
                          : nothing}
                        ${msg.timestamp ? html`<span class="msg-time">${msg.timestamp}</span>` : nothing}
                      </div>
                    `}
              </div>
            `
          )}

          ${this._chatLoading
            ? html`
                <div class="chat-message assistant">
                  <div class="msg-avatar bot-avatar">
                    <ha-icon icon="mdi:robot-happy"></ha-icon>
                  </div>
                  <div class="msg-body">
                    <div class="msg-bubble bot-bubble typing-indicator">
                      <span></span><span></span><span></span>
                    </div>
                  </div>
                </div>
              `
            : nothing}
        </div>

        <!-- Pending actions confirmation -->
        ${this._pendingActions.length > 0 && !this._chatLoading
          ? html`
              <div class="pending-actions-panel">
                <div class="pending-header">
                  <ha-icon icon="mdi:shield-alert"></ha-icon>
                  <strong>Der Assistent möchte folgende Änderungen vornehmen:</strong>
                </div>
                <ul class="pending-list">
                  ${this._pendingActions.map(
                    (a) => html`
                      <li class="pending-item ${a.is_destructive ? "destructive" : ""}">
                        <ha-icon icon=${a.is_destructive ? "mdi:pencil" : "mdi:information"}></ha-icon>
                        <span>${a.description}</span>
                      </li>
                    `
                  )}
                </ul>
                <div class="pending-buttons">
                  <button class="btn btn-success" @click=${this._handleExecuteActions}>
                    <ha-icon icon="mdi:check"></ha-icon>
                    Alle ausführen
                  </button>
                  <button class="btn btn-secondary" @click=${this._handleDenyActions}>
                    <ha-icon icon="mdi:close"></ha-icon>
                    Ablehnen
                  </button>
                </div>
              </div>
            `
          : nothing}

        <!-- Input -->
        <div class="chat-input-area">
          <textarea
            class="chat-input"
            placeholder="Frage stellen oder Befehl eingeben... (Enter = Senden, Shift+Enter = Neue Zeile)"
            .value=${this._chatInput}
            ?disabled=${this._chatLoading}
            @input=${(e) => (this._chatInput = e.target.value)}
            @keydown=${(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                this._handleChatSend();
              }
            }}
            rows="2"
          ></textarea>
          <button
            class="chat-send-btn"
            @click=${this._handleChatSend}
            ?disabled=${this._chatLoading || !this._chatInput.trim()}
            title="Nachricht senden"
          >
            ${this._chatLoading
              ? html`<ha-circular-progress active size="small"></ha-circular-progress>`
              : html`<ha-icon icon="mdi:send"></ha-icon>`}
          </button>
        </div>
      </div>

      <!-- Capability Info -->
      <div class="card info-card">
        <div class="card-header">
          <ha-icon icon="mdi:information-outline"></ha-icon>
          <h2>Was kann der KI-Assistent?</h2>
        </div>
        <ul class="info-list">
          <li><ha-icon icon="mdi:lightbulb"></ha-icon>Lichter, Heizung, Medien, Rolläden und alle anderen Geräte steuern</li>
          <li><ha-icon icon="mdi:robot"></ha-icon>Automationen erstellen (z.B. "Licht aus wenn niemand zuhause")</li>
          <li><ha-icon icon="mdi:palette"></ha-icon>Szenen erstellen (z.B. "Filmabend", "Guten Morgen")</li>
          <li><ha-icon icon="mdi:pencil"></ha-icon>Entities umbenennen und Bereichen zuweisen</li>
          <li><ha-icon icon="mdi:magnify"></ha-icon>Entities nach Domain, Bereich, Geräteklasse suchen</li>
          <li><ha-icon icon="mdi:chart-line"></ha-icon>Zustände und Verlauf von Sensoren abfragen</li>
          <li><ha-icon icon="mdi:view-dashboard"></ha-icon>Dashboard automatisch generieren und anwenden</li>
        </ul>
        <p style="margin-top:12px;font-size:0.85rem;color:var(--secondary-text-color)">
          ⚠️ Änderungen werden direkt in Home Assistant gespeichert. Mit <strong>Auto-Execute</strong> 
          werden alle Aktionen sofort ausgeführt, ohne Bestätigungsschritt.
        </p>
      </div>
    `;
  }

  _getProviderName() {
    const map = {
      openai: "OpenAI GPT",
      anthropic: "Anthropic Claude",
      google: "Google Gemini",
    };
    return map[this._settings?.ai_provider] || "KI";
  }

  _renderMarkdownish(text) {
    if (!text) return nothing;
    // Very simple markdown-like rendering: newlines, bold, code
    return html`${text.split("\n").map((line, i) => html`${i > 0 ? html`<br>` : nothing}${line}`)}`;
  }

  _renderSettingsTab() {
    const currentProvider = this._settings.ai_provider || "groq";
    const currentModel = this._settings.ai_model || "";
    const currentApiKey = this._settings.api_key || "";
    const currentBaseUrl = this._settings.base_url || "https://aiprimetech.io/v1";
    const useMushroom = this._settings.use_mushroom !== false;
    const language = this._settings.language || "de";
    const dashboardTitle = this._settings.dashboard_title || "AI Dashboard";

    return html`
      <div class="card settings-card">
        <div class="card-header">
          <ha-icon icon="mdi:brain"></ha-icon>
          <h2>KI-Einstellungen</h2>
        </div>

        <form
          @submit=${(e) => {
            e.preventDefault();
            const data = new FormData(e.target);
            this._handleSaveSettings({
              ai_provider: data.get("ai_provider"),
              api_key: data.get("api_key") || "",
              ai_model: data.get("ai_model") || "",
              base_url: data.get("base_url") || "",
              use_mushroom: data.get("use_mushroom") === "on",
              language: data.get("language"),
              dashboard_title: data.get("dashboard_title"),
            });
          }}
        >
          <div class="form-group">
            <label>KI-Anbieter</label>
            <!-- .value binding guarantees the select shows the correct saved value after reload -->
            <select name="ai_provider" class="form-control"
              .value=${currentProvider}
              @change=${(e) => {
                this._settings = { ...this._settings, ai_provider: e.target.value };
              }}>
              <option value="openai">🤖 OpenAI (GPT-5.5 / GPT-5.4-mini)</option>
              <option value="anthropic">🧠 Anthropic (Claude Opus 4.7 / Sonnet 4.6)</option>
              <option value="google">✨ Google (Gemini 2.5 Flash / Pro)</option>
              <option value="groq">⚡ Groq (Llama 4 / Llama 3.3 – kostenlos &amp; schnell)</option>
              <option value="opencode">🌐 OpenCode.ai (Custom Endpoint / Anthropic)</option>
            </select>
          </div>

          <div class="form-group">
            <label>API-Schlüssel</label>
            <input
              type="password"
              name="api_key"
              class="form-control"
              .value=${currentApiKey}
              placeholder="sk-... / claude-... / AIza... / gsk_..."
              autocomplete="off"
            />
            <small>Wird verschlüsselt gespeichert. Nie geteilt.</small>
            ${currentProvider === "groq" ? html`
              <small style="display:block;margin-top:4px">
                Groq API-Key kostenlos auf
                <a href="https://console.groq.com/keys" target="_blank" rel="noopener">console.groq.com</a>
              </small>
            ` : nothing}
          </div>

          ${currentProvider === "opencode" ? html`
            <div class="form-group">
              <label>Base URL</label>
              <input
                type="url"
                name="base_url"
                class="form-control"
                .value=${currentBaseUrl}
                placeholder="https://aiprimetech.io/v1"
              />
              <small>OpenAI-kompatibler Endpunkt. Hinweis: /v1 wird automatisch hinzugefügt falls nicht vorhanden</small>
            </div>
          ` : nothing}

          <div class="form-group">
            <label>Modell</label>
            <select name="ai_model" class="form-control" .value=${currentModel}>
              ${currentProvider === "openai" ? html`
                  <option value="gpt-4o-mini">GPT-4o Mini (bewährt, günstig)</option>
                  <option value="gpt-4o">GPT-4o (bewährt, gut)</option>
                  <option value="gpt-5.4-mini">GPT-5.4 Mini ✅ (neu, schnell &amp; günstig)</option>
                  <option value="gpt-5.4">GPT-5.4 (neu, beste Qualität)</option>
                  <option value="gpt-5.5">GPT-5.5 (neuestes Flaggschiff)</option>
                `
                : currentProvider === "anthropic" ? html`
                  <option value="claude-haiku-4-5">Claude Haiku 4.5 (schnell, günstig)</option>
                  <option value="claude-sonnet-4-6">Claude Sonnet 4.6 ✅ (empfohlen)</option>
                  <option value="claude-opus-4-7">Claude Opus 4.7 (bestes Modell)</option>
                `
                : currentProvider === "groq" ? html`
                  <option value="llama-3.1-8b-instant">Llama 3.1 8B (ultraschnell, kostenlos)</option>
                  <option value="llama-3.3-70b-versatile">Llama 3.3 70B ✅ (empfohlen, gut &amp; kostenlos)</option>
                  <option value="meta-llama/llama-4-scout-17b-16e-instruct">Llama 4 Scout 17B (Preview, sehr schnell)</option>
                  <option value="openai/gpt-oss-20b">GPT OSS 20B (1000 TPS, ultraschnell)</option>
                  <option value="openai/gpt-oss-120b">GPT OSS 120B (beste OSS-Qualität)</option>
                `
                : currentProvider === "opencode" ? html`
                  <option value="anthropic">Anthropic Claude (Standard)</option>
                  <option value="anthropic/claude-sonnet-4-6">Claude Sonnet 4.6</option>
                  <option value="anthropic/claude-opus-4-7">Claude Opus 4.7</option>
                  <option value="openai">OpenAI GPT (Standard)</option>
                  <option value="gpt-5.4-mini">GPT-5.4 Mini</option>
                `
                : html`
                  <option value="gemini-2.5-flash-lite">Gemini 2.5 Flash-Lite (schnell &amp; günstig)</option>
                  <option value="gemini-2.5-flash">Gemini 2.5 Flash ✅ (empfohlen)</option>
                  <option value="gemini-2.5-pro">Gemini 2.5 Pro (beste Qualität)</option>
                `}
            </select>
          </div>

          <hr class="divider" />

          <div class="form-group">
            <label>Dashboard-Titel</label>
            <input
              type="text"
              name="dashboard_title"
              class="form-control"
              .value=${dashboardTitle}
              placeholder="AI Dashboard"
            />
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input
                type="checkbox"
                name="use_mushroom"
                ?checked=${useMushroom}
              />
              Mushroom Cards verwenden (empfohlen, muss über HACS installiert sein)
            </label>
          </div>

          <div class="form-group">
            <label>Sprache</label>
            <select name="language" class="form-control" .value=${language}>
              <option value="de">🇩🇪 Deutsch</option>
              <option value="en">🇬🇧 English</option>
            </select>
          </div>

          <div class="button-row">
            <button type="submit" class="btn btn-primary">
              <ha-icon icon="mdi:content-save"></ha-icon>
              Einstellungen speichern
            </button>
          </div>
        </form>
      </div>

      <!-- Mushroom Cards Install Guide -->
      <div class="card info-card">
        <div class="card-header">
          <ha-icon icon="mdi:mushroom"></ha-icon>
          <h2>Mushroom Cards installieren</h2>
        </div>
        <ol class="install-steps">
          <li>Öffne <strong>HACS</strong> in der Seitenleiste</li>
          <li>Gehe zu <strong>Frontend</strong></li>
          <li>Suche nach <strong>"Mushroom"</strong></li>
          <li>Klicke auf <strong>Herunterladen</strong></li>
          <li>Starte Home Assistant neu oder lade die Seite neu (Strg+F5)</li>
        </ol>
        <a
          href="https://github.com/piitaya/lovelace-mushroom"
          target="_blank"
          class="btn btn-secondary"
          style="display:inline-flex;margin-top:8px"
        >
          <ha-icon icon="mdi:github"></ha-icon>
          Mushroom Cards auf GitHub
        </a>
      </div>
    `;
  }

  // ─────────────────────────────────────────────────────────────
  // Helper methods
  // ─────────────────────────────────────────────────────────────

  _getProviderIcon() {
    const provider = this._settings.ai_provider || "groq";
    const icons = {
      openai: "mdi:robot",
      anthropic: "mdi:brain",
      google: "mdi:google",
      groq: "mdi:lightning-bolt",
      opencode: "mdi:web",
    };
    return icons[provider] || "mdi:robot";
  }

  _getProviderName() {
    const provider = this._settings.ai_provider || "groq";
    const names = {
      openai: `OpenAI ${this._settings.ai_model || "GPT-5.4-mini"}`,
      anthropic: `Anthropic ${this._settings.ai_model || "Claude Sonnet 4.6"}`,
      google: `Google ${this._settings.ai_model || "Gemini 2.5 Flash"}`,
      groq: `Groq ${this._settings.ai_model || "Llama 3.3 70B"}`,
      opencode: `OpenCode.ai (${this._settings.ai_model || "anthropic"})`,
    };
    return names[provider] || "Unbekannt";
  }

  _getProviderDescription() {
    const provider = this._settings.ai_provider || "groq";
    const descs = {
      openai: "Nutzt OpenAI GPT für intelligente Benennungen und Empfehlungen.",
      anthropic: "Nutzt Anthropic Claude für intelligente Analyse und Design-Vorschläge.",
      google: "Nutzt Google Gemini für schnelle, intelligente Dashboard-Generierung.",
      groq: "Nutzt Groq's ultraschnelle Inferenz (bis 1000 t/s) – kostenloser Tier verfügbar.",
      opencode: "Nutzt OpenCode.ai / aiprimetech.io – OpenAI-kompatibler Custom-Endpunkt.",
    };
    return descs[provider] || "";
  }

  // ─────────────────────────────────────────────────────────────
  // Styles
  // ─────────────────────────────────────────────────────────────

  static get styles() {
    return css`
      :host {
        display: block;
        min-height: 100vh;
        background: var(--secondary-background-color, #f5f5f5);
        font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        color: var(--primary-text-color);
      }

      .panel-root {
        max-width: 1200px;
        margin: 0 auto;
        padding: 16px;
      }

      /* Header */
      .panel-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 0 16px;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
        margin-bottom: 16px;
      }

      .header-left {
        display: flex;
        align-items: center;
        gap: 16px;
      }

      .header-icon {
        --mdc-icon-size: 48px;
        color: var(--primary-color, #03a9f4);
      }

      .panel-header h1 {
        margin: 0;
        font-size: 1.6rem;
        font-weight: 600;
        color: var(--primary-text-color);
      }

      .header-subtitle {
        margin: 2px 0 0;
        color: var(--secondary-text-color);
        font-size: 0.875rem;
      }

      /* Tabs */
      .tabs {
        display: flex;
        gap: 4px;
        margin-bottom: 20px;
        background: var(--card-background-color, #fff);
        border-radius: 12px;
        padding: 6px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      }

      .tab {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 10px 16px;
        border: none;
        background: transparent;
        border-radius: 8px;
        cursor: pointer;
        color: var(--secondary-text-color);
        font-size: 0.9rem;
        font-weight: 500;
        transition: all 0.2s;
      }

      .tab:hover {
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
      }

      .tab.active {
        background: var(--primary-color, #03a9f4);
        color: white;
      }

      /* Cards */
      .card {
        background: var(--card-background-color, #fff);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
      }

      .card-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 16px;
      }

      .card-header ha-icon {
        color: var(--primary-color, #03a9f4);
        --mdc-icon-size: 24px;
      }

      .card-header h2 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
      }

      /* Messages */
      .message {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 12px;
        font-size: 0.9rem;
        font-weight: 500;
      }

      .message.error {
        background: #ffebee;
        color: #c62828;
        border-left: 4px solid #f44336;
      }

      .message.success {
        background: #e8f5e9;
        color: #1b5e20;
        border-left: 4px solid #4caf50;
      }

      .close-btn {
        margin-left: auto;
        background: none;
        border: none;
        cursor: pointer;
        color: inherit;
        font-size: 1rem;
        opacity: 0.7;
      }

      /* Status Grid */
      .status-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
      }

      .stat {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 12px;
        background: var(--secondary-background-color);
        border-radius: 10px;
      }

      .stat-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--primary-color, #03a9f4);
      }

      .stat-label {
        font-size: 0.75rem;
        color: var(--secondary-text-color);
        text-align: center;
        margin-top: 2px;
      }

      .last-generated {
        margin-top: 12px;
        font-size: 0.8rem;
        color: var(--secondary-text-color);
      }

      /* AI Provider */
      .ai-provider-info {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 12px;
        background: var(--secondary-background-color);
        border-radius: 10px;
      }

      .provider-icon {
        --mdc-icon-size: 40px;
        color: var(--primary-color);
      }

      .ai-provider-info p {
        margin: 4px 0 0;
        font-size: 0.85rem;
        color: var(--secondary-text-color);
      }

      /* Generate Steps */
      .generate-description {
        color: var(--secondary-text-color);
        margin-bottom: 20px;
      }

      .generate-steps {
        display: flex;
        align-items: center;
        margin-bottom: 24px;
      }

      .step {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 6px;
        flex: 1;
        font-size: 0.8rem;
        color: var(--secondary-text-color);
      }

      .step-icon {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background: var(--secondary-background-color);
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px solid var(--divider-color);
        transition: all 0.3s;
      }

      .step.active .step-icon {
        background: var(--primary-color);
        border-color: var(--primary-color);
        color: white;
        animation: pulse 1.5s infinite;
      }

      .step.done .step-icon {
        background: #4caf50;
        border-color: #4caf50;
        color: white;
      }

      .step.done {
        color: var(--primary-text-color);
      }

      .step-divider {
        flex: 0.3;
        height: 2px;
        background: var(--divider-color);
        margin-bottom: 20px;
      }

      @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.1); }
        100% { transform: scale(1); }
      }

      /* Buttons */
      .button-row {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }

      .btn {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 10px 20px;
        border: none;
        border-radius: 10px;
        cursor: pointer;
        font-size: 0.9rem;
        font-weight: 600;
        transition: all 0.2s;
        text-decoration: none;
      }

      .btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }

      .btn-primary {
        background: var(--primary-color, #03a9f4);
        color: white;
      }

      .btn-primary:hover:not(:disabled) {
        background: var(--dark-primary-color, #0288d1);
        transform: translateY(-1px);
      }

      .btn-success {
        background: #4caf50;
        color: white;
      }

      .btn-success:hover:not(:disabled) {
        background: #388e3c;
        transform: translateY(-1px);
      }

      .btn-secondary {
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
      }

      .btn-secondary:hover:not(:disabled) {
        background: var(--divider-color);
      }

      /* YAML Preview */
      .yaml-preview {
        background: #1e1e1e;
        color: #d4d4d4;
        padding: 16px;
        border-radius: 10px;
        overflow: auto;
        max-height: 500px;
        font-size: 0.75rem;
        line-height: 1.6;
        font-family: 'Courier New', monospace;
        white-space: pre-wrap;
        word-break: break-word;
      }

      /* Rooms Grid */
      .rooms-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 16px;
        margin-bottom: 16px;
      }

      .area-card {
        padding: 0;
        overflow: hidden;
      }

      .area-image-container {
        position: relative;
        height: 160px;
        overflow: hidden;
        background: var(--secondary-background-color);
      }

      .area-image {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .area-image-placeholder {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, var(--secondary-background-color), var(--divider-color));
      }

      .area-image-placeholder ha-icon {
        --mdc-icon-size: 64px;
        color: var(--secondary-text-color);
        opacity: 0.5;
      }

      .upload-overlay {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(0,0,0,0.5);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 8px;
        cursor: pointer;
        opacity: 0;
        transition: opacity 0.2s;
        font-size: 0.85rem;
      }

      .area-image-container:hover .upload-overlay {
        opacity: 1;
      }

      .delete-image-btn {
        position: absolute;
        top: 8px;
        right: 8px;
        background: rgba(244, 67, 54, 0.85);
        color: white;
        border: none;
        border-radius: 50%;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        opacity: 0;
        transition: opacity 0.2s;
      }

      .area-image-container:hover .delete-image-btn {
        opacity: 1;
      }

      .area-info {
        padding: 16px;
      }

      .area-name-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
      }

      .area-icon {
        --mdc-icon-size: 20px;
        color: var(--primary-color);
      }

      .area-info h3 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
      }

      .entity-counts {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 10px;
      }

      .entity-count-chip {
        display: flex;
        align-items: center;
        gap: 4px;
        background: var(--secondary-background-color);
        border-radius: 20px;
        padding: 3px 8px;
        font-size: 0.8rem;
      }

      .entity-count-chip ha-icon {
        --mdc-icon-size: 14px;
        color: var(--secondary-text-color);
      }

      .area-stats {
        display: flex;
        gap: 8px;
      }

      .stat-badge {
        font-size: 0.75rem;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 500;
      }

      .stat-badge.relevant {
        background: #e8f5e9;
        color: #2e7d32;
      }

      .stat-badge.hidden-badge {
        background: var(--secondary-background-color);
        color: var(--secondary-text-color);
      }

      /* Entity List */
      .entity-details summary {
        cursor: pointer;
        padding: 10px 16px;
        background: var(--secondary-background-color);
        font-size: 0.85rem;
        color: var(--secondary-text-color);
        list-style: none;
        border-top: 1px solid var(--divider-color);
      }

      .entity-list {
        padding: 8px 16px;
        max-height: 280px;
        overflow-y: auto;
      }

      .entity-item {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 0;
        border-bottom: 1px solid var(--divider-color);
        font-size: 0.85rem;
      }

      .entity-item ha-icon {
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
        flex-shrink: 0;
      }

      .entity-info {
        flex: 1;
        min-width: 0;
      }

      .entity-name {
        display: block;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .entity-id {
        display: block;
        font-size: 0.75rem;
        color: var(--secondary-text-color);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .entity-state {
        font-size: 0.75rem;
        padding: 2px 6px;
        border-radius: 8px;
        flex-shrink: 0;
      }

      .state-on {
        background: #fff9c4;
        color: #f57f17;
      }

      .state-off {
        background: var(--secondary-background-color);
        color: var(--secondary-text-color);
      }

      .state-other {
        background: #e3f2fd;
        color: #1565c0;
      }

      .hidden-entities-label {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 0;
        font-size: 0.8rem;
        color: var(--secondary-text-color);
      }

      .more-items {
        font-size: 0.8rem;
        color: var(--secondary-text-color);
        text-align: center;
        padding: 8px;
      }

      /* Settings */
      .form-group {
        margin-bottom: 16px;
      }

      .form-group label {
        display: block;
        font-size: 0.875rem;
        font-weight: 500;
        margin-bottom: 6px;
        color: var(--secondary-text-color);
      }

      .form-control {
        width: 100%;
        padding: 10px 12px;
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 0.9rem;
        box-sizing: border-box;
        transition: border-color 0.2s;
      }

      .form-control:focus {
        outline: none;
        border-color: var(--primary-color, #03a9f4);
      }

      .form-group small {
        display: block;
        margin-top: 4px;
        font-size: 0.75rem;
        color: var(--secondary-text-color);
      }

      .checkbox-group label {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        font-weight: 400;
        color: var(--primary-text-color);
      }

      .divider {
        border: none;
        border-top: 1px solid var(--divider-color);
        margin: 20px 0;
      }

      /* Info List */
      .info-list, .install-steps {
        padding-left: 0;
        list-style: none;
        margin: 0;
      }

      .info-list li, .install-steps li {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 8px 0;
        border-bottom: 1px solid var(--divider-color);
        font-size: 0.9rem;
        line-height: 1.5;
      }

      .install-steps li {
        counter-increment: step-counter;
        padding: 10px 0;
      }

      .info-list li ha-icon {
        --mdc-icon-size: 20px;
        color: var(--primary-color);
        flex-shrink: 0;
        margin-top: 2px;
      }

      .info-list a {
        color: var(--primary-color);
      }

      /* Architecture diagram */
      .architecture-desc {
        color: var(--secondary-text-color);
        margin: 0 0 16px;
        font-size: 0.9rem;
      }

      .architecture-diagram {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
      }

      .arch-main {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 4px;
        background: var(--primary-color);
        color: #fff;
        border-radius: 12px;
        padding: 12px 24px;
        min-width: 180px;
      }

      .arch-main ha-icon {
        --mdc-icon-size: 28px;
      }

      .arch-label {
        font-weight: 600;
        font-size: 1rem;
      }

      .arch-sub {
        font-size: 0.75rem;
        opacity: 0.85;
      }

      .arch-arrow-down {
        display: flex;
        flex-direction: column;
        align-items: center;
        color: var(--secondary-text-color);
        font-size: 0.8rem;
        gap: 2px;
      }

      .arch-arrow-down ha-icon {
        --mdc-icon-size: 22px;
      }

      .arch-rooms {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: center;
        width: 100%;
      }

      .arch-room {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 4px;
        background: var(--secondary-background-color, #f5f5f5);
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 10px;
        padding: 10px 16px;
        font-size: 0.82rem;
        color: var(--primary-text-color);
        min-width: 90px;
      }

      .arch-room ha-icon {
        --mdc-icon-size: 20px;
        color: var(--primary-color);
      }

      .arch-room-placeholder {
        opacity: 0.4;
        border-style: dashed;
      }

      .arch-room-more {
        align-self: center;
        background: none;
        border: none;
        color: var(--secondary-text-color);
        font-size: 0.85rem;
      }

      /* Dashboard links */
      .dashboard-links {
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px solid var(--divider-color, #e0e0e0);
      }

      .dashboard-links p {
        margin: 0 0 8px;
        font-size: 0.9rem;
        color: var(--primary-text-color);
      }

      .link-list {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .dash-link {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        background: var(--secondary-background-color, #f5f5f5);
        border-radius: 8px;
        text-decoration: none;
        color: var(--primary-text-color);
        font-size: 0.88rem;
        transition: background 0.15s;
      }

      .dash-link:hover {
        background: var(--primary-color);
        color: #fff;
      }

      .dash-link:hover ha-icon {
        color: #fff;
      }

      .dash-link span {
        flex: 1;
      }

      .dash-link em {
        font-style: normal;
        opacity: 0.6;
        font-size: 0.78rem;
        margin-left: 6px;
      }

      .dash-link-room {
        margin-left: 20px;
        font-size: 0.84rem;
      }

      .more-links {
        color: var(--secondary-text-color);
        font-size: 0.82rem;
        margin: 4px 0 0 20px;
      }

      /* Secondary button row */
      .button-row-secondary {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid var(--divider-color, #e0e0e0);
        flex-wrap: wrap;
      }

      /* Unassigned Card */
      .unassigned-card p {
        color: var(--secondary-text-color);
        margin: 0 0 12px;
        font-size: 0.9rem;
      }

      /* Loading */
      .loading {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 80px 20px;
        color: var(--secondary-text-color);
        gap: 16px;
      }

      /* Responsive */
      @media (max-width: 600px) {
        .status-grid {
          grid-template-columns: repeat(2, 1fr);
        }

        .tabs {
          flex-direction: column;
        }

        .generate-steps {
          flex-direction: column;
          align-items: flex-start;
          gap: 8px;
        }

        .step-divider {
          width: 2px;
          height: 20px;
          margin: 0 22px;
        }

        .rooms-grid {
          grid-template-columns: 1fr;
        }
      }

      /* ========================= KI-ASSISTENT CHAT ========================= */

      .tab-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 18px;
        height: 18px;
        background: var(--error-color, #f44336);
        color: white;
        border-radius: 9px;
        font-size: 0.7rem;
        font-weight: 700;
        padding: 0 4px;
        margin-left: 4px;
      }

      .link-btn {
        background: none;
        border: none;
        color: var(--primary-color);
        cursor: pointer;
        padding: 0;
        font-size: inherit;
        text-decoration: underline;
      }

      .chat-container {
        display: flex;
        flex-direction: column;
        height: calc(100vh - 320px);
        min-height: 420px;
        max-height: 720px;
        padding: 0;
        overflow: hidden;
      }

      .chat-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 18px;
        border-bottom: 1px solid var(--divider-color);
        background: var(--secondary-background-color);
        flex-shrink: 0;
      }

      .chat-header-left {
        display: flex;
        align-items: center;
        gap: 12px;
      }

      .chat-bot-icon {
        --mdc-icon-size: 32px;
        color: var(--primary-color);
      }

      .chat-provider-badge {
        display: inline-block;
        font-size: 0.7rem;
        padding: 1px 6px;
        background: var(--primary-color, #03a9f4);
        color: white;
        border-radius: 10px;
        margin-left: 6px;
        vertical-align: middle;
      }

      .chat-header-actions {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .auto-execute-toggle {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.82rem;
        cursor: pointer;
        user-select: none;
        color: var(--secondary-text-color);
      }

      .btn-sm {
        padding: 6px 10px;
        font-size: 0.8rem;
      }

      .chat-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        scroll-behavior: smooth;
      }

      .chat-welcome {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: 32px 16px;
        color: var(--secondary-text-color);
        gap: 8px;
      }

      .chat-welcome ha-icon {
        --mdc-icon-size: 56px;
        color: var(--primary-color);
        opacity: 0.6;
      }

      .chat-welcome h3 {
        margin: 0;
        color: var(--primary-text-color);
        font-size: 1.1rem;
      }

      .chat-welcome p {
        margin: 0;
        font-size: 0.9rem;
      }

      .suggestion-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: center;
        margin-top: 16px;
      }

      .suggestion-chip {
        background: var(--secondary-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 20px;
        padding: 6px 14px;
        font-size: 0.82rem;
        cursor: pointer;
        color: var(--primary-text-color);
        transition: background 0.15s, border-color 0.15s;
      }

      .suggestion-chip:hover {
        background: var(--primary-color, #03a9f4);
        border-color: var(--primary-color, #03a9f4);
        color: white;
      }

      .chat-message {
        display: flex;
        gap: 10px;
        align-items: flex-start;
      }

      .chat-message.user {
        flex-direction: row-reverse;
      }

      .msg-avatar {
        width: 34px;
        height: 34px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }

      .bot-avatar {
        background: var(--primary-color, #03a9f4);
        color: white;
      }

      .user-avatar {
        background: var(--secondary-background-color);
        color: var(--secondary-text-color);
        border: 1px solid var(--divider-color);
      }

      .error-avatar {
        background: var(--error-color, #f44336);
        color: white;
      }

      .msg-avatar ha-icon {
        --mdc-icon-size: 20px;
      }

      .msg-body {
        display: flex;
        flex-direction: column;
        max-width: 75%;
      }

      .chat-message.user .msg-body {
        align-items: flex-end;
      }

      .msg-bubble {
        padding: 10px 14px;
        border-radius: 14px;
        font-size: 0.9rem;
        line-height: 1.5;
        word-break: break-word;
      }

      .user-bubble {
        background: var(--primary-color, #03a9f4);
        color: white;
        border-bottom-right-radius: 4px;
      }

      .bot-bubble {
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        border-bottom-left-radius: 4px;
        border: 1px solid var(--divider-color);
      }

      .error-bubble {
        background: #ffebee;
        color: #c62828;
        border: 1px solid #ef9a9a;
        border-bottom-left-radius: 4px;
      }

      .msg-time {
        font-size: 0.7rem;
        color: var(--secondary-text-color);
        margin-top: 3px;
        padding: 0 2px;
      }

      /* Typing indicator */
      .typing-indicator {
        display: flex;
        align-items: center;
        gap: 5px;
        padding: 12px 16px;
      }

      .typing-indicator span {
        width: 8px;
        height: 8px;
        background: var(--secondary-text-color);
        border-radius: 50%;
        display: inline-block;
        animation: typing-bounce 1.3s ease-in-out infinite;
      }

      .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
      .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

      @keyframes typing-bounce {
        0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
        30% { transform: translateY(-6px); opacity: 1; }
      }

      /* Executed actions */
      .executed-actions {
        margin-top: 6px;
        display: flex;
        flex-direction: column;
        gap: 3px;
      }

      .executed-action {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.8rem;
        padding: 3px 0;
      }

      .executed-action.ok {
        color: #2e7d32;
      }

      .executed-action.fail {
        color: #c62828;
      }

      .executed-action ha-icon {
        --mdc-icon-size: 16px;
        flex-shrink: 0;
      }

      /* Pending actions */
      .pending-actions-panel {
        border-top: 2px solid var(--warning-color, #ff9800);
        background: #fff8e1;
        padding: 14px 18px;
        flex-shrink: 0;
      }

      .pending-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
        color: #e65100;
        font-size: 0.9rem;
      }

      .pending-header ha-icon {
        --mdc-icon-size: 20px;
        color: var(--warning-color, #ff9800);
      }

      .pending-list {
        list-style: none;
        padding: 0;
        margin: 0 0 12px;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .pending-item {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        font-size: 0.85rem;
        padding: 5px 8px;
        background: white;
        border-radius: 6px;
        border: 1px solid #ffe082;
      }

      .pending-item.destructive {
        border-color: #ffab91;
        background: #fff3e0;
      }

      .pending-item ha-icon {
        --mdc-icon-size: 16px;
        color: var(--warning-color, #ff9800);
        flex-shrink: 0;
        margin-top: 1px;
      }

      .pending-buttons {
        display: flex;
        gap: 10px;
      }

      /* Chat input */
      .chat-input-area {
        display: flex;
        align-items: flex-end;
        gap: 8px;
        padding: 12px 16px;
        border-top: 1px solid var(--divider-color);
        background: var(--card-background-color, #fff);
        flex-shrink: 0;
      }

      .chat-input {
        flex: 1;
        resize: none;
        border: 1px solid var(--divider-color);
        border-radius: 12px;
        padding: 10px 14px;
        font-size: 0.9rem;
        font-family: inherit;
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        line-height: 1.4;
        transition: border-color 0.2s;
      }

      .chat-input:focus {
        outline: none;
        border-color: var(--primary-color, #03a9f4);
      }

      .chat-input:disabled {
        opacity: 0.5;
      }

      .chat-send-btn {
        width: 42px;
        height: 42px;
        border-radius: 50%;
        border: none;
        background: var(--primary-color, #03a9f4);
        color: white;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s, transform 0.1s;
        flex-shrink: 0;
      }

      .chat-send-btn:hover:not(:disabled) {
        background: var(--dark-primary-color, #0288d1);
        transform: scale(1.05);
      }

      .chat-send-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }

      .chat-send-btn ha-icon {
        --mdc-icon-size: 20px;
      }

      .info-card {
        margin-top: 16px;
      }
    `;
  }
}

customElements.define("ai-dashboard-panel", AIDashboardPanel);

})(); // end async IIFE
