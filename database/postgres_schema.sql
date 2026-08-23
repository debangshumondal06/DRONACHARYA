-- DRONACHARYA database schema
-- PostgreSQL 15+
--
-- This schema stores data from the login, estimated-yield, and farmer-marketplace pages.
-- Never store raw Aadhaar or PAN values. The application must normalize and hash them
-- server-side with a slow password-hashing algorithm such as Argon2id or bcrypt before
-- writing identity_hash values below.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE account_role AS ENUM ('buyer', 'seller', 'both', 'admin');
CREATE TYPE account_status AS ENUM ('pending', 'active', 'suspended', 'deleted');
CREATE TYPE area_unit AS ENUM ('acres', 'hectares');
CREATE TYPE map_source AS ENUM ('OpenStreetMap', 'Live street-map connector', 'Manual state profile');
CREATE TYPE listing_status AS ENUM ('draft', 'published', 'paused', 'sold_out', 'archived');
CREATE TYPE order_status AS ENUM ('pending', 'confirmed', 'packed', 'shipped', 'delivered', 'cancelled');
CREATE TYPE payment_status AS ENUM ('unpaid', 'authorized', 'paid', 'failed', 'refunded');

-- Login / workspace identity
CREATE TABLE user_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role account_role NOT NULL DEFAULT 'both',
  status account_status NOT NULL DEFAULT 'pending',
  email TEXT,
  email_normalized TEXT GENERATED ALWAYS AS (lower(trim(email))) STORED,
  email_verified_at TIMESTAMPTZ,
  password_hash TEXT,
  aadhaar_hash TEXT,
  pan_hash TEXT,
  identity_hash_algorithm TEXT NOT NULL DEFAULT 'argon2id',
  prototype_consent BOOLEAN NOT NULL DEFAULT FALSE,
  prototype_consent_at TIMESTAMPTZ,
  display_name TEXT,
  phone_e164 TEXT,
  preferred_language TEXT NOT NULL DEFAULT 'English',
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CHECK (email IS NULL OR length(trim(email)) BETWEEN 3 AND 320),
  CHECK (prototype_consent_at IS NULL OR prototype_consent = TRUE),
  CHECK (status <> 'active' OR prototype_consent = TRUE),
  CHECK (aadhaar_hash IS NULL OR length(aadhaar_hash) >= 32),
  CHECK (pan_hash IS NULL OR length(pan_hash) >= 32)
);

CREATE UNIQUE INDEX user_accounts_email_uq
  ON user_accounts (email_normalized)
  WHERE email_normalized IS NOT NULL AND deleted_at IS NULL;
CREATE UNIQUE INDEX user_accounts_aadhaar_hash_uq
  ON user_accounts (aadhaar_hash)
  WHERE aadhaar_hash IS NOT NULL AND deleted_at IS NULL;
CREATE UNIQUE INDEX user_accounts_pan_hash_uq
  ON user_accounts (pan_hash)
  WHERE pan_hash IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX user_accounts_role_status_idx ON user_accounts (role, status);

-- Optional farmer/buyer profile fields shared by marketplace and farm pages
CREATE TABLE user_profiles (
  user_id UUID PRIMARY KEY REFERENCES user_accounts(id) ON DELETE CASCADE,
  legal_name TEXT,
  farm_name TEXT,
  state TEXT,
  district TEXT,
  village TEXT,
  postal_code TEXT,
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  profile_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
  CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

-- State-level benchmark context used by the estimator. Keep benchmark source URLs
-- and retrieval dates so report provenance is auditable.
CREATE TABLE state_benchmarks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  state_name TEXT NOT NULL UNIQUE,
  soil_profile TEXT NOT NULL,
  weather_profile TEXT NOT NULL,
  seasonal_rainfall_mm NUMERIC(8,2),
  soil_score NUMERIC(5,2) NOT NULL CHECK (soil_score BETWEEN 0 AND 100),
  weather_score NUMERIC(5,2) NOT NULL CHECK (weather_score BETWEEN 0 AND 100),
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  source_name TEXT,
  source_url TEXT,
  source_retrieved_at TIMESTAMPTZ,
  source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX state_benchmarks_active_state_idx ON state_benchmarks (active, state_name);

-- A saved field profile captures the controls from the yield-estimation page.
CREATE TABLE farm_fields (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  field_name TEXT NOT NULL,
  state_benchmark_id UUID REFERENCES state_benchmarks(id) ON DELETE SET NULL,
  state_name TEXT NOT NULL,
  crop_name TEXT NOT NULL,
  season_cycle TEXT NOT NULL,
  area_value NUMERIC(12,4) NOT NULL CHECK (area_value > 0),
  area_unit area_unit NOT NULL DEFAULT 'acres',
  soil_ph NUMERIC(4,2) NOT NULL CHECK (soil_ph BETWEEN 0 AND 14),
  organic_carbon_percent NUMERIC(5,3) CHECK (organic_carbon_percent >= 0),
  irrigation_access TEXT NOT NULL,
  farmer_education_level TEXT NOT NULL,
  seed_variety_class TEXT NOT NULL,
  map_source map_source NOT NULL DEFAULT 'OpenStreetMap',
  map_latitude NUMERIC(9,6),
  map_longitude NUMERIC(9,6),
  external_map_reference TEXT,
  soil_report_uri TEXT,
  field_boundary_geojson JSONB,
  custom_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (map_latitude IS NULL OR map_latitude BETWEEN -90 AND 90),
  CHECK (map_longitude IS NULL OR map_longitude BETWEEN -180 AND 180)
);
CREATE INDEX farm_fields_owner_idx ON farm_fields (owner_user_id, updated_at DESC);
CREATE INDEX farm_fields_state_crop_idx ON farm_fields (state_name, crop_name);

-- Each generation from the estimator is kept as an immutable report snapshot.
CREATE TABLE yield_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  field_id UUID NOT NULL REFERENCES farm_fields(id) ON DELETE CASCADE,
  generated_by_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE RESTRICT,
  model_version TEXT NOT NULL DEFAULT '2.6',
  baseline_yield_tonnes_per_acre NUMERIC(12,4) NOT NULL CHECK (baseline_yield_tonnes_per_acre >= 0),
  soil_factor NUMERIC(8,5) NOT NULL CHECK (soil_factor >= 0),
  water_factor NUMERIC(8,5) NOT NULL CHECK (water_factor >= 0),
  practice_factor NUMERIC(8,5) NOT NULL CHECK (practice_factor >= 0),
  seed_factor NUMERIC(8,5) NOT NULL CHECK (seed_factor >= 0),
  weather_factor NUMERIC(8,5) NOT NULL CHECK (weather_factor >= 0),
  estimated_yield_tonnes_per_acre NUMERIC(12,4) NOT NULL CHECK (estimated_yield_tonnes_per_acre >= 0),
  estimated_total_tonnes NUMERIC(14,4) NOT NULL CHECK (estimated_total_tonnes >= 0),
  model_confidence_percent NUMERIC(5,2) NOT NULL CHECK (model_confidence_percent BETWEEN 0 AND 100),
  water_requirement_mm NUMERIC(10,2) NOT NULL CHECK (water_requirement_mm >= 0),
  progression_sowing_tonnes NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (progression_sowing_tonnes >= 0),
  progression_tillering_tonnes NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (progression_tillering_tonnes >= 0),
  progression_flowering_tonnes NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (progression_flowering_tonnes >= 0),
  progression_harvest_tonnes NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (progression_harvest_tonnes >= 0),
  assumptions JSONB NOT NULL DEFAULT '{}'::jsonb,
  benchmark_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX yield_reports_field_generated_idx ON yield_reports (field_id, generated_at DESC);
CREATE INDEX yield_reports_user_generated_idx ON yield_reports (generated_by_user_id, generated_at DESC);

-- Government/public data provenance attached to a report or benchmark refresh.
CREATE TABLE data_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name TEXT NOT NULL,
  source_url TEXT NOT NULL,
  dataset_name TEXT,
  agency_name TEXT,
  retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  checksum TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_name, source_url, dataset_name)
);
CREATE TABLE yield_report_sources (
  yield_report_id UUID NOT NULL REFERENCES yield_reports(id) ON DELETE CASCADE,
  data_source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE RESTRICT,
  contribution_note TEXT,
  PRIMARY KEY (yield_report_id, data_source_id)
);

-- Farmer marketplace listings.
CREATE TABLE marketplace_listings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  seller_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE RESTRICT,
  title TEXT NOT NULL,
  description TEXT,
  category TEXT NOT NULL,
  crop_name TEXT NOT NULL,
  variety_name TEXT,
  quantity NUMERIC(14,3) NOT NULL CHECK (quantity > 0),
  quantity_unit TEXT NOT NULL DEFAULT 'kg',
  available_quantity NUMERIC(14,3) NOT NULL CHECK (available_quantity >= 0),
  price_per_unit NUMERIC(14,2) NOT NULL CHECK (price_per_unit >= 0),
  currency_code CHAR(3) NOT NULL DEFAULT 'INR',
  state TEXT,
  district TEXT,
  village TEXT,
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  harvest_date DATE,
  status listing_status NOT NULL DEFAULT 'draft',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (available_quantity <= quantity),
  CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
  CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);
CREATE INDEX marketplace_listings_browse_idx ON marketplace_listings (status, category, crop_name, updated_at DESC);
CREATE INDEX marketplace_listings_seller_idx ON marketplace_listings (seller_user_id, status, updated_at DESC);

CREATE TABLE marketplace_listing_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id UUID NOT NULL REFERENCES marketplace_listings(id) ON DELETE CASCADE,
  object_uri TEXT NOT NULL,
  alt_text TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX marketplace_listing_images_listing_idx ON marketplace_listing_images (listing_id, sort_order);

-- Buyer cart and immutable cart lines.
CREATE TABLE shopping_carts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  buyer_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'converted', 'abandoned')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX shopping_carts_one_active_per_buyer
  ON shopping_carts (buyer_user_id) WHERE status = 'active';

CREATE TABLE shopping_cart_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cart_id UUID NOT NULL REFERENCES shopping_carts(id) ON DELETE CASCADE,
  listing_id UUID NOT NULL REFERENCES marketplace_listings(id) ON DELETE RESTRICT,
  quantity NUMERIC(14,3) NOT NULL CHECK (quantity > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (cart_id, listing_id)
);

-- Orders preserve the values at checkout so later listing changes do not alter history.
CREATE TABLE marketplace_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  buyer_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE RESTRICT,
  cart_id UUID REFERENCES shopping_carts(id) ON DELETE SET NULL,
  status order_status NOT NULL DEFAULT 'pending',
  payment_status payment_status NOT NULL DEFAULT 'unpaid',
  currency_code CHAR(3) NOT NULL DEFAULT 'INR',
  subtotal_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (subtotal_amount >= 0),
  delivery_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (delivery_amount >= 0),
  total_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
  delivery_address JSONB,
  buyer_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX marketplace_orders_buyer_idx ON marketplace_orders (buyer_user_id, created_at DESC);
CREATE INDEX marketplace_orders_status_idx ON marketplace_orders (status, payment_status);

CREATE TABLE marketplace_order_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID NOT NULL REFERENCES marketplace_orders(id) ON DELETE CASCADE,
  listing_id UUID REFERENCES marketplace_listings(id) ON DELETE SET NULL,
  seller_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE RESTRICT,
  title_snapshot TEXT NOT NULL,
  crop_snapshot TEXT NOT NULL,
  unit_snapshot TEXT NOT NULL,
  quantity NUMERIC(14,3) NOT NULL CHECK (quantity > 0),
  unit_price_snapshot NUMERIC(14,2) NOT NULL CHECK (unit_price_snapshot >= 0),
  line_total NUMERIC(14,2) NOT NULL CHECK (line_total >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX marketplace_order_items_seller_idx ON marketplace_order_items (seller_user_id, created_at DESC);

-- Minimal audit trail for security-sensitive account and order changes.
CREATE TABLE audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id UUID REFERENCES user_accounts(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id UUID,
  request_id TEXT,
  ip_hash TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_entity_idx ON audit_events (entity_type, entity_id, created_at DESC);
CREATE INDEX audit_events_actor_idx ON audit_events (actor_user_id, created_at DESC);

-- Updated-at helper. Use it from application triggers on mutable tables.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER user_accounts_set_updated_at BEFORE UPDATE ON user_accounts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER user_profiles_set_updated_at BEFORE UPDATE ON user_profiles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER state_benchmarks_set_updated_at BEFORE UPDATE ON state_benchmarks FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER farm_fields_set_updated_at BEFORE UPDATE ON farm_fields FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER marketplace_listings_set_updated_at BEFORE UPDATE ON marketplace_listings FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER shopping_carts_set_updated_at BEFORE UPDATE ON shopping_carts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER shopping_cart_items_set_updated_at BEFORE UPDATE ON shopping_cart_items FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER marketplace_orders_set_updated_at BEFORE UPDATE ON marketplace_orders FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Read models useful to the frontend.
CREATE VIEW latest_yield_report_per_field AS
SELECT DISTINCT ON (yr.field_id)
  yr.*
FROM yield_reports yr
ORDER BY yr.field_id, yr.generated_at DESC;

CREATE VIEW published_marketplace_listings AS
SELECT
  ml.id, ml.seller_user_id, ml.title, ml.description, ml.category, ml.crop_name,
  ml.variety_name, ml.available_quantity, ml.quantity_unit, ml.price_per_unit,
  ml.currency_code, ml.state, ml.district, ml.village, ml.harvest_date,
  ml.created_at, ml.updated_at
FROM marketplace_listings ml
WHERE ml.status = 'published' AND ml.available_quantity > 0;

COMMIT;

-- Application integration notes:
-- 1. Normalize Aadhaar by removing spaces/hyphens, normalize PAN to uppercase,
--    then hash with Argon2id/bcrypt. Do not log or persist raw values.
-- 2. Create a user_accounts row only after prototype_consent is checked.
-- 3. Store each estimator run in farm_fields + yield_reports; never overwrite
--    historical yield_reports when the user generates a new report.
-- 4. Recalculate cart totals and available quantities inside a transaction with
--    row locks when creating marketplace_orders.
-- 5. Add PostgreSQL Row-Level Security policies before exposing these tables to
--    a browser-facing API.



-- DRONACHARYA — Estimate Yield-2 database schema
-- This is created automatically by yield_backend.init_db(), included here
-- for reference / manual setup (e.g. `sqlite3 dronacharya.db < schema.sql`).

CREATE TABLE IF NOT EXISTS yield_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,          -- anonymous visitor id (Flask session), or user id once auth exists
    created_at      TEXT NOT NULL,          -- ISO 8601 UTC timestamp
    place           TEXT NOT NULL,
    latitude        REAL,
    longitude       REAL,
    crop            TEXT NOT NULL,          -- rice | wheat | maize | cotton | sugarcane | pulses
    soil_type       TEXT NOT NULL,          -- alluvial | black | red | laterite | arid | mountain | saline
    irrigation_type TEXT NOT NULL,          -- drip | sprinkler | canal | tubewell | rainfed
    ph              REAL NOT NULL,
    area_input      REAL NOT NULL,          -- raw value the user typed
    area_unit       TEXT NOT NULL,          -- acre | hectare
    area_acres      REAL NOT NULL,          -- normalised to acres
    per_acre_yield  REAL NOT NULL,          -- quintals / acre
    total_yield     REAL NOT NULL,          -- quintals, whole field
    confidence_low  REAL NOT NULL,
    confidence_high REAL NOT NULL,
    rainfall_30d_mm REAL,                   -- NULL when weather lookup failed
    weather_source  TEXT NOT NULL,
    result_json     TEXT NOT NULL           -- full report payload, so history replays exactly
);

CREATE INDEX IF NOT EXISTS idx_yield_reports_session ON yield_reports(session_id);


-- DRONACHARYA field-visit booking schema
-- PostgreSQL 15+
BEGIN;

CREATE TYPE field_visit_status AS ENUM ('draft','submitted','under_review','approved','scheduled','sample_collected','report_in_progress','completed','cancelled');
CREATE TYPE visit_priority AS ENUM ('routine_planning','before_sowing','in_season_correction','visible_crop_stress');

CREATE TABLE field_visit_test_catalog (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  category TEXT NOT NULL,
  indicative_fee_inr NUMERIC(10,2) NOT NULL CHECK (indicative_fee_inr >= 0),
  turnaround_min_days INTEGER NOT NULL CHECK (turnaround_min_days > 0),
  turnaround_max_days INTEGER NOT NULL CHECK (turnaround_max_days >= turnaround_min_days),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE field_visit_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_code TEXT NOT NULL UNIQUE,
  user_id UUID REFERENCES user_accounts(id) ON DELETE SET NULL,
  field_name TEXT NOT NULL,
  crop_name TEXT NOT NULL,
  area_value NUMERIC(12,4) NOT NULL CHECK (area_value > 0),
  area_unit TEXT NOT NULL CHECK (area_unit IN ('acres','hectares')),
  soil_type TEXT,
  irrigation_system TEXT,
  preferred_visit_date DATE NOT NULL,
  preferred_time_window TEXT NOT NULL,
  contact_phone TEXT NOT NULL,
  location_label TEXT,
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  location_accuracy_m NUMERIC(10,2),
  location_capture_method TEXT NOT NULL DEFAULT 'manual' CHECK (location_capture_method IN ('manual','browser_geolocation','connector')),
  approximate_ph NUMERIC(4,2) CHECK (approximate_ph IS NULL OR approximate_ph BETWEEN 0 AND 14),
  last_soil_test TEXT,
  priority visit_priority NOT NULL DEFAULT 'routine_planning',
  agronomist_notes TEXT,
  status field_visit_status NOT NULL DEFAULT 'submitted',
  indicative_fee_inr NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (indicative_fee_inr >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
  CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
  CHECK (location_accuracy_m IS NULL OR location_accuracy_m >= 0)
);
CREATE INDEX field_visit_requests_user_idx ON field_visit_requests (user_id, created_at DESC);
CREATE INDEX field_visit_requests_status_date_idx ON field_visit_requests (status, preferred_visit_date);

CREATE TABLE field_visit_request_tests (
  request_id UUID NOT NULL REFERENCES field_visit_requests(id) ON DELETE CASCADE,
  test_id UUID NOT NULL REFERENCES field_visit_test_catalog(id) ON DELETE RESTRICT,
  fee_snapshot_inr NUMERIC(10,2) NOT NULL CHECK (fee_snapshot_inr >= 0),
  status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','scheduled','sample_received','processing','completed','cancelled')),
  result_summary TEXT,
  report_uri TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (request_id, test_id)
);

CREATE TABLE field_visit_slots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES field_visit_requests(id) ON DELETE CASCADE,
  visit_date DATE NOT NULL,
  time_window TEXT NOT NULL,
  assigned_team TEXT,
  assigned_agent TEXT,
  confirmation_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX field_visit_slots_date_idx ON field_visit_slots (visit_date, time_window);

CREATE TABLE field_visit_status_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES field_visit_requests(id) ON DELETE CASCADE,
  from_status field_visit_status,
  to_status field_visit_status NOT NULL,
  changed_by UUID REFERENCES user_accounts(id) ON DELETE SET NULL,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX field_visit_status_history_request_idx ON field_visit_status_history (request_id, created_at DESC);

CREATE OR REPLACE FUNCTION update_field_visit_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;
CREATE TRIGGER field_visit_requests_updated_at
BEFORE UPDATE ON field_visit_requests
FOR EACH ROW EXECUTE FUNCTION update_field_visit_timestamp();

-- Suggested catalog rows based on the page's research-backed options.
INSERT INTO field_visit_test_catalog (code,name,description,category,indicative_fee_inr,turnaround_min_days,turnaround_max_days) VALUES
('routine_soil','Routine soil fertility','Texture, pH, organic matter, available N-P-K.','Soil',650,3,5),
('salinity_sodicity','Salinity & sodicity','EC / soluble salts and sodium-structure risk.','Soil',450,3,5),
('micronutrients','Micronutrient panel','Ca, Mg, Zn, Fe, Cu, Mn, boron and nitrate add-ons.','Soil',800,5,7),
('soil_health','Soil health & biology','Aggregate stability, slake, infiltration and biology indicators.','Soil',950,5,8),
('irrigation_water','Irrigation water quality','EC, pH, SAR, nitrate-N, boron, bicarbonate / chloride.','Water',700,3,5),
('plant_tissue','Plant tissue nutrition','Crop tissue nutrient balance for in-season correction.','Plant',850,5,7),
('nematode','Nematode screening','Composite soil screen for plant-parasitic nematode pressure.','Plant health',900,7,10),
('disease_pest','Plant disease & pest diagnostic','Symptom review and lab referral for pathogen or pest signals.','Plant health',600,3,7),
('contaminants','Contaminant screen','Lead and trace-element checks where risk or history warrants.','Risk',1100,7,14)
ON CONFLICT (code) DO NOTHING;

COMMIT;

-- Application notes:
-- * Treat fees as indicative snapshots, not payment authorization.
-- * Confirm sample depth/count and chain-of-custody at the visit.
-- * Do not store unnecessary identity documents in this schema.
-- * Add row-level security before exposing requests through a browser API.


-- DRONACHARYA climate + market intelligence schema
-- PostgreSQL 14+
-- Store API keys and provider credentials in server-side secrets, never in this table.

begin;

create extension if not exists pgcrypto;

create type climate_source_kind as enum ('imd','open_meteo','weather_api','manual');
create type market_source_kind as enum ('agmarknet','data_gov_in','enam','state_apmc','manual');
create type feed_status as enum ('healthy','degraded','failed');

create table if not exists farm_locations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid null,
  label text not null,
  village text,
  district text,
  state_code text,
  latitude numeric(9,6) not null check (latitude between -90 and 90),
  longitude numeric(9,6) not null check (longitude between -180 and 180),
  timezone text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists crop_profiles (
  id uuid primary key default gen_random_uuid(),
  crop_code text not null unique,
  crop_name text not null,
  indicative_sowing_start smallint check (indicative_sowing_start between 1 and 12),
  indicative_sowing_end smallint check (indicative_sowing_end between 1 and 12),
  indicative_care_start smallint check (indicative_care_start between 1 and 12),
  indicative_care_end smallint check (indicative_care_end between 1 and 12),
  indicative_harvest_start smallint check (indicative_harvest_start between 1 and 12),
  indicative_harvest_end smallint check (indicative_harvest_end between 1 and 12),
  guidance_text text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists location_crop_watchlists (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  location_id uuid not null references farm_locations(id) on delete cascade,
  crop_id uuid not null references crop_profiles(id) on delete restrict,
  created_at timestamptz not null default now(),
  unique(user_id, location_id, crop_id)
);

create table if not exists weather_observations (
  id bigserial primary key,
  location_id uuid not null references farm_locations(id) on delete cascade,
  source climate_source_kind not null,
  observed_at timestamptz not null,
  valid_until timestamptz,
  temperature_c numeric(5,2),
  apparent_temperature_c numeric(5,2),
  precipitation_mm numeric(8,2),
  humidity_percent numeric(5,2),
  wind_speed_kmh numeric(7,2),
  weather_code integer,
  raw_payload jsonb not null default '{}'::jsonb,
  fetched_at timestamptz not null default now(),
  unique(location_id, source, observed_at)
);

create table if not exists weather_forecast_days (
  id bigserial primary key,
  location_id uuid not null references farm_locations(id) on delete cascade,
  source climate_source_kind not null,
  forecast_date date not null,
  temperature_max_c numeric(5,2),
  temperature_min_c numeric(5,2),
  precipitation_sum_mm numeric(8,2),
  precipitation_probability_percent numeric(5,2),
  wind_max_kmh numeric(7,2),
  weather_code integer,
  fetched_at timestamptz not null default now(),
  unique(location_id, source, forecast_date, fetched_at)
);

create table if not exists market_sources (
  id uuid primary key default gen_random_uuid(),
  source_code market_source_kind not null,
  display_name text not null,
  endpoint_url text,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists market_observations (
  id bigserial primary key,
  source_id uuid not null references market_sources(id) on delete restrict,
  crop_id uuid references crop_profiles(id) on delete set null,
  commodity_name text not null,
  state_code text,
  district text,
  mandi_name text,
  variety text,
  grade text,
  unit text not null default 'quintal',
  min_price numeric(14,2),
  modal_price numeric(14,2),
  max_price numeric(14,2),
  arrival_quantity numeric(14,3),
  currency text not null default 'INR',
  observed_at timestamptz not null,
  raw_payload jsonb not null default '{}'::jsonb,
  fetched_at timestamptz not null default now(),
  unique(source_id, commodity_name, state_code, district, mandi_name, observed_at, variety, grade)
);

create table if not exists agriculture_news_items (
  id uuid primary key default gen_random_uuid(),
  crop_id uuid references crop_profiles(id) on delete set null,
  source_name text not null,
  source_url text not null,
  title text not null,
  summary text,
  published_at timestamptz,
  fetched_at timestamptz not null default now(),
  content_hash text not null unique,
  is_active boolean not null default true
);

create table if not exists feed_refresh_logs (
  id bigserial primary key,
  feed_name text not null check (feed_name in ('weather','market','news')),
  source_name text not null,
  status feed_status not null,
  requested_at timestamptz not null default now(),
  completed_at timestamptz,
  records_written integer not null default 0,
  error_message text,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists idx_weather_location_observed on weather_observations(location_id, observed_at desc);
create index if not exists idx_weather_forecast_location_date on weather_forecast_days(location_id, forecast_date);
create index if not exists idx_market_crop_time on market_observations(crop_id, observed_at desc);
create index if not exists idx_market_lookup on market_observations(commodity_name, state_code, district, mandi_name, observed_at desc);
create index if not exists idx_news_crop_published on agriculture_news_items(crop_id, published_at desc);
create index if not exists idx_feed_refresh_recent on feed_refresh_logs(feed_name, requested_at desc);

create or replace view climate_market_latest_prices as
select distinct on (coalesce(mandi_name,'') , commodity_name, coalesce(state_code,''), coalesce(district,''))
  m.id, m.commodity_name, m.state_code, m.district, m.mandi_name, m.variety, m.grade,
  m.unit, m.min_price, m.modal_price, m.max_price, m.arrival_quantity, m.currency,
  m.observed_at, s.display_name as source_name
from market_observations m
join market_sources s on s.id = m.source_id
order by coalesce(mandi_name,''), commodity_name, coalesce(state_code,''), coalesce(district,''), m.observed_at desc;

create or replace view climate_market_latest_weather as
select distinct on (location_id)
  w.location_id, w.source, w.observed_at, w.temperature_c, w.apparent_temperature_c,
  w.precipitation_mm, w.humidity_percent, w.wind_speed_kmh, w.weather_code, w.fetched_at
from weather_observations w
order by location_id, observed_at desc;

create or replace function set_updated_at() returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists farm_locations_updated_at on farm_locations;
create trigger farm_locations_updated_at before update on farm_locations for each row execute function set_updated_at();
drop trigger if exists crop_profiles_updated_at on crop_profiles;
create trigger crop_profiles_updated_at before update on crop_profiles for each row execute function set_updated_at();

commit;
