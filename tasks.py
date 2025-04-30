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
        self.download_dir = download_dir # os.path.abspath('output/assets')
        os.makedirs(os.path.dirname(self.download_dir), exist_ok=True)


    def set_chrome_options(self):
        # print('setando webdriver')
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
        # print('webdriver setado')
        return options


    def set_webdriver(self):
        options = self.set_chrome_options()
        try:
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 30)
            # self.logger.info('WebDriver started successfully.')
        except Exception as e:
            self.logger.error(f'Failed to start WebDriver:\n{e}')
            # self.logger.error(f'Failed to start WebDriver.')
            sys.exit()

    def open_url(self, url: str):
        if self.driver:
            try:
                self.driver.get(url)
                # self.logger.info(f'Opened URL: {url}')
            except Exception as e:
                self.logger.error(f'Failed to open URL {url}:\n{e}')
        else:
            self.logger.error('WebDriver not initialized. You must set_webdriver() first.')

    def scroll_down(self, selector):
        try:
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(selector)
            )
            self.driver.execute_script("arguments[0].scrollIntoView({ block: 'center' });", element)
            time.sleep(0.5)
            # element.click()
        except Exception as e:
            pass
            # self.logger.error(f"An exception occured while scrolling down:\n{e}")

    def get_products(self, url):
        # self.logger.info('get_products')
        try:
            # print('get products no try')
            with requests.get(url, headers=self.headers) as response:
                response.raise_for_status()  # Se der erro tipo 404, levanta exceção
                if response.status_code == 200:
                    # print('get products deu certo')
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
                        # print('resultado appendado')

                        self.logger.info(f'{product_id} basic information extracted.')
                    return result
                else:
                    self.logger.info(f"{product_id} Error {response.status_code}: Inaccessible URL.")
        except requests.exceptions.RequestException as e:
            self.logger.error(f'Error trying to get products:\n{e}')
            sys.exit()

    
    def get_bom(self, product_id):
        # print('entrando no BOM')
        self.open_url(f'https://www.baldor.com/catalog/{product_id}#tab="parts"')
        self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'table.data-table tbody tr')))
        bom_rows = self.driver.find_elements(By.CSS_SELECTOR, 'table.data-table tbody tr')
        # print('BOM começar o for')
        bom_list = []
        for row in bom_rows:
            cells = row.find_elements(By.TAG_NAME, 'td')
            part_number = cells[0].text
            description = cells[1].text
            quantity = cells[2].text

            if any([part_number, description, quantity]):
                # print('BOM deu bom')
                quantity = int(quantity.split('.')[0])
                bom_list.append({
                    "part_number": part_number,
                    "description": description,
                    "quantity": quantity
                })
        return bom_list

    def get_assets(self, product_id):
        # print('get assets')
        assets = {"manual": '', "cad": '', "image": ''}
        assets_url = f'output/assets/{product_id}/'
        os.makedirs(os.path.dirname(assets_url), exist_ok=True)

        # print('assets pdf')
        pdf_url = f"https://www.baldor.com/api/products/{product_id}/infopacket"
        pdf_path = f'{assets_url}manual.pdf'

        # print('assets img')
        img_tag = self.driver.find_element(By.CLASS_NAME, 'product-image')
        img_url = img_tag.get_attribute('src') 
        img_path = f'{assets_url}img.jpg'

        # print('assets for pdf img')
        for asset, url, path in zip(['manual', 'image'], [pdf_url, img_url], [pdf_path, img_path]):
            try:
                # print('try ', product_id, asset)
                with requests.get(url, stream=True, timeout=(5, 30), headers=self.headers) as response:
                    response.raise_for_status()
                    with open(path, 'wb') as f:
                        f.write(response.content)
                # self.logger.info(f'{product_id} {asset.capitalize()} successfully downloaded.')

            except requests.exceptions.RequestException as e:
                if not url:
                    self.logger.info(f'{product_id} No {asset} avaliable for this product.')
                else:
                    self.logger.error(f'{product_id} Error trying to download the {asset}:\n{e}')
            assets[asset] = path.replace('output/', '')

        # CAD 
        try:
            # print(product_id, ' vamos CAD')
            self.open_url(f'https://www.baldor.com/catalog/{product_id}#tab="drawings"')
            self.scroll_down((By.XPATH, "//input[@value='2D']"))
            # print(product_id, ' CAD 1')
            self.wait.until(EC.presence_of_all_elements_located((By.XPATH, "//input[@value='2D']")))
            # print(product_id, ' CAD 2')

            try:
                # print('tentando fechar o allow')
                # close_button = self.driver.find_element(By.CLASS_NAME, "adroll_consent_close_icon")
                # print('pegou o fechar o allow', close_button)
                banner = self.driver.find_element(By.ID, "adroll_consent_banner")
                # print('pegou o banner o allow', banner)
                self.driver.execute_script("arguments[0].style.display = 'none';", banner)
                self.driver.delete_all_cookies()
                # print('cliclou')
                time.sleep(1)  # Espera curta para garantir que o banner sumiu
            except Exception as e:
                # print('deu ruim')
                self.logger.error(f'An exception occured while trying to close the consent banner:\n{e}')
            
            # self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            # print(product_id, ' CAD 3')

            radio_button_2d = self.driver.find_element(By.XPATH, "//input[@value='2D']")
            radio_button_2d.click()
            # print(product_id, ' CAD 4')

            dropdown_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(@class, 'k-dropdown')]"))
            )
            dropdown_button.click()
            # print(product_id, ' CAD 5')
                    
            option = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//li[contains(text(), '2D AutoCAD DWG >=2000')]"))
            )
            option.click()
            download_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, "cadDownload"))
            )
            time.sleep(1)
            download_button.click()
            time.sleep(2.5) # Adjust according to connection speed
            # print(product_id, ' CAD 6')

            waiting_time = 0
            while waiting_time < 60:
                # print(product_id, ' CAD 7')
                arquivos = os.listdir(self.download_dir)
                arquivos_crdownload = [arq for arq in arquivos if arq.lower().endswith('.tmp') or arq.lower().endswith('.crdownload')]
                # print(product_id, ' CAD 8')

                if not arquivos_crdownload:
                    # print(product_id, ' CAD 9')
                    arquivos = os.listdir(self.download_dir)
                    # print(product_id, arquivos)
                    arquivo_cad = [arq for arq in arquivos if arq.lower().endswith('.dwg')]
                    # print(product_id, ' CAD 10', arquivo_cad)
                    if arquivo_cad:
                        filename_cad = arquivo_cad[0]

                        # print(product_id, ' CAD 11 ', filename_cad)
                        old_path = os.path.join(self.download_dir, filename_cad)
                        new_path = f'output/assets/{product_id}/cad.dwg'
                        os.rename(old_path, new_path)
                        # shutil.move(old_path, new_path)
                        # print(old_path, new_path)
                        assets['cad'] = new_path.replace('output/', '')
                        # self.logger.info(f'{product_id} DWG file successfully downloaded.')
                    else:
                        self.logger.warning(f'{product_id} No DWG file found after download attempt.')
                    break

                time.sleep(1)
                waiting_time += 1
            else:
                self.logger.error(f'{product_id} Timeout - Could not download DWG file.')
        except Exception as e:
            self.logger.error(f'{product_id} An exceptin occured while getting the CAD file:\n{e}')
            # print('deu exception ', e)

        return assets

    def processing_product(self, product):
        # self.logger.info('processing_product')
        product_id = product['product_id']
        self.logger.info(f'Processing product {product_id}.')

        product['bom'] = self.get_bom(product_id)
        # print('processing BOM')
        product['assets'] = self.get_assets(product_id)
        # print('processing ASSETS')

        not_found = []
        for key in product.keys():
            # print(product[key])
            if isinstance(product[key], dict):
                for key_1 in product[key]:
                    if not product[key][key_1]:
                        not_found.append(key_1)
            if not product[key]:
                not_found.append(key)

        # print('PASSOU NOT FOUND')

        # print('VAI SALVAR JSON')
        with open(f"output/{product_id}.json", "w", encoding="utf-8") as f:
            json.dump(product, f, ensure_ascii=False, indent=4)
        # print('SALVOU JSON')

        log_msg = f'{product_id} Information acquired.'
        if not_found:
            log_msg += f' Missing files: {not_found}.'
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)

    def close_all(self):
        if self.driver:
            try:
                self.driver.quit()
                # self.logger.info('WebDriver closed successfully.')
            except Exception as e:
                self.logger.error(f'Failed to close WebDriver:\n{e}')
        else:
            self.logger.error('WebDriver not initialized.')

def run_scraper_for_product(product):
    # print('RUN SCRAPER')
    product_id = product['product_id']
    scraper = OEMCatalogScraper(download_dir=os.path.abspath(f'output/assets/{product_id}'))
    scraper.set_webdriver()
    scraper.processing_product(product)
    scraper.close_all()

def main():
    scraper = OEMCatalogScraper()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='output/0_OEM_Scraper.log')
    scraper.set_webdriver()

    catalog_number = 312 # 16, 24, 69, 110, 312, 315...
    num_products = 10
    url = f"https://www.baldor.com/api/products?include=results&language=en-US&pageIndex=3&pageSize={num_products}&category={catalog_number}"    

    scraper.logger.info(f'---------- Getting data for {num_products} products in catalog {catalog_number}.')
    products = scraper.get_products(url)
    scraper.logger.info(f'---------- {len(products)} products gotten.')

    with ThreadPoolExecutor(max_workers=2) as executor:
        for product in products:
            # print('----------', product)
            executor.submit(run_scraper_for_product, product)

    scraper.close_all()

    scraper.logger.info('-'*60)


if __name__ == '__main__':
    main()
