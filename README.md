##### DRONACHARYA #####

Agricultural Intelligence and Farmer Services Assistance

DRONACHARYA is a Flask-based agricultural intelligence prototype that brings together dataset analysis, illustrative yield estimation, field-visit requests, marketplace services, climate data adapters, and a browser-based field assistant in one web application.

The project is intentionally designed as a prototype. It demonstrates the frontend-to-backend flow, persistence, validation, recommendation generation, and service integration patterns required for a larger agricultural platform. It is not an official agricultural advisory system, identity-verification service, financial marketplace, or production-ready machine-learning platform.


# Features:

Prototype login
Creates or retrieves a local development user using Aadhaar and phone-number fields.
Implemented for local demonstration; not official authentication.

CSV upload
Accepts a CSV file, detects numeric columns, reports missing values, and calculates a quality score.
Implemented.

Dataset prediction
Produces a transparent trend-baseline prediction and basic correlation factors.
Implemented as a demonstration model.

Analysis dashboard
Loads a saved analysis using its database ID.
Implemented.

Yield estimator
Computes an illustrative crop-yield estimate using crop, soil, irrigation, pH, area, and optional weather data.
Implemented through the Flask API.

Yield history
Stores and retrieves the current visitor’s or signed-in user’s yield reports.
Implemented.

Field visits
Submits a field-visit request and stores its request code and payload in SQLite.
Implemented in the latest prototype state.

Store interface
Provides the frontend marketplace interface and JavaScript controller.
Frontend present; marketplace API must be added before the store is fully operational.

Assistant page
Provides the prototype assistant interface and links to application services.
Page present; responses are currently prototype-level.


# Technology stack used

The prototype uses Flask for server-side routing, Jinja templates for page rendering, vanilla JavaScript for browser interactions, SQLite for local persistence, and the Python requests package for selected external data requests.


Python 3.10+ and Flask 3.x

HTML, CSS, Jinja templates, and vanilla JavaScript

SQLite 3

External weather data:
Open-Meteo geocoding, forecast, and archive endpoints
Browser speech:
Web Speech API / SpeechSynthesisUtterance

Dependencies:
Flask and requests





# Architecture

The application uses a single Flask process and a local SQLite database. Jinja renders HTML templates on the server. Browser-side JavaScript submits forms and JSON requests to Flask endpoints. Flask validates the request, runs the relevant application logic, and returns either an HTML page or a JSON response.



Browser
  │
  ├── Jinja-rendered pages in templates/
  ├── CSS in static/css/
  └── JavaScript controllers in static/js/
          │
          ▼
Flask application: app.py
  │
  ├── Authentication and sessions
  ├── CSV upload and analysis
  ├── Analysis dashboard
  ├── Field-visit API
  ├── Yield blueprint: yield_backend.py
  └── Marketplace blueprint: marketplace_backend.py
          │
          ▼
SQLite database: database/dronacharya.db



The yield blueprint can also request public geocoding and rainfall data from Open-Meteo. If those requests fail, the estimator falls back to a local calculation without live rainfall data.


# Repository structure:


DRONACHARYA-main/
├── app.py                         # Main Flask application and page/API routes
├── database.py                    # Shared SQLite connection, users, and analyses
├── data_cleaner.py                # CSV validation and quality analysis
├── predictor.py                   # Transparent trend-baseline prediction
├── recommender.py                 # Prototype recommendation cards
├── yield_backend.py               # Yield blueprint, calculation engine, history, CSV export
├── marketplace_backend.py         # Product and order marketplace blueprint
├── climate_backend.py             # Optional climate, market, news, and watchlist blueprint
├── api.js                         # Shared API helper kept in the project root
├── database/
│   ├── sqlite_schema.sql          # Main SQLite schema
│   └── postgres_schema.sql        # Reference PostgreSQL schema
├── templates/
│   ├── index.html                 # Protected home/dashboard landing page
│   ├── login.html                 # Prototype login form
│   ├── dashboard.html             # Uploaded dataset analysis result
│   ├── estimate_yield.html        # Connected yield estimator
│   ├── yield.html                 # Legacy yield page retained for compatibility
│   ├── field_visit.html            # Field-visit request form
│   ├── store.html                 # Marketplace interface
│   ├── climate.html               # Climate/market/news interface
│   └── assistant.html             # Voice-enabled field assistant
├── static/
│   ├── css/style.css              # Shared stylesheet
│   └── js/
│       ├── app.js                 # CSV upload controller
│       ├── login.js               # Login controller
│       └── store.js               # Marketplace controller
├── uploads/.gitkeep               # Runtime upload directory placeholder
├── requirements.txt               # Python dependencies
├── test_integration.py            # Main end-to-end smoke test
└── test_climate_backend.py        # Climate blueprint tests



