import pandas as pd
import glob
import os

# Find the CSV file
csv_files = glob.glob("/home/uy/Dropbox/smrz04/dgis-gui/backend/*_miembros_completos.csv")

if not csv_files:
    print("No CSV files found!")
else:
    csv_file = csv_files[0]
    print(f"Inspecting: {csv_file}")
    
    try:
        df = pd.read_csv(csv_file)
        print("Columns:", df.columns.tolist())
        
        if 'MIEMBRO_ORDINAL' in df.columns:
            print("\nFirst 20 rows with Ordinal:")
            print(df[['MIEMBRO_CAPTION', 'MIEMBRO_ORDINAL']].head(20))
            
            # Check for Mes members specifically
            mes_members = df[df['MIEMBRO_CAPTION'].isin(['Enero', 'Febrero', 'Marzo', 'Abril'])]
            if not mes_members.empty:
                print("\nMes members:")
                print(mes_members[['MIEMBRO_CAPTION', 'MIEMBRO_ORDINAL']])
        else:
            print("\nMIEMBRO_ORDINAL column NOT found!")
            
    except Exception as e:
        print(f"Error reading CSV: {e}")
