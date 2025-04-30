import os
import sys
import time
import json
import logging
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor


class OEMCatalogScraper:

    def __init__(self, download_dir=os.path.abspath('output/assets')):
        self.driver = None
        self.wait = None
        self.logger = logging.getLogger(__name__)
        self.headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.download_dir = download_dir
        os.makedirs(os.path.dirname(self.download_dir), exist_ok=True)

    def set_chrome_options(self):
        """
        Configures Chrome options for Selenium WebDriver.
        Returns:
            options (ChromeOptions): The configured ChromeOptions object.
        """
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--start-maximized')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--log-level=3')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

        prefs = {
            'download.default_directory': self.download_dir,
            'download.prompt_for_download': False,
            'directory_upgrade': True,
            'safebrowsing.enabled': True
        }
        options.add_experimental_option('prefs', prefs)
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        return options

    def set_webdriver(self):
        """
        Initializes the Chrome WebDriver with the specified options.
        Returns:
            None
        """
        options = self.set_chrome_options()
        try:
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 30)
        except Exception as e:
            self.logger.error(f'Failed to start WebDriver:\n{e}')
            sys.exit()

    def open_url(self, url: str):
        """
        Opens the specified URL in the web browser using the initialized WebDriver.
        Args:
            url (str): The URL to be opened.
        Returns:
            None
        """
        if self.driver:
            try:
                self.driver.get(url)
            except Exception as e:
                self.logger.error(f'Failed to open URL {url}:\n{e}')
        else:
            self.logger.error('WebDriver not initialized. You must set_webdriver() first.')

    def scroll_down(self, selector):
        """
        Scrolls the page to bring the specified element into view.
        Args:
            selector (tuple): The locator for the element to scroll to (e.g., (By.XPATH, '...')).
        Returns:
            None
        """
        try:
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(selector)
            )
            self.driver.execute_script("arguments[0].scrollIntoView({ block: 'center' });", element)
            time.sleep(0.5)
        except Exception as e:
            pass

    def get_products(self, url):
        """
        Fetches product details from a specified URL and extracts relevant information.
        Info logs are generated for each successfully extracted product.
        Errors are logged if the request fails or the URL is inaccessible.
        Args:
            url (str): The URL to fetch the product data from.
        Returns:
            list: A list of dictionaries, each containing product details including `product_id`, `name`, 
                `description`, and `specs`.
        """
        try:
            with requests.get(url, headers=self.headers) as response:
                response.raise_for_status()
                if response.status_code == 200:
                    data = response.json()

                    result = []
                    for item in data['results']['matches']:
                        for attribute in item['attributes']:
                            if attribute['name'] == 'output_at_frequency':
                                hp = attribute['values'][0]['value'].replace('hp', '')
                            if attribute['name'] == 'voltage_at_frequency':
                                values = [item['value'].replace('V', '') for item in attribute['values']]
                                voltage = '/'.join(values)
                            if attribute['name'] == 'synchronous_speed_at_freq':
                                rpm = attribute['values'][0]['value'].replace('rpm', '')
                            if attribute['name'] == 'frame':
                                frame = attribute['values'][0]['value']

                        product_id = item.get('code')
                        name = item['categories'][0]['text'] if item['categories'] else ''
                        if "Motors" in name:
                            name = name.replace('Motors', 'Motor')
                        else:
                            name = f'{name} Motor'
                        
                        formatted_item = {
                        'product_id': product_id,
                        'name': name,
                        'description': item.get('description'),
                        'specs': {'hp': hp, 'voltage': voltage, 'rpm': rpm, 'frame': frame}
                        }
                        result.append(formatted_item)

                        self.logger.info(f'{product_id} basic information extracted.')
                    return result
                else:
                    self.logger.info(f"{product_id} Error {response.status_code}: Inaccessible URL.")
        except requests.exceptions.RequestException as e:
            self.logger.error(f'Error trying to get products:\n{e}')
            sys.exit()

    def get_bom(self, product_id):
        """
        Fetches the Bill of Materials (BOM) for a product from the specified URL and extracts part details.
        Args:
            product_id (str): The product ID used to form the URL to fetch the BOM.
        Returns:
            list: A list of dictionaries, each containing details about a part, including `part_number`, 
                `description`, and `quantity`.
        """
        self.open_url(f'https://www.baldor.com/catalog/{product_id}#tab="parts"')
        self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'table.data-table tbody tr')))
        bom_rows = self.driver.find_elements(By.CSS_SELECTOR, 'table.data-table tbody tr')
        bom_list = []
        for row in bom_rows:
            cells = row.find_elements(By.TAG_NAME, 'td')
            part_number = cells[0].text
            description = cells[1].text
            quantity = cells[2].text

            if any([part_number, description, quantity]):
                quantity = int(quantity.split('.')[0])
                bom_list.append({
                    "part_number": part_number,
                    "description": description,
                    "quantity": quantity
                })
        return bom_list

    def get_assets(self, product_id):
        """
        Fetches and downloads product assets including a manual (PDF), image, and CAD drawing (DWG) file.
        Logs errors or warnings if any assets cannot be downloaded or if there are any issues during the process.
        Args:
            product_id (str): The product ID used to fetch the asset files.
        Returns:
            dict: A dictionary containing the file paths of the downloaded assets (manual, image, and CAD).
        """
        assets = {"manual": '', "cad": '', "image": ''}
        assets_url = f'output/assets/{product_id}/'
        os.makedirs(os.path.dirname(assets_url), exist_ok=True)

        pdf_url = f"https://www.baldor.com/api/products/{product_id}/infopacket"
        pdf_path = f'{assets_url}manual.pdf'

        img_tag = self.driver.find_element(By.CLASS_NAME, 'product-image')
        img_url = img_tag.get_attribute('src') 
        img_path = f'{assets_url}img.jpg'

        for asset, url, path in zip(['manual', 'image'], [pdf_url, img_url], [pdf_path, img_path]):
            try:
                with requests.get(url, stream=True, timeout=(5, 30), headers=self.headers) as response:
                    response.raise_for_status()
                    with open(path, 'wb') as f:
                        f.write(response.content)

            except requests.exceptions.RequestException as e:
                if not url:
                    self.logger.info(f'{product_id} No {asset} avaliable for this product.')
                else:
                    self.logger.error(f'{product_id} Error trying to download the {asset}:\n{e}')
            assets[asset] = path.replace('output/', '')

        # CAD 
        try:
            self.open_url(f'https://www.baldor.com/catalog/{product_id}#tab="drawings"')
            self.scroll_down((By.XPATH, "//input[@value='2D']"))
            self.wait.until(EC.presence_of_all_elements_located((By.XPATH, "//input[@value='2D']")))

            try:
                banner = self.driver.find_element(By.ID, "adroll_consent_banner")
                self.driver.execute_script("arguments[0].style.display = 'none';", banner)
                self.driver.delete_all_cookies()
                time.sleep(1)
            except Exception as e:
                self.logger.error(f'An exception occured while trying to close the consent banner:\n{e}')
            
            radio_button_2d = self.driver.find_element(By.XPATH, "//input[@value='2D']")
            radio_button_2d.click()

            dropdown_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(@class, 'k-dropdown')]"))
            )
            dropdown_button.click()
                    
            option = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//li[contains(text(), '2D AutoCAD DWG >=2000')]"))
            )
            option.click()
            download_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, "cadDownload"))
            )
            time.sleep(1)
            download_button.click()
            time.sleep(2.5)

            waiting_time = 0
            while waiting_time < 60:
                arquivos = os.listdir(self.download_dir)
                arquivos_crdownload = [arq for arq in arquivos if arq.lower().endswith('.tmp') or arq.lower().endswith('.crdownload')]

                if not arquivos_crdownload:
                    arquivos = os.listdir(self.download_dir)
                    arquivo_cad = [arq for arq in arquivos if arq.lower().endswith('.dwg')]
                    if arquivo_cad:
                        filename_cad = arquivo_cad[0]

                        old_path = os.path.join(self.download_dir, filename_cad)
                        new_path = f'output/assets/{product_id}/cad.dwg'
                        os.rename(old_path, new_path)
                        assets['cad'] = new_path.replace('output/', '')
                    else:
                        self.logger.warning(f'{product_id} No DWG file found after download attempt.')
                    break

                time.sleep(1)
                waiting_time += 1
            else:
                self.logger.error(f'{product_id} Timeout - Could not download DWG file.')
        except Exception as e:
            self.logger.error(f'{product_id} An exception occured while getting the CAD file:\n{e}')

        return assets

    def processing_product(self, product):
        """
        Processes product data by fetching the BOM and assets, and saves the results to a JSON file.
        Logs a warning if any assets or information are missing, otherwise logs a success message.
        Args:
            product (dict): A dictionary containing product information, including the 'product_id'.
        Returns:
            None: The function modifies the provided product dictionary and saves the results to a JSON file.
        """
        product_id = product['product_id']
        self.logger.info(f'Processing product {product_id}.')

        product['bom'] = self.get_bom(product_id)
        product['assets'] = self.get_assets(product_id)

        not_found = []
        for key in product.keys():
            if isinstance(product[key], dict):
                for key_1 in product[key]:
                    if not product[key][key_1]:
                        not_found.append(key_1)
            if not product[key]:
                not_found.append(key)

        with open(f"output/{product_id}.json", "w", encoding="utf-8") as f:
            json.dump(product, f, ensure_ascii=False, indent=4)

        log_msg = f'{product_id} Information acquired.'
        if not_found:
            log_msg += f' Missing files: {not_found}.'
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)

    def close_all(self):
        """
        Closes the WebDriver session. 
        Logs an error if the WebDriver fails to close or if it was not initialized.
        Args:
            None
        Returns:
            None
        """
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.error(f'Failed to close WebDriver:\n{e}')
        else:
            self.logger.error('WebDriver not initialized.')


def run_scraper_for_product(product):
    """
    Runs the scraper for a given product. 
    Logs the processing of the product and any issues encountered during scraping.
    Args:
        product (dict): A dictionary containing product details, including `product_id`.
    Returns:
        None
    """
    product_id = product['product_id']
    scraper = OEMCatalogScraper(download_dir=os.path.abspath(f'output/assets/{product_id}'))
    scraper.set_webdriver()
    scraper.processing_product(product)
    scraper.close_all()


def main():
    """
    Main function to run the scraper for multiple products from a specific catalog.
    Sets up the scraper, retrieves product data from the Baldor API, and processes each product concurrently 
    using a ThreadPoolExecutor.
    Logs the start and completion of product data retrieval, the number of products processed, 
    and any issues or exceptions encountered during scraping.
    Returns:
        None
    """
    scraper = OEMCatalogScraper()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='output/0_OEM_Scraper.log')
    scraper.set_webdriver()

    catalog_number = 110  # Existing catalogs: 16, 24, 69, 110, 312, 315...
    num_products = 10
    url = f"https://www.baldor.com/api/products?include=results&language=en-US&pageIndex=3&pageSize={num_products}&category={catalog_number}"    

    scraper.logger.info(f'---------- Getting data for {num_products} products in catalog {catalog_number}.')
    products = scraper.get_products(url)
    scraper.logger.info(f'---------- {len(products)} products gotten.')

    with ThreadPoolExecutor(max_workers=2) as executor:
        for product in products:
            executor.submit(run_scraper_for_product, product)

    scraper.close_all()

    scraper.logger.info('-'*60)


if __name__ == '__main__':
    main()
