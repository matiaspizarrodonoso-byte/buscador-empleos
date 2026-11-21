import sys
from pathlib import Path

# Permite importar "scrapers" y "excel" desde la raiz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
