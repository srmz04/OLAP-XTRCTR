-- OLAP XTRCTR v3.0 - Initial Database Schema
-- Description: Normalized schema for OLAP member catalogs
-- Author: AI Assistant
-- Date: 2024-12-14

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- TABLE: catalogs
-- Description: Top-level OLAP cubes (e.g., SIS_2025, DEFUNCIONES_2024)
-- ============================================================================
CREATE TABLE catalogs (
  id SERIAL PRIMARY KEY,
  code VARCHAR(50) UNIQUE NOT NULL,
  name VARCHAR(200),
  year INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- TABLE: dimensions
-- Description: Dimensions within a catalog (e.g., DIM VARIABLES, DIM TIEMPO)
-- ============================================================================
CREATE TABLE dimensions (
  id SERIAL PRIMARY KEY,
  catalog_id INT REFERENCES catalogs(id) ON DELETE CASCADE,
  code VARCHAR(100) NOT NULL,
  name VARCHAR(200),
  UNIQUE(catalog_id, code)
);

CREATE INDEX idx_dimensions_catalog ON dimensions(catalog_id);

-- ============================================================================
-- TABLE: hierarchies
-- Description: Hierarchies within dimensions (e.g., Apartado y Variable)
-- ============================================================================
CREATE TABLE hierarchies (
  id SERIAL PRIMARY KEY,
  dimension_id INT REFERENCES dimensions(id) ON DELETE CASCADE,
  code VARCHAR(100) NOT NULL,
  name VARCHAR(200),
  UNIQUE(dimension_id, code)
);

CREATE INDEX idx_hierarchies_dimension ON hierarchies(dimension_id);

-- ============================================================================
-- TABLE: levels
-- Description: Levels within hierarchies (e.g., Apartado, Variable)
-- ============================================================================
CREATE TABLE levels (
  id SERIAL PRIMARY KEY,
  hierarchy_id INT REFERENCES hierarchies(id) ON DELETE CASCADE,
  name VARCHAR(50) NOT NULL,  -- 'Apartado', 'Variable', etc.
  number INT,                  -- Level number (1, 2, 3, ...)
  UNIQUE(hierarchy_id, name)
);

CREATE INDEX idx_levels_hierarchy ON levels(hierarchy_id);
CREATE INDEX idx_levels_name ON levels(name);

-- ============================================================================
-- TABLE: members
-- Description: Individual members (apartados, variables, etc.)
-- This is the largest table (~1.7M rows for 131 catalogs)
-- ============================================================================
CREATE TABLE members (
  id SERIAL PRIMARY KEY,
  level_id INT REFERENCES levels(id) ON DELETE CASCADE,
  caption VARCHAR(500) NOT NULL,
  unique_name VARCHAR(500) UNIQUE NOT NULL,
  parent_unique_name VARCHAR(500),
  children_cardinality INT DEFAULT 0,
  ordinal INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indexes (CRITICAL for query speed)
CREATE INDEX idx_members_level ON members(level_id);
CREATE INDEX idx_members_parent ON members(parent_unique_name);
CREATE INDEX idx_members_caption ON members(caption);
CREATE INDEX idx_members_unique ON members(unique_name);

-- Full-text search index for Spanish text
CREATE INDEX idx_members_search ON members 
USING GIN(to_tsvector('spanish', caption));

-- ============================================================================
-- VIEW: v_members_full
-- Description: Denormalized view for easy querying
-- Usage: SELECT * FROM v_members_full WHERE catalog_code = 'SIS_2025' AND level_name = 'Apartado'
-- ============================================================================
CREATE VIEW v_members_full AS
SELECT 
  m.id,
  c.code as catalog_code,
  c.name as catalog_name,
  c.year as catalog_year,
  d.code as dimension_code,
  d.name as dimension_name,
  h.code as hierarchy_code,
  h.name as hierarchy_name,
  l.name as level_name,
  l.number as level_number,
  m.caption,
  m.unique_name,
  m.parent_unique_name,
  m.children_cardinality,
  m.ordinal
FROM members m
JOIN levels l ON m.level_id = l.id
JOIN hierarchies h ON l.hierarchy_id = h.id
JOIN dimensions d ON h.dimension_id = d.id
JOIN catalogs c ON d.catalog_id = c.id;

-- ============================================================================
-- SAMPLE QUERIES (for testing)
-- ============================================================================

-- Get all apartados from SIS_2025
-- SELECT caption, unique_name FROM v_members_full WHERE catalog_code = 'SIS_2025' AND level_name = 'Apartado' ORDER BY caption;

-- Count members by level
-- SELECT catalog_code, level_name, COUNT(*) FROM v_members_full GROUP BY catalog_code, level_name ORDER BY catalog_code, level_name;

-- Full-text search example
-- SELECT caption FROM members WHERE to_tsvector('spanish', caption) @@ to_tsquery('spanish', 'diabetes') LIMIT 10;
