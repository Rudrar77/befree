"""OpenAPI 3.0 documentation and Swagger UI at /docs matching Appendix A."""

from __future__ import annotations

import json
from flask import Response, jsonify, render_template_string
from app.api import api_bp

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Bank Statement Processing & Classification API",
        "version": "1.0.0",
        "description": "Standard REST API for statement upload, OCR/text extraction, transaction classification, reconciliation, and export.",
    },
    "paths": {
        "/api/health": {
            "get": {
                "summary": "Health check",
                "responses": {"200": {"description": "Service is healthy"}},
            }
        },
        "/api/statements/upload": {
            "post": {
                "summary": "Upload bank statement PDFs or images (PDF, JPG, JPEG, PNG)",
                "requestBody": {
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "files": {
                                        "type": "array",
                                        "items": {"type": "string", "format": "binary"},
                                    }
                                },
                                "required": ["files"],
                            }
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Upload batch processed"},
                    "413": {"description": "File too large"},
                    "415": {"description": "Invalid file type"},
                },
            }
        },
        "/api/statements": {
            "get": {
                "summary": "List paginated statements",
                "parameters": [
                    {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}},
                    {"name": "page_size", "in": "query", "schema": {"type": "integer", "default": 50}},
                    {"name": "processing_status", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "Paginated statements"}},
            }
        },
        "/api/statements/{id}": {
            "get": {
                "summary": "Get statement by ID",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "Statement details"}, "404": {"description": "Not found"}},
            },
            "delete": {
                "summary": "Delete statement and stored file",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"204": {"description": "Deleted"}, "404": {"description": "Not found"}},
            },
        },
        "/api/statements/{id}/process": {
            "post": {
                "summary": "Enqueue background processing for statement",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"202": {"description": "Processing queued"}, "409": {"description": "Already processing"}},
            }
        },
        "/api/statements/{id}/status": {
            "get": {
                "summary": "Get processing status and progress",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "Current processing status"}},
            }
        },
        "/api/statements/{id}/transactions": {
            "get": {
                "summary": "List transactions for statement",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "Paginated transactions"}},
            }
        },
        "/api/statements/{id}/unresolved": {
            "get": {
                "summary": "List unresolved rows for statement",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "List of unresolved rows"}},
            }
        },
        "/api/transactions": {
            "get": {
                "summary": "List transactions across all statements",
                "responses": {"200": {"description": "Paginated transactions"}},
            }
        },
        "/api/transactions/{id}": {
            "get": {
                "summary": "Get single transaction",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "Transaction detail"}},
            },
            "patch": {
                "summary": "Update transaction category, review status, or notes",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "category_id": {"type": "string", "format": "uuid"},
                                    "needs_review": {"type": "boolean"},
                                    "notes": {"type": "string"},
                                },
                            }
                        }
                    }
                },
                "responses": {"200": {"description": "Updated transaction"}},
            },
        },
        "/api/classification/classify": {
            "post": {
                "summary": "Classify transactions for a statement",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["statement_id"],
                                "properties": {"statement_id": {"type": "string", "format": "uuid"}, "force": {"type": "boolean", "default": False}},
                            }
                        }
                    }
                },
                "responses": {"200": {"description": "Classification result summary"}},
            }
        },
        "/api/classify": {
            "post": {
                "summary": "Classify one transaction using rules first and ML only as fallback",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["description"],
                                "properties": {
                                    "description": {"type": "string"},
                                    "date": {"type": "string"},
                                    "debit": {"type": "string"},
                                    "credit": {"type": "string"},
                                    "balance": {"type": "string"},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {"description": "Rule or fallback ML category, method, confidence, and review status"},
                    "422": {"description": "Invalid description"},
                },
            }
        },
        "/api/classify/bulk": {
            "post": {
                "summary": "Classify up to 500 transactions using rules first and ML only as fallback",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["transactions"],
                                "properties": {
                                    "transactions": {
                                        "type": "array",
                                        "items": {"type": "object"},
                                    }
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {"description": "Batch rule or fallback ML results with classification method"},
                    "422": {"description": "Invalid batch"},
                },
            }
        },
        "/api/classify/categories": {
            "get": {
                "summary": "List the model's exact 20 category labels",
                "responses": {"200": {"description": "Supported model categories"}},
            }
        },
        "/api/classify/status": {
            "get": {
                "summary": "Get pretrained model availability and loading status",
                "responses": {"200": {"description": "Classifier status"}},
            }
        },
        "/api/categories": {
            "get": {"summary": "List all categories", "responses": {"200": {"description": "List of categories"}}},
            "post": {
                "summary": "Create category",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {"name": {"type": "string"}, "is_transfer": {"type": "boolean"}, "color": {"type": "string"}},
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "Category created"}, "409": {"description": "Duplicate name"}},
            },
        },
        "/api/categories/{id}": {
            "patch": {
                "summary": "Update category",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "Updated category"}},
            }
        },
        "/api/categories/rules": {
            "get": {"summary": "List classification rules", "responses": {"200": {"description": "List of rules"}}},
            "post": {
                "summary": "Create classification rule",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["category_id", "keyword"],
                                "properties": {
                                    "category_id": {"type": "string", "format": "uuid"},
                                    "keyword": {"type": "string"},
                                    "match_type": {"type": "string", "enum": ["exact", "partial", "regex"]},
                                    "priority": {"type": "integer"},
                                },
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "Rule created"}},
            },
        },
        "/api/categories/rules/{rule_id}": {
            "patch": {
                "summary": "Update classification rule",
                "parameters": [{"name": "rule_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "Updated rule"}},
            },
            "delete": {
                "summary": "Delete user-defined rule",
                "parameters": [{"name": "rule_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"204": {"description": "Rule deleted"}},
            },
        },
        "/api/validation/{statement_id}": {
            "get": {
                "summary": "Get validation and reconciliation report",
                "parameters": [{"name": "statement_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "ValidationReport"}},
            }
        },
        "/api/validation/{statement_id}/recheck": {
            "post": {
                "summary": "Re-run validation checks",
                "parameters": [{"name": "statement_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "Updated ValidationReport"}},
            }
        },
        "/api/analytics": {
            "get": {
                "summary": "Global analytics",
                "responses": {"200": {"description": "Aggregated analytics"}},
            }
        },
        "/api/analytics/{statement_id}": {
            "get": {
                "summary": "Statement-specific analytics",
                "parameters": [{"name": "statement_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"200": {"description": "Statement analytics"}},
            }
        },
        "/api/export/{statement_id}": {
            "get": {
                "summary": "Export statement transactions",
                "parameters": [
                    {"name": "statement_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                    {"name": "format", "in": "query", "required": True, "schema": {"type": "string", "enum": ["xlsx", "csv"]}},
                ],
                "responses": {"200": {"description": "File attachment stream"}},
            }
        },
    },
}

SWAGGER_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>API Documentation - Swagger UI</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.18.2/swagger-ui.css">
  <link rel="icon" type="image/png" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.18.2/favicon-32x32.png">
  <style>
    body { margin: 0; background: #fafafa; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.18.2/swagger-ui-bundle.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.18.2/swagger-ui-standalone-preset.js"></script>
  <script>
    window.onload = function() {
      SwaggerUIBundle({
        url: "/api/openapi.json",
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        layout: "StandaloneLayout"
      });
    };
  </script>
</body>
</html>
"""


@api_bp.route("/openapi.json", methods=["GET"])
def get_openapi_spec() -> Response:
    """Return OpenAPI 3.0 specification in JSON format."""
    return jsonify(OPENAPI_SPEC)
