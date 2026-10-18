"""Interactive API documentation page served at GET /docs (public, read-only).

Swagger UI renders two OpenAPI documents, selectable from the top bar:
  * the pod contract v1.0           -> /openapi.yaml
  * the course testing endpoints    -> /openapi/system-test-interface.yaml
Requests made from the page go to this same server and still need the API key:
click "Authorize" and paste it. The key is kept only in the page's memory
(persistAuthorization is off), so it is gone when the tab closes.

Swagger UI is loaded from jsDelivr at a pinned version with Subresource Integrity
hashes, so the browser refuses a modified copy.
"""

from __future__ import annotations

SWAGGER_VERSION = "5.32.15"
_CDN = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_VERSION}"
_SRI = {
    "css": "sha384-fgyWYkUAamzuI8mJFu/xpRP0JWCJRwkwUwsYDoOYVHUJ8NQE5cENn8ib3ppwFFSX",
    "bundle": "sha384-m7zaGj7MPzU+G4lz2eyy73GxK9bbRDr9bB2CSdj8wodg2wu/Wnt6wsoLP3JD+RS9",
    "preset": "sha384-9rDX8vR4ir9/JIiV/XvxMpb5T9tVyFbssk49PV935hrdwmkVNJ7VZMM0RXAm184h",
}

DOCS_HTML = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>IncidentClock API</title>
  <link rel="stylesheet" href="{_CDN}/swagger-ui.css" integrity="{_SRI["css"]}" crossorigin="anonymous">
  <style>
    body {{ margin: 0; background: #fff; }}
    .ic-note {{ font: 14px/1.5 system-ui, sans-serif; padding: 10px 20px; background: #f4f6fb;
               border-bottom: 1px solid #dde2ee; color: #24324a; }}
    .ic-note code {{ background: #e7ebf5; padding: 1px 4px; border-radius: 3px; }}
  </style>
</head>
<body>
  <div class="ic-note">
    <strong>IncidentClock</strong> &middot; pod contract v1.0. Every endpoint except
    <code>/health</code> needs the API key: click <strong>Authorize</strong>, paste it into
    <code>X-API-Key</code>, then use <strong>Try it out</strong>. Switch between the pod contract and
    the course testing endpoints with the selector at the top right.
    Operations planned for Phases 4&ndash;5 answer <code>501 NOT_IMPLEMENTED</code>.
  </div>
  <div id="swagger-ui"></div>
  <script src="{_CDN}/swagger-ui-bundle.js" integrity="{_SRI["bundle"]}" crossorigin="anonymous"></script>
  <script src="{_CDN}/swagger-ui-standalone-preset.js" integrity="{_SRI["preset"]}"
          crossorigin="anonymous"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      urls: [
        {{ url: "/openapi.yaml", name: "Pod contract v1.0 (project API)" }},
        {{ url: "/openapi/system-test-interface.yaml", name: "Course testing endpoints (/test/*)" }}
      ],
      "urls.primaryName": "Pod contract v1.0 (project API)",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
      layout: "StandaloneLayout",
      persistAuthorization: false,
      tryItOutEnabled: false,
      displayRequestDuration: true
    }});
  </script>
</body>
</html>
"""
