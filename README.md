# OEM Catalog Scraper

This project aims to scrape data from an industrial equipment catalog, extract relevant product information and assets, and format that into a structured schema suitable for downstream ingestion.

### Deliverables:

- A scraping pipeline in Python that:
  - Extracts structured data from individual product pages
  - Normalizes metadata, specifications, and BOM information
  - Downloads related assets like manuals, CAD files, and images
- One JSON file per product, following a defined schema
- A structured output folder for assets

### Technologies Used

* **Python 3.11.9**
* **Requests** - For HTTP requests.
* **Selenium** - For browser automation.
* **Concurrent Futures** - For parallel execution of functions.

### Installation Steps

1. Clone the repository:

   ```BASH
   git clone https://github.com/luizassimoes/OEM-catalog-scraper.git
   cd OEM-catalog-scraper
   ```
2. (Optional) Create a virtual environment:

   ```bash
   uv venv
   .\venv\Scripts\activate
   ```
3. Install the dependencies:

   ```bash
   uv pip install -r requirements.txt
   ```
4. Once the dependencies are installed, you can execute the script.


### Executing the Script

To execute the script, go to its main folder and run the following command.

```bash
python src/main.py
```
