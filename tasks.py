import re
import os
import sys
import time
import json
import shutil
import logging
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from concurrent.futures import ThreadPoolExecutor

class OEMCatalogScraper:

    def __init__(self):
        self.driver = None
        self.wait = None
        self.logger = logging.getLogger(__name__)
        self.headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.download_dir = os.path.abspath('output/assets')


    def set_chrome_options(self):
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
        options = self.set_chrome_options()
        try:
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 30)
            self.logger.info('WebDriver started successfully.')
        except Exception as e:
            self.logger.error(f'Failed to start WebDriver.')
            sys.exit()

    def open_url(self, url: str):
        if self.driver:
            try:
                self.driver.get(url)
                # self.logger.info(f'Opened URL: {url}')
            except Exception as e:
                self.logger.error(f'Failed to open URL {url}:\n {e}')
        else:
            self.logger.error('WebDriver not initialized. You must set_webdriver() first.')

    def scroll_down(self, element_selector, max_scrolls=2):
        """
        Rola a página para baixo várias vezes para carregar todos os itens.
        """
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        for i in range(max_scrolls):
            time.sleep(1)  
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  

            new_height = self.driver.execute_script("return document.body.scrollHeight")
            # print(i, ':', len(self.driver.find_elements(By.CSS_SELECTOR, element_selector)))

            try:
                self.wait.until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, element_selector)) >= 10*(i+2)
                )
                # print(len(self.driver.find_elements(By.CSS_SELECTOR, element_selector)))
            except:
                self.logger.info(f"Error scrolling down.")

            if new_height == last_height:  # It means there are no more new content
                break
            last_height = new_height


    def get_products(self, url):
        try:
            with requests.get(url, headers=self.headers) as response:
                response.raise_for_status()  # Se der erro tipo 404, levanta exceção
                if response.status_code == 200:
                    # Converter a resposta para JSON e exibir
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
                        name = item['categories'][0]['text'] if item['categories'] else None
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

                        # self.logger.info(f'{product_id} basic information extracted.')
                    return result
                else:
                    self.logger.info(f"{product_id} Error {response.status_code}: Inaccessible URL.")
        except requests.exceptions.RequestException as e:
            self.logger.error(f'Error trying to get products: {e}')
            sys.exit()

    
    def get_bom(self, product_code):
        self.open_url(f'https://www.baldor.com/catalog/{product_code}#tab="parts"')
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

    def get_assets(self, product_code):
        assets = {"manual": None, "cad": None, "image": None}
        assets_url = f'output/assets/{product_code}/'
        os.makedirs(os.path.dirname(assets_url), exist_ok=True)

        # CAD
        self.open_url(f'https://www.baldor.com/catalog/{product_code}#tab="drawings"')
        self.scroll_down(None, max_scrolls=1)

        self.wait.until(EC.presence_of_all_elements_located((By.XPATH, "//input[@value='2D']")))
        
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

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
        download_button.click()
        time.sleep(1)

        timeout = 60
        product_id = 'EGDM2333T'
        waiting_time = 0
        while waiting_time < timeout:
            arquivos = os.listdir(self.download_dir)
            arquivos_crdownload = [arq for arq in arquivos if arq.endswith('.tmp') or arq.endswith('.crdownload')]

            if not arquivos_crdownload:
                arquivos = os.listdir(self.download_dir)
                arquivo_cad = [arq for arq in arquivos if arq.endswith('.dwg')]
                if arquivo_cad:
                    filename_cad = arquivo_cad[0]

                    old_file_path = os.path.join(self.download_dir, filename_cad)
                    new_file_path = os.path.join(f'output/assets/{product_id}',  'cad.dwg')
                    shutil.move(old_file_path, new_file_path)
                break

            time.sleep(0.5)
            waiting_time += 1
        else:
            self.logger.error(f'{product_code} Timeout - Could not download DWG file.')


        pdf_url = f"https://www.baldor.com/api/products/{product_code}/infopacket"
        pdf_path = f'{assets_url}manual.pdf'

        img_tag = self.driver.find_element(By.CLASS_NAME, 'product-image')
        img_url = img_tag.get_attribute('src') 
        img_path = f'{assets_url}img.jpg'

        if img_url.endswith('images/451?bc=white&as=1&h=256&w=256'):
            img_url = None

        for asset, url, path in zip(['manual', 'image'], [pdf_url, img_url], [pdf_path, img_path]):
            try:
                with requests.get(url, stream=True, timeout=(5, 30), headers=self.headers) as response:
                    response.raise_for_status()  # Se der erro tipo 404, levanta exceção
                    with open(path, 'wb') as f:
                        f.write(response.content)
                # self.logger.info(f'{product_code} {asset.capitalize()} successfully downloaded.')

            except requests.exceptions.RequestException as e:
                if not url:
                    self.logger.info(f'{product_code} No {asset} avaliable for this product.')
                else:
                    self.logger.error(f'{product_code} Error trying to download the {asset}: {e}')
            assets[asset] = path

        return assets

    def processing_product(self, product):
        product_id = product['product_id']
        # self.logger.info(f'Product {product_id}.')

        product['bom'] = self.get_bom(product_id)
        product['assets'] = self.get_assets(product_id)

        not_found = []
        for key in product.keys():
            if not product[key]:
                not_found.append(key)

        log_msg = f'{product_id} Information acquired.'
        if not_found:
            log_msg += f' Missing: {not_found}.'

        with open(f"output/{product_id}.json", "w", encoding="utf-8") as f:
            json.dump(product, f, ensure_ascii=False, indent=4)

        self.logger.info(log_msg)

    def close_all(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info('WebDriver closed successfully.')
            except Exception as e:
                self.logger.error(f'Failed to close WebDriver.')
        else:
            self.logger.error('WebDriver not initialized.')

def run_scraper_for_product(product):
    scraper = OEMCatalogScraper()
    scraper.set_webdriver()
    scraper.processing_product(product)
    scraper.close_all()

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') #, filename='output/0_logging.log')

    scraper = OEMCatalogScraper()
    scraper.set_webdriver()

    catalog_number = 20
    num_products = 3
    url = f"https://www.baldor.com/api/products?include=results&language=en-US&pageIndex=3&pageSize={num_products}&category={catalog_number}"    

    scraper.logger.info(f'---------- Getting data for {num_products} products in catalog {catalog_number}.')
    products = scraper.get_products(url)
    scraper.logger.info(f'---------- {len(products)} products gotten.')

    with ThreadPoolExecutor(max_workers=3) as executor:
        for product in products:
            executor.submit(run_scraper_for_product, product)

    scraper.close_all()

    scraper.logger.info('-'*60)


if __name__ == '__main__':
    main()
