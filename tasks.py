import re
import os
import time
import json
import logging
import requests
import urllib.parse
from datetime import datetime, timedelta
from dateutil import parser
from dateutil.relativedelta import relativedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from concurrent.futures import ThreadPoolExecutor

class OEMCatalogScraper:

    def __init__(self):
        self.driver = None
        self.logger = logging.getLogger(__name__)
        self.wait = WebDriverWait(self.driver, 20)


    def set_chrome_options(self):
        options = webdriver.ChromeOptions()
        # options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--start-maximized')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("--log-level=3")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        return options


    def set_webdriver(self):
        options = self.set_chrome_options()
        try:
            self.driver = webdriver.Chrome(options=options)
            self.logger.info('WebDriver started successfully.')
        except Exception as e:
            self.logger.error(f'ERR0R set_webdriver() | Failed to start WebDriver: {e}')

    def open_url(self, url: str):
        if self.driver:
            try:
                self.driver.get(url)
                self.logger.info(f'Opened URL: {url}')
            except Exception as e:
                self.logger.error(f'ERROR open_url() | Failed to open URL {url}: {e}')
        else:
            self.logger.error('ERR0R open_url() | WebDriver not initialized. You must call set_webdriver() first.')

    def scroll_down(self, element_selector, pause_time=3, max_scrolls=2):
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
                WebDriverWait(self.driver, 10).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, element_selector)) >= 10*(i+2)
                )
                # print(len(self.driver.find_elements(By.CSS_SELECTOR, element_selector)))
            except:
                self.logger.info("No more content to load.")

            if new_height == last_height:  # It means there are no more new content
                break
            last_height = new_height

        self.logger.info("All content loaded.")


    def get_element_list(self, element_selector):
        """
        Gets the elements from the web page.
        """
        try: 
            self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, element_selector)))
            
            products = self.driver.find_elements(By.CSS_SELECTOR, element_selector)
            code_list = []
            for product in products:
                try:
                    code = product.find_element(By.CSS_SELECTOR, 'h3 a').text
                    code_list.append(code)
                except Exception as e:
                    self.logger.warning("Error capturing a product:", e)
            self.logger.info("Finished getting elements.")
            return code_list
        except Exception as e:
            self.logger.warning("Could not get any of the products.")


    def find_element(self, element_xpath):
        try:
            return self.driver.find_element(By.XPATH, element_xpath)
        except:
            return None
    
    def span_text(self, text):
        return f"//span[text()='{text}']/following-sibling::span[@class='value']"

    def get_specs(self, product_code):
        self.open_url(f'https://www.baldor.com/catalog/{product_code}#tab="specs"')
        hp = self.find_element(self.span_text('Output @ Frequency')).text
        voltage = self.find_element(self.span_text('Voltage @ Frequency')).text
        rpm = self.find_element(self.span_text('Synchronous Speed @ Frequency')).text
        frame = self.find_element(self.span_text('Frame')).text

        specs = {
            'hp': hp.split('.')[0],
            'voltage': '/'.join([v.split()[0].replace('.0', '') for v in voltage.split('\n')]),
            'rpm': rpm.split('RPM')[0].strip(),
            'frame': frame
        }

        return specs
    
    def get_bom(self, product_code):
        self.open_url(f'https://www.baldor.com/catalog/{product_code}#tab="parts"')
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
    
    def download_asset(self, product_code, asset, url, path, headers):
        self.logger.info(f'{product_code} Getting {asset}.')
        try:
            with requests.get(url, stream=True, timeout=(5, 30), headers=headers) as response:
                response.raise_for_status()  # Se der erro tipo 404, levanta exceção
                with open(path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            self.logger.info(f'{product_code} {asset.capitalize()} successfully downloaded.')
            return asset, path.replace('output/', '')

        except requests.exceptions.RequestException as e:
            if not url:
                self.logger.info(f'{product_code} No {asset} avaliable for this product.')
            else:
                self.logger.error(f'{product_code} Error trying to download the {asset}: {e}')
            return asset, None

    def get_assets(self, product_code):
        assets = {"manual": None, "cad": None, "image": None}
        assets_url = f'output/assets/{product_code}/'
        os.makedirs(os.path.dirname(assets_url), exist_ok=True)

        # CAD
        self.open_url(f'https://www.baldor.com/catalog/{product_code}#tab="drawings"')
        self.scroll_down(None, max_scrolls=1)
        radio_button_2d = self.driver.find_element(By.XPATH, "//input[@value='2D']")
        radio_button_2d.click()
        # dropdown = self.driver.find_element(By.XPATH, "//select[@kendo-drop-down-list]")
        # dropdown.click()
        # dwg = self.driver.find_element(By.XPATH, "//option[contains(@value, 'DWG')]")
        # dwg.click()
        # # CLICAR NO DOWNLOAD


        # pegar PDF se o link nao for igual
        # pdf_tag = self.driver.find_element(By.ID, 'infoPacket')
        # pdf_url = pdf_tag.get_attribute('href')

        pdf_url = f"https://www.baldor.com/api/products/{product_code}/infopacket"
        pdf_path = f'{assets_url}manual.pdf'

        img_tag = self.driver.find_element(By.CLASS_NAME, 'product-image')
        img_url = img_tag.get_attribute('src') 
        img_path = f'{assets_url}img.jpg'

        if img_url.endswith('images/451?bc=white&as=1&h=256&w=256'):
            img_url = None

        headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            for asset, url, path in zip(['manual', 'image'], [pdf_url, img_url], [pdf_path, img_path]):
                futures.append(executor.submit(self.download_asset, product_code, asset, url, path, headers))
            
            for future in futures:
                asset, result_path = future.result()
                if result_path:
                    assets[asset] = result_path

        return assets

    def get_dict(self, product_code):
        product_dict = {
            "product_id": product_code,
            "name": None,
            "description": None
            # "specs": {"hp": None, "voltage": None, "rpm": None, "frame": None}
        }

        product_dict['specs'] = self.get_specs(product_code)
        product_dict['bom'] = self.get_bom(product_code)
        product_dict['assets'] = self.get_assets(product_code)

        product_dict['description'] = self.driver.find_element(By.CLASS_NAME, 'product-description').text

        return product_dict


    def close_all(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info('WebDriver closed successfully.')
            except Exception as e:
                self.logger.error(f'ERROR close_all() | Failed to close WebDriver: {e}')
        else:
            self.logger.error('ERROR close_all() | WebDriver not initialized.')

    def to_excel(self, data):
        wb = Workbook()
        sheet = wb.active

        headers = ['Title', 'Description', 'Date', 'Filename', 'Count Query in Title and Description', 'Contains Money in Title']
        for i_col, header in enumerate(headers):
            cell_header = sheet.cell(row=1, column=i_col+1)
            cell_header.value = header
            cell_header.font = Font(bold=True, size=12)
            cell_header.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

            if data[i_col] is not None:
                for i_row, val in enumerate(data[i_col]):
                    cell_content = sheet.cell(row=i_row+2, column=i_col+1)
                    cell_content.value = val
                    sheet.row_dimensions[i_row+2].height = 60
                    if i_col > 1:  # Horizontal aligment not for columns Title and Description
                        cell_content.alignment = Alignment(horizontal='center', vertical='center')
                    else:
                        cell_content.alignment = Alignment(vertical='center', wrap_text=True)
            else:
                self.logger.error(f'ERROR to_excel() | {header} list is None.')

        sheet.column_dimensions['A'].width = 25
        sheet.column_dimensions['B'].width = 50
        for col in ['C', 'D', 'E', 'F']:
            sheet.column_dimensions[col].width = 25
        sheet.row_dimensions[1].height = 35

        sheet.title = 'NEWS'
        self.logger.info('Excel done.')
        return wb


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    scraper = OEMCatalogScraper()
    scraper.set_webdriver()

    catalog_number = 110
    url = f'https://www.baldor.com/catalog#category={catalog_number}'
    # scraper.open_url(url)

    element_selector = "div[ng-repeat='product in products.matches track by product.code']"
    # scraper.scroll_down(element_selector)
    # product_codes = scraper.get_element_list(element_selector)

    # for product_code in product_codes:
    product_code = 'CEBM3546T'
    product_dict = scraper.get_dict(product_code)
    print(product_dict)

    with open(f"output/{product_code}.json", "w", encoding="utf-8") as f:
        json.dump(product_dict, f, ensure_ascii=False, indent=4)
# ----- fim do for loop

    time.sleep(1)
    # scraper.close_all()

    scraper.logger.info('-'*60)


if __name__ == '__main__':
    main()
