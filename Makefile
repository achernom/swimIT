.PHONY: data serve

data:            ## Re-procesa los PDFs de data/raw y regenera la base y los datasets
	python3 ingest/parse.py
	python3 ingest/export_dashboard.py

serve:           ## Sirve el tablero standalone en http://localhost:8000/dashboard/standalone.html
	python3 -m http.server 8000
