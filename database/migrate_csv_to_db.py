#!/usr/bin/env python3
"""
CSV to PostgreSQL Migration Script
Converts OLAP member CSVs to normalized PostgreSQL schema

Usage:
  python database/migrate_csv_to_db.py --csv ../DOCS/SIS_2025_miembros_completos.csv
  python database/migrate_csv_to_db.py --csv ../DOCS/SIS_2025_miembros_completos.csv --dry-run
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from pathlib import Path
import sys
import os
from typing import Dict
import argparse
from tqdm import tqdm
import re

# Connection string from environment
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set")
    print("   Run: export DATABASE_URL='postgresql://...'")
    sys.exit(1)

def extract_year(catalog_code: str) -> int:
    """Extract year from catalog code (e.g. 'SIS_2025' -> 2025)"""
    match = re.search(r'(\d{4})', catalog_code)
    return int(match.group(1)) if match else None

def migrate_catalog(csv_path: Path, catalog_code: str, dry_run: bool = False):
    """
    Migrate a single catalog CSV to PostgreSQL
    
    Args:
        csv_path: Path to CSV file
        catalog_code: Catalog code (e.g. 'SIS_2025')
        dry_run: If True, don't actually insert data
    """
    print(f"\n{'='*60}")
    print(f"📂 Migrating: {catalog_code}")
    print(f"📄 Source: {csv_path}")
    print(f"{'='*60}\n")
    
    # 1. Load CSV
    print("1️⃣  Loading CSV...")
    try:
        df = pd.read_csv(csv_path)
        print(f"   ✅ Loaded {len(df):,} rows, {len(df.columns)} columns")
    except Exception as e:
        print(f"   ❌ Failed to load CSV: {e}")
        return False
    
    # 2. Validate required columns
    required_cols = [
        'CATALOGO', 'DIMENSION', 'JERARQUIA', 'NIVEL_NOMBRE', 
        'NIVEL_NUMERO', 'MIEMBRO_CAPTION', 'MIEMBRO_UNIQUE_NAME'
    ]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        print(f"   ❌ Missing columns: {missing}")
        print(f"   Available columns: {list(df.columns)}")
        return False
    
    print(f"   ✅ All required columns present")
    
    # 3. Connect to database
    print("\n2️⃣  Connecting to PostgreSQL...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        host = DATABASE_URL.split('@')[1].split('/')[0]
        print(f"   ✅ Connected to {host}")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False
    
    if dry_run:
        print("\n🔍 DRY RUN MODE - No data will be inserted\n")
        print(f"   Would process {len(df):,} members")
        print(f"   Estimated time: ~{len(df) // 1000} minutes")
        conn.close()
        return True
    
    try:
        # 4. Insert catalog
        print("\n3️⃣  Inserting catalog...")
        cur.execute("""
            INSERT INTO catalogs (code, name, year)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """, (catalog_code, catalog_code, extract_year(catalog_code)))
        catalog_id = cur.fetchone()[0]
        print(f"   ✅ Catalog ID: {catalog_id}")
        
        # 5. Get unique dimensions
        print("\n4️⃣  Processing dimensions...")
        dimensions = df[['DIMENSION']].drop_duplicates()
        dim_map = {}
        
        for _, row in tqdm(dimensions.iterrows(), total=len(dimensions), desc="   Dimensions", unit="dim"):
            cur.execute("""
                INSERT INTO dimensions (catalog_id, code, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (catalog_id, code) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """, (catalog_id, row['DIMENSION'], row['DIMENSION']))
            dim_map[row['DIMENSION']] = cur.fetchone()[0]
        
        print(f"   ✅ {len(dim_map)} dimensions inserted")
        
        # 6. Get unique hierarchies
        print("\n5️⃣  Processing hierarchies...")
        hierarchies = df[['DIMENSION', 'JERARQUIA']].drop_duplicates()
        hier_map = {}
        
        for _, row in tqdm(hierarchies.iterrows(), total=len(hierarchies), desc="   Hierarchies", unit="hier"):
            dim_id = dim_map[row['DIMENSION']]
            cur.execute("""
                INSERT INTO hierarchies (dimension_id, code, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (dimension_id, code) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """, (dim_id, row['JERARQUIA'], row['JERARQUIA']))
            hier_map[(row['DIMENSION'], row['JERARQUIA'])] = cur.fetchone()[0]
        
        print(f"   ✅ {len(hier_map)} hierarchies inserted")
        
        # 7. Get unique levels
        print("\n6️⃣  Processing levels...")
        levels = df[['DIMENSION', 'JERARQUIA', 'NIVEL_NOMBRE', 'NIVEL_NUMERO']].drop_duplicates()
        level_map = {}
        
        for _, row in tqdm(levels.iterrows(), total=len(levels), desc="   Levels", unit="level"):
            hier_id = hier_map[(row['DIMENSION'], row['JERARQUIA'])]
            cur.execute("""
                INSERT INTO levels (hierarchy_id, name, number)
                VALUES (%s, %s, %s)
                ON CONFLICT (hierarchy_id, name) DO UPDATE SET number = EXCLUDED.number
                RETURNING id
            """, (hier_id, row['NIVEL_NOMBRE'], int(row['NIVEL_NUMERO'])))
            level_map[(row['DIMENSION'], row['JERARQUIA'], row['NIVEL_NOMBRE'])] = cur.fetchone()[0]
        
        print(f"   ✅ {len(level_map)} levels inserted")
        
        # 8. Batch insert members
        print(f"\n7️⃣  Batch inserting {len(df):,} members...")
        member_data = []
        
        for _, row in df.iterrows():
            level_id = level_map[(row['DIMENSION'], row['JERARQUIA'], row['NIVEL_NOMBRE'])]
            member_data.append((
                level_id,
                row['MIEMBRO_CAPTION'],
                row['MIEMBRO_UNIQUE_NAME'],
                row.get('PARENT_UNIQUE_NAME'),
                int(row.get('CHILDREN_CARDINALITY', 0)),
                int(row.get('MIEMBRO_ORDINAL', 0))
            ))
        
        # Batch insert for performance (1000 rows at a time)
        batch_size = 1000
        for i in tqdm(range(0, len(member_data), batch_size), desc="   Members", unit="batch"):
            batch = member_data[i:i+batch_size]
            execute_batch(cur, """
                INSERT INTO members (level_id, caption, unique_name, parent_unique_name, children_cardinality, ordinal)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (unique_name) DO NOTHING
            """, batch, page_size=1000)
        
        print(f"   ✅ Members inserted")
        
        # 9. Commit transaction
        conn.commit()
        print("\n✅ Migration complete!")
        
        # 10. Verify row counts
        print("\n📊 Verification:")
        cur.execute("""
            SELECT COUNT(*) 
            FROM members m
            JOIN levels l ON m.level_id = l.id
            JOIN hierarchies h ON l.hierarchy_id = h.id
            JOIN dimensions d ON h.dimension_id = d.id
            WHERE d.catalog_id = %s
        """, (catalog_id,))
        count = cur.fetchone()[0]
        print(f"   Total members in DB: {count:,}")
        print(f"   Expected from CSV: {len(df):,}")
        
        if count == len(df):
            print("   ✅ Counts match perfectly!")
        else:
            diff = abs(count - len(df))
            print(f"   ⚠️  Mismatch: {diff:,} difference (duplicates skipped)")
        
        # 11. Count apartados
        cur.execute("""
            SELECT COUNT(*) 
            FROM v_members_full
            WHERE catalog_code = %s AND level_name = 'Apartado'
        """, (catalog_code,))
        apartado_count = cur.fetchone()[0]
        print(f"\n   🎯 Apartados found: {apartado_count:,}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description='Migrate OLAP CSV to PostgreSQL')
    parser.add_argument('--csv', required=True, help='Path to CSV file')
    parser.add_argument('--catalog', help='Catalog code (default: extracted from filename)')
    parser.add_argument('--dry-run', action='store_true', help='Validate without inserting')
    
    args = parser.parse_args()
    
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"❌ File not found: {csv_path}")
        sys.exit(1)
    
    catalog_code = args.catalog or csv_path.stem.replace('_miembros_completos', '')
    
    success = migrate_catalog(csv_path, catalog_code, args.dry_run)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
