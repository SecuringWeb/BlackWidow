from selenium import webdriver
from selenium.webdriver.support.select import Select
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, UnexpectedAlertPresentException, NoSuchFrameException, NoAlertPresentException, ElementNotVisibleException, InvalidElementStateException
from urllib.parse import urlparse, urljoin
import json
import pprint
import datetime
import tldextract
import math
import os
import traceback
import random
import re
import logging
import copy
import time

import Classes

# If the url is from a form then the form method is used
# However, javascript overrides the form method.
def url_to_request(url, form_method=None):
    purl = urlparse(url)

    if form_method:
        method = form_method
    else:
        method = "get"

    if purl.scheme == "javascript":
        method = "javascript"
    return Classes.Request(url,method)


# Looks for a and from urls
def extract_urls(driver):
    urls = set()

    # Search for urls in <a>
    elem = driver.find_elements_by_tag_name("a")
    for el in elem:
        try:
            if el.get_attribute("href"):
                urls.add( url_to_request(el.get_attribute("href")) )

        except StaleElementReferenceException as e:
            print("Stale pasta in from action")
        except:
            print("Failed to write element")
            print(traceback.format_exc())

    # Search for urls in <frame>
    # elem = driver.find_elements_by_tag_name("frame")
    elem = []
    for el in elem:
        try:
            if el.get_attribute("src"):
                urls.add( url_to_request(el.get_attribute("src")) )

        except StaleElementReferenceException as e:
            print("Stale pasta in from action")
        except:
            print("Failed to write element")
            print(traceback.format_exc())

    # Search for urls in <iframe>
    elem = driver.find_elements_by_tag_name("iframe")
    for el in elem:
        try:
            if el.get_attribute("src"):
                urls.add( url_to_request(el.get_attribute("src")) )

        except StaleElementReferenceException as e:
            print("Stale pasta in from action")
        except:
            print("Failed to write element")
            print(traceback.format_exc())

    # Search for urls in <meta>
    elem = driver.find_elements_by_tag_name("meta")
    for el in elem:
        try:
            
            if el.get_attribute("http-equiv") and el.get_attribute("content"):
                #print(el.get_attribute("http-equiv"))
                #print(el.get_attribute("content"))
                if el.get_attribute("http-equiv").lower()  == "refresh":
                    m = re.search("url=(.*)", el.get_attribute("content"), re.IGNORECASE )
                    fresh_url = m.group(1)
                    #print(fresh_url)
                    full_fresh_url = urljoin( driver.current_url, fresh_url )
                    #print(full_fresh_url)

                    urls.add( url_to_request(full_fresh_url) )

        except StaleElementReferenceException as e:
            print("Stale pasta in from action")
        except:
            print("Failed to write element")
            print(traceback.format_exc())


    resps = driver.execute_script("return JSON.stringify(window_open_urls)")
    window_open_urls = json.loads(resps)
    for window_open_url in window_open_urls:
        full_window_open_url = urljoin( driver.current_url, window_open_url )
        urls.add( url_to_request(full_window_open_url) )

    # Search in comments
    # Regex from https://stackoverflow.com/a/1084759 (Accessed: 2019-02-21)
    # comments = re.findall('<!--(.*?)-->', driver.page_source)
    # for comment in comments:
    #     # Regex from https://stackoverflow.com/a/48769624 (Accessed: 2019-02-21)
    #     m = re.findall('(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+', comment)
    #     for possible_url in m:
    #         full_url = urljoin( driver.current_url, possible_url )
    #         urls.add( url_to_request(full_url) )

    logging.debug("URLs from extract_urls %s" % str(urls) )

    return urls


