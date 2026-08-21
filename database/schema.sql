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
