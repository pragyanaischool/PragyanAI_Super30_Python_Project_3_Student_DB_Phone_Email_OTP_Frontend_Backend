/**
 * Frontend Runtime Configuration & Environment Resolver
 * Dynamically switches between local development and your deployed Render backend.
 */
const CONFIG = {
  API_BASE_URL: (() => {
    const isLocalhost = Boolean(
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1" ||
      window.location.hostname === "[::1]" ||
      window.location.protocol === "file:"
    );

    // Local development endpoint (no trailing /api)
    if (isLocalhost) {
      return "http://127.0.0.1:8000";
    }

    // Live Render production backend URL (no trailing /api)
    return "https://https-gipragyanai-super30-python-project.onrender.com";
  })()
};

// Freeze the object to prevent accidental runtime modifications
Object.freeze(CONFIG);

// Export for module systems while keeping global access for standard scripts
if (typeof module !== "undefined" && module.exports) {
  module.exports = CONFIG;
}

