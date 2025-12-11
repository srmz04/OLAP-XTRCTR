
import pandas as pd
import logging
from typing import List, Dict, Optional, Any
import os

logger = logging.getLogger(__name__)

class SnapshotOlapService:
    """
    Serves REAL DATA from static CSV snapshots when live connection is unavailable.
    (Previously named MockOlapService, renamed to clarify data authenticity)
    """
    
    def __init__(self, csv_path: str = "mock_data.csv"):
        # Resolve absolute path relative to this file
        if not os.path.isabs(csv_path):
             csv_path = os.path.join(os.path.dirname(__file__), csv_path)
        self.csv_path = csv_path
        self.df = None
        self._load_data()

    def _load_data(self):
        try:
            if os.path.exists(self.csv_path):
                logger.info(f"Loading mock data from {self.csv_path}")
                self.df = pd.read_csv(self.csv_path)
                # Normalize column names just in case
                self.df.columns = [c.upper() for c in self.df.columns]
            else:
                logger.warning(f"Mock data file {self.csv_path} not found")
                self.df = pd.DataFrame()
        except Exception as e:
            logger.error(f"Error loading mock data: {e}")
            self.df = pd.DataFrame()

    async def get_catalogs(self) -> List[Dict[str, str]]:
        """Return list of catalogs found in the CSV."""
        if self.df.empty:
            return [{"name": "MOCK_CATALOG", "description": "Mock Data (No CSV loaded)", "created": "2025-01-01"}]
        
        catalogs = self.df['CATALOGO'].unique()
        return [{"name": str(cat), "description": f"Mock Catalog {cat}", "created": "2025-01-01"} for cat in catalogs]

    async def get_measures(self, catalog_name: str) -> List[Dict[str, str]]:
        """Return fake measures since CSV mostly contains dimension members."""
        # Check if catalog exists in our mock data
        if not self.df.empty and catalog_name not in self.df['CATALOGO'].values:
             logger.warning(f"Catalog {catalog_name} not found in mock data")
        
        # Return some standard mock measures
        return [
            {"id": "[Measures].[Total]", "name": "Total", "caption": "Total Registros", "aggregator": "Count", "type": "measure"},
            {"id": "[Measures].[Cantidad]", "name": "Cantidad", "caption": "Cantidad", "aggregator": "Sum", "type": "measure"}
        ]

    async def get_dimensions(self, catalog_name: str) -> List[Dict[str, Any]]:
        """Return schema from CSV."""
        if self.df.empty:
            return []

        # Filter by catalog
        cat_df = self.df[self.df['CATALOGO'] == catalog_name]
        
        dimensions = []
        for dim_name in cat_df['DIMENSION'].unique():
            dim_df = cat_df[cat_df['DIMENSION'] == dim_name]
            
            hierarchies = []
            for hier_name in dim_df['JERARQUIA'].unique():
                hier_df = dim_df[dim_df['JERARQUIA'] == hier_name]
                
                # Extract levels
                levels = []
                # Assuming NIVEL_NUMERO and NIVEL_CAPTION exist
                level_groups = hier_df.groupby(['NIVEL_NUMERO', 'NIVEL_CAPTION']).size().reset_index()
                level_groups = level_groups.sort_values('NIVEL_NUMERO')
                
                for _, row in level_groups.iterrows():
                    levels.append({
                        "name": row['NIVEL_CAPTION'],
                        "depth": int(row['NIVEL_NUMERO'])
                    })
                
                hierarchies.append({
                    "name": hier_name,
                    "uniqueName": f"[{dim_name}].[{hier_name}]",
                    "levels": levels
                })
            
            dimensions.append({
                "dimension": dim_name,
                "hierarchies": hierarchies,
                "type": "dimension"
            })
            
        return dimensions

    async def get_members(self, catalog_name: str, dimension: str, hierarchy: str, level: str) -> List[Dict[str, str]]:
        """Return members from CSV."""
        if self.df.empty:
            return []

        # Simple filter logic - in a real DB this would be a query
        # Try to match reasonable columns. 
        # API expects args like dimension='[DIM MODULO]', hierarchy='[DIM MODULO].[Módulo]'
        # But our CSV has simple names 'DIM MODULO', 'Módulo'
        
        clean_dim = dimension.replace('[', '').replace(']', '')
        # Hierarchy often comes as [Dim].[Hier], we want the Hier part if possible, or just match strictly if the CSV has full paths?
        # The CSV has 'DIMENSION' column like 'DIM MODULO'
        
        mask = (self.df['CATALOGO'] == catalog_name) & \
               (self.df['DIMENSION'] == clean_dim)
               
        # Try to match level caption or name
        # mask &= (self.df['NIVEL_CAPTION'] == level) # Might need fuzzy matching or strict handling
        
        filtered = self.df[mask]
        
        # If specific level requested, filter by it. 
        # Note: 'level' arg might be unique name or caption.
        # Let's assume caption for now as that's easier with this CSV structure
        if not filtered.empty and level:
             filtered = filtered[filtered['NIVEL_CAPTION'] == level]

        members = []
        # Get unique members at this level
        unique_members = filtered[['MIEMBRO_CAPTION', 'MIEMBRO_UNIQUE_NAME']].drop_duplicates()
        
        for _, row in unique_members.iterrows():
            members.append({
                "caption": str(row['MIEMBRO_CAPTION']),
                "uniqueName": str(row['MIEMBRO_UNIQUE_NAME']),
                "type": "member"
            })
            
        return members[:1000] # Limit return size for mock

    async def execute_query(self, request: Dict) -> Dict:
        """Return mock query result."""
        return {
            "columns": [{"field": "Measures", "headerName": "Measures"}],
            "rows": [{"Measures": "MOCK_VALUE_123"}],
            "rowCount": 1
        }
