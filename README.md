DRONACHARYA

Agricultural Intelligence and Farmer Services Prototype

DRONACHARYA is a beginner-friendly agricultural intelligence prototype that combines a Flask backend, SQLite persistence, server-rendered Jinja templates, and vanilla JavaScript frontend controllers. It is designed to demonstrate how farmers could receive basic data analysis, yield estimates, field-visit assistance, and marketplace services from one web application.


Features:

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




Architecture

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