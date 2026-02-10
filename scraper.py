import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import random
import re
from datetime import datetime, timedelta

import argparse

def get_ads_urls(keyword="minibus"):
    url = f"https://www.moteur.ma/fr/occasion/voitures/recherche/?search=1&motcle={keyword}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    
    print(f"Fetching Moteur.ma category: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        ads = []
        # Try finding ads in picture containers first (best for images)
        containers = soup.find_all('div', class_=re.compile(r'picture|item-annonce|content-inner-listing'))
        for item in containers:
            a = item.find('a', href=True)
            if not a: continue
            href = a['href']
            if '/detail-annonce/' not in href: continue
            
            if not href.startswith('http'):
                href = "https://www.moteur.ma" + href
            
            img = item.find('img')
            image = ""
            if img:
                # Prioritize src but check data-src too
                image = img.get('src') or img.get('data-src') or ""
            
            if image and not image.startswith('http'):
                image = "https://www.moteur.ma" + image
            
            if not any(x[0] == href for x in ads):
                ads.append((href, image))
        
        # Fallback to any ad links if containers failed
        if not ads:
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/detail-annonce/' in href:
                    if not href.startswith('http'):
                        href = "https://www.moteur.ma" + href
                    
                    if not any(x[0] == href for x in ads):
                        img = a.find('img') or (a.find_parent() and a.find_parent().find('img'))
                        image = img.get('src') if img else ""
                        if image and not image.startswith('http'):
                            image = "https://www.moteur.ma" + image
                        ads.append((href, image))
        
        print(f"Found {len(ads)} unique ads on Moteur.ma.")
        return ads[:10]
    except Exception as e:
        print(f"Moteur.ma Error: {e}")
        return []

def parse_date(date_str):
    if not date_str or date_str == "Unknown":
        return None
    
    today = datetime.now()
    date_str = date_str.lower().strip()
    
    try:
        # Handle "Aujourd'hui"
        if "aujourd'hui" in date_str:
            return today
        
        # Handle "Hier"
        if "hier" in date_str:
            return today - timedelta(days=1)
        
        # Handle "Il y a X jours"
        match_jours = re.search(r'il y a (\d+) jours', date_str)
        if match_jours:
            days = int(match_jours.group(1))
            return today - timedelta(days=days)
        
        # Handle "Il y a X heures" / "Il y a X minutes" (treat as today)
        if "il y a" in date_str and ("heures" in date_str or "minutes" in date_str):
            return today

        # Handle DD-MM-YYYY or DD/MM/YYYY
        match_date = re.search(r'(\d{2})[-/](\d{2})[-/](\d{4})', date_str)
        if match_date:
            day, month, year = map(int, match_date.groups())
            return datetime(year, month, day)

        # Handle Avito listTime format (assuming it's a timestamp or ISO-like string if extracted from JSON)
        # If it's a simple string like "2026-02-10 12:00:00"
        if len(date_str) >= 10:
            try:
                return datetime.fromisoformat(date_str.split(' ')[0])
            except:
                pass

    except Exception as e:
        print(f"Error parsing date {date_str}: {e}")
    
    return None

def is_within_4_weeks(date_val):
    if date_val is None:
        return True # Keep if unknown
    
    cutoff = datetime.now() - timedelta(weeks=4)
    return date_val >= cutoff

def get_ad_details(url, image_from_list=""):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Date parsing
        date_pub_str = "Today"
        date_elem = soup.find(string=re.compile(r'\d{2}-\d{2}-\d{4}'))
        if date_elem:
            date_pub_str = date_elem.strip()
        
        date_val = parse_date(date_pub_str)
        if not is_within_4_weeks(date_val):
            return None

        model = "Utilitaire"
        h1 = soup.find('h1')
        if h1: model = h1.get_text(strip=True)
        
        price_tag = soup.find('div', class_=re.compile(r'price'))
        price = price_tag.get_text(strip=True) if price_tag else "N/A"
        
        image_url = image_from_list
        if not image_url:
            image_tag = soup.find('img', class_=re.compile(r'fluid|detail'))
            image_url = image_tag['src'] if image_tag and image_tag.get('src') else ""

        contact_elem = soup.find(attrs={"data-token": True, "data-seller": True})
        phone = "N/A"
        if contact_elem:
            try:
                seller_id = contact_elem['data-seller']
                token = contact_elem['data-token']
                ajax_url = f"https://www.moteur.ma/fr/occasion/get_phone/{seller_id}/?token={token}"
                phone_res = requests.get(ajax_url, headers={'X-Requested-With': 'XMLHttpRequest', 'User-Agent': headers['User-Agent']})
                phone = phone_res.json().get('phone', "N/A")
            except:
                pass

        return {
            "model": model,
            "prix": price,
            "contact": "Vendeur (Moteur.ma)",
            "lien": url,
            "telephone": phone or "N/A",
            "date": date_pub_str,
            "image": image_url,
            "site": "Moteur.ma"
        }
    except Exception as e:
        print(f"Moteur.ma Detail Error for {url}: {e}")
        return None

def get_phone_ajax(ajax_url, seller_id, token, referer):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': referer
    }
    data = {'seller': seller_id, 'token': token}
    
    try:
        time.sleep(random.uniform(0.5, 1.5))
        response = requests.post(ajax_url, headers=headers, data=data)
        if response.status_code == 200 and response.text.strip():
            return response.text.strip()
    except Exception as e:
        print(f"Error fetching phone: {e}")
    return None

def get_avito_ads(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    print(f"Fetching Avito category: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        ads = []
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag:
            try:
                data = json.loads(next_data_tag.string)
                page_props = data.get('props', {}).get('pageProps', {})
                
                # New direct path to ads
                ads_list = page_props.get("componentProps", {}).get("ads", {}).get("ads", [])
                if not ads_list:
                    ads_list = page_props.get("ads", {}).get("ads", [])
                
                # If that fails, try the older apolloState way as fallback
                if not ads_list:
                    apollo_state = data.get("props", {}).get("pageProps", {}).get("apolloState", {})
                    for key, val in apollo_state.items():
                        if isinstance(val, dict) and val.get("__typename") == "Ad":
                            ad_url = val.get("url")
                            if ad_url:
                                if not ad_url.startswith('http'):
                                    ad_url = "https://www.avito.ma" + ad_url
                                image = ""
                                images = val.get("images", [])
                                if images:
                                    img_ref = images[0]
                                    if isinstance(img_ref, dict):
                                        img_id = img_ref.get("id")
                                        if img_id and img_id in apollo_state:
                                            image = apollo_state[img_id].get("url") or apollo_state[img_id].get("uri")
                                        else:
                                            image = img_ref.get("url") or img_ref.get("uri")
                                if not any(x[0] == ad_url for x in ads):
                                    ads.append((ad_url, image))
                else:
                    for ad in ads_list:
                        ad_url = ad.get("href")
                        if not ad_url: continue
                        if not ad_url.startswith('http'):
                            ad_url = "https://www.avito.ma" + ad_url
                        
                        image = ad.get("defaultImage") or ""
                        if not image and ad.get("images"):
                            image = ad.get("images")[0]
                        
                        if not any(x[0] == ad_url for x in ads):
                            ads.append((ad_url, image))
            except Exception as e:
                print(f"Error parsing Avito JSON: {e}")
            
        print(f"Found {len(ads)} unique Avito ads.")
        return ads[:10]
    except Exception as e:
        print(f"Avito Error: {e}")
        return []

def get_avito_details(url, image_from_list=""):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try finding JSON data first
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag:
            try:
                data = json.loads(next_data_tag.string)
                # Ad details are usually in props.pageProps.ad
                ad_details = data.get("props", {}).get("pageProps", {}).get("ad", {})
                if ad_details:
                    prix = ad_details.get("price", {}).get("value")
                    model = ad_details.get("subject", "N/A")
                    date_str = ad_details.get("date", "N/A")
                    phone_obj = ad_details.get("seller", {}).get("phone", {})
                    telephone = phone_obj.get("number") if phone_obj else "N/A"
                    image_url = ad_details.get("defaultImage") or (ad_details.get("images", [""])[0])
                    
                    return {
                        "prix": f"{prix} DH" if prix else "N/A",
                        "model": model,
                        "date": date_str,
                        "telephone": telephone or "N/A",
                        "image": image_url or image_from_list,
                        "lien": url,
                        "site": "Avito.ma"
                    }
                
                # Fallback to apolloState if that fails
                apollo_state = data.get("props", {}).get("pageProps", {}).get("apolloState", {})
                ad_info = None
                for key, val in apollo_state.items():
                    if key.startswith("Ad:"):
                        ad_info = val
                        break
                
                if ad_info:
                    prix = ad_info.get("price", {}).get("amount")
                    model = ad_info.get("subject", "N/A")
                    date_str = ad_info.get("listTime", "N/A")
                    return {
                        "prix": f"{prix} DH" if prix else "N/A",
                        "model": model,
                        "date": date_str,
                        "telephone": "N/A",
                        "image": image_from_list,
                        "lien": url,
                        "site": "Avito.ma"
                    }
            except Exception as e:
                print(f"Error parsing Avito detail JSON: {e}")

        # Fallback to HTML selectors
        prix_tag = soup.find('p', class_=re.compile(r'price|Price'))
        prix = prix_tag.text.strip() if prix_tag else "N/A"
        model_tag = soup.find('h1')
        model = model_tag.text.strip() if model_tag else "N/A"
        date_tag = soup.find('time') or soup.find('span', class_=re.compile(r'date|Date'))
        date_str = date_tag.text.strip() if date_tag else "N/A"
        
        return {
            "prix": prix,
            "model": model,
            "date": date_str,
            "telephone": "N/A",
            "image": image_from_list,
            "lien": url,
            "site": "Avito.ma"
        }
    except Exception as e:
        print(f"Avito Detail Error for {url}: {e}")
        return None

def get_maroc_utilitaires_ads():
    url = "https://www.maroc-utilitaires.com/minibus/3-37-v115/minibus-occasion.html"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    print(f"Fetching Maroc-Utilitaires ads from: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        ads = []
        # In Maroc-Utilitaires, entries have class 'annonce-utilitaire'
        for item in soup.select('div.annonce-utilitaire'):
            a = item.find('a', href=True)
            if not a: continue
            ad_url = a['href']
            if not ad_url.startswith('http'):
                ad_url = "https://www.maroc-utilitaires.com" + ad_url
            
            img_tag = item.find('img')
            img_url = ""
            if img_tag:
                img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-original') or ""
            
            if not any(x[0] == ad_url for x in ads):
                ads.append((ad_url, img_url))
        
        print(f"Found {len(ads)} unique Maroc-Utilitaires ads.")
        return ads[:10]
    except Exception as e:
        print(f"Maroc-Utilitaires Ads Error: {e}")
        return []

def get_maroc_utilitaires_details(url, image_from_list=""):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        date_tag = soup.find(string=re.compile(r'\d{2}/\d{2}/\d{4}'))
        date_pub_str = date_tag.strip() if date_tag else "Unknown"
        date_val = parse_date(date_pub_str)
        if not is_within_4_weeks(date_val):
            print(f"MU: {url} excluded by date ({date_pub_str})")
            return None

        model = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Utilitaire"
        price_tag = soup.find('div', class_='price-tag') or soup.find(string=re.compile(r'\d+ DH'))
        price = price_tag.get_text(strip=True) if hasattr(price_tag, 'get_text') else "Sur demande"
        
        image = image_from_list
        if not image:
            img_tag = soup.find('img', class_='img-fluid')
            image = img_tag['src'] if img_tag and img_tag.get('src') else ""
        
        return {
            "model": model,
            "prix": price,
            "contact": "Vendeur (Maroc-Utilitaires)",
            "lien": url,
            "telephone": "Voir site",
            "date": date_pub_str,
            "image": image,
            "site": "Maroc-Utilitaires"
        }
    except Exception as e:
        print(f"MU Detail Error for {url}: {e}")
        return None

def get_autoline_ads():
    url = "https://autoline.co.ma/-/minibus--c5835"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    print(f"Fetching Autoline ads from: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        ads = []
        # Autoline ads are in containers like 'div.sl-item'
        for item in soup.select('div.sl-item'):
            a = item.find('a', class_='sales-item-title-link', href=True)
            if not a: continue
            ad_url = a['href']
            if not ad_url.startswith('http'):
                ad_url = "https://autoline.co.ma" + ad_url
            
            img_tag = item.find('img')
            image = ""
            if img_tag:
                image = img_tag.get('data-src') or img_tag.get('src') or ""
            
            if not any(x[0] == ad_url for x in ads):
                ads.append((ad_url, image))

        print(f"Found {len(ads)} unique Autoline ads.")
        return ads[:10]
    except Exception as e:
        print(f"Autoline Ads Error: {e}")
        return []

def get_autoline_details(url, image_from_list=""):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        date_pub_str = "Today"
        date_val = parse_date(date_pub_str)
        if not is_within_4_weeks(date_val):
            return None

        model = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Minibus"
        price_tag = soup.find('div', class_='price') or soup.find('div', class_='item-price') or soup.find('div', class_='sl-item__price')
        price = price_tag.get_text(strip=True) if price_tag else "Sur demande"
        
        image = image_from_list
        if not image:
            img = soup.find('img', class_='gallery__main-image') or soup.find('img', class_='main-image')
            image = img['src'] if img and img.get('src') else ""
        
        return {
            "model": model,
            "prix": price,
            "contact": "Autoline Seller",
            "lien": url,
            "telephone": "N/A",
            "date": date_pub_str,
            "image": image,
            "site": "Autoline"
        }
    except Exception as e:
        print(f"AL Detail Error for {url}: {e}")
        return None

def get_truck1_ads():
    url = "https://www.truck1.co.ma/bus-et-autocars/minibus"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    print(f"Searching Truck1: {url}")
    try:
        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        headers['Accept-Language'] = 'fr,fr-FR;q=0.8,en-US;q=0.5,en;q=0.3'
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        ads = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/minibus/' in href and not href.endswith('/minibus'):
                if not href.startswith('http'):
                    if not href.startswith('/'): href = '/' + href
                    href = "https://www.truck1.co.ma" + href
                ads.append(href)
        print(f"Truck1 found {len(ads)} candidates.")
        return list(set(ads))[:10]
    except Exception as e:
        print(f"T1 Error: {e}")
        return []

def get_truck1_details(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.1234.56 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
    }
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        date_pub_str = "Today" 
        date_val = parse_date(date_pub_str)
        if not is_within_4_weeks(date_val):
            return None

        model = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Truck1 Ad"
        price_tag = soup.find('div', class_='price-value')
        price = price_tag.get_text(strip=True) if price_tag else "Sur demande"
        
        img = soup.find('img', class_='main-image')
        image = img['src'] if img and img.get('src') else ""
        
        return {
            "model": model,
            "prix": price,
            "contact": "Truck1 Seller",
            "lien": url,
            "telephone": "N/A",
            "date": date_pub_str,
            "image": image,
            "site": "Truck1.co.ma"
        }
    except Exception as e:
        print(f"T1 Detail Error for {url}: {e}")
        return None

def parse_price(price_str):
    if not price_str or "demande" in price_str.lower():
        return 0
    nums = re.findall(r'\d+', price_str.replace(' ', '').replace('\xa0', '').replace('\u202f', ''))
    return int(nums[0]) if nums else 0

def run_full_scrape(keyword="minibus", avito_url="https://www.avito.ma/fr/maroc/fourgon_et_minibus"):
    ads_data = []
    
    print(f"--- Starting Moteur.ma ---")
    m_urls = get_ads_urls(keyword)
    for url in m_urls:
        details = get_ad_details(url)
        if details:
            ads_data.append(details)
            time.sleep(0.5)

    print(f"--- Starting Avito ---")
    a_urls = get_avito_ads(avito_url)
    for url in a_urls:
        details = get_avito_details(url)
        if details:
            ads_data.append(details)
            time.sleep(0.5)

    print(f"--- Starting Maroc-Utilitaires ---")
    mu_data = get_maroc_utilitaires_ads() # Returns (url, img)
    for url, img in mu_data:
        details = get_maroc_utilitaires_details(url, image_from_list=img)
        if details:
            ads_data.append(details)
            time.sleep(0.5)

    print(f"--- Starting Autoline ---")
    al_data = get_autoline_ads() # Returns (url, img)
    for url, img in al_data:
        details = get_autoline_details(url, image_from_list=img)
        if details:
            ads_data.append(details)
            time.sleep(0.5)

    print(f"--- Starting Truck1 ---")
    t1_urls = get_truck1_ads()
    for url in t1_urls:
        details = get_truck1_details(url)
        if details:
            ads_data.append(details)
            time.sleep(0.5)

    try:
        ads_data.sort(key=lambda x: (x.get('date', ''), parse_price(x.get('prix', ''))), reverse=True)
    except:
        pass

    csv_file = "liste_annonces_v2.csv"
    try:
        with open(csv_file, mode='w', newline='', encoding='utf-8') as file:
            fieldnames = ["site", "model", "prix", "contact", "lien", "telephone", "date", "image"]
            writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            for ad in ads_data:
                row = {k: ad.get(k, "") for k in fieldnames}
                writer.writerow(row)
    except Exception as e:
        print(f"CSV Error: {e}")
        
    return ads_data, csv_file

def main():
    parser = argparse.ArgumentParser(description="Scrape vehicle ads from various sites")
    parser.add_argument("--keyword", default="minibus", help="Keyword for Moteur.ma search")
    parser.add_argument("--avito-url", default="https://www.avito.ma/fr/maroc/fourgon_et_minibus", help="Category URL for Avito.ma")
    args = parser.parse_args()

    results, _ = run_full_scrape(args.keyword, args.avito_url)
    print(f"Done. Found {len(results)} total ads.")

if __name__ == "__main__":
    main()
