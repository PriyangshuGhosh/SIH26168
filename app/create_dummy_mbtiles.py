import sqlite3
import os

mbtiles_path = r"C:\Users\anish\Desktop\SIH26168\app\app\src\main\assets\map.mbtiles"

# Create assets directory if it doesn't exist
os.makedirs(os.path.dirname(mbtiles_path), exist_ok=True)

# Connect to sqlite database (creates it if it doesn't exist)
conn = sqlite3.connect(mbtiles_path)
c = conn.cursor()

# Create MBTiles required tables
c.execute('CREATE TABLE IF NOT EXISTS metadata (name text, value text);')
c.execute('CREATE UNIQUE INDEX IF NOT EXISTS name ON metadata (name);')
c.execute('CREATE TABLE IF NOT EXISTS tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);')
c.execute('CREATE UNIQUE INDEX IF NOT EXISTS tile_index on tiles (zoom_level, tile_column, tile_row);')

# Insert required metadata
metadata = [
    ('name', 'DummyMap'),
    ('type', 'baselayer'),
    ('version', '1.0'),
    ('description', 'Dummy blank map'),
    ('format', 'png'),
    ('bounds', '-180.0,-85.0,180.0,85.0')
]

for item in metadata:
    c.execute('INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)', item)

conn.commit()
conn.close()
print("Dummy map.mbtiles created successfully.")
