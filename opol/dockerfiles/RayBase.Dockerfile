FROM rayproject/ray:2.39.0-py311

WORKDIR /app

RUN pip install prefect_ray

COPY ../core/ ./core

COPY images/raybaserequirements.txt .

RUN pip install --no-cache-dir -r raybaserequirements.txt

# Add NLTK data download
RUN python -m nltk.downloader punkt punkt_tab
