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


def extract_data_toggle(driver):
    toggles = driver.find_elements_by_xpath("//button[@data-toggle]") 
    dos = []
    for toggle in toggles:

        xpath = driver.execute_script("return getXPath(arguments[0])", toggle) 
        do = {'function_id': '',
              'event': 'click',
              'id': toggle.get_attribute('id'),
              'tag': 'button',
              'addr': xpath,
              'class': ''}
        dos.append(do)

    return dos

def extract_inputs(driver):
    toggles = driver.find_elements_by_xpath("//input") 
    dos = []
    for toggle in toggles:
        input_type = toggle.get_attribute("type")
        if (not input_type) or input_type == "text":

            in_form = toggle.find_elements_by_xpath(".//ancestor::form")
            if not in_form:
                xpath = driver.execute_script("return getXPath(arguments[0])", toggle)
                do = {'function_id': '',
                      'event': 'input',
                      'id': toggle.get_attribute('id'),
                      'tag': 'input',
                      'addr': xpath,
                      'class': ''}
                dos.append(do)

    toggles = driver.find_elements_by_xpath("//textarea")
    for toggle in toggles:
        xpath = driver.execute_script("return getXPath(arguments[0])", toggle)
        do = {'function_id': '',
              'event': 'input',
              'id': toggle.get_attribute('id'),
              'tag': 'input',
              'addr': xpath,
                  'class': ''}
        dos.append(do)

    return dos



def extract_fake_buttons(driver):
    fake_buttons = driver.find_elements_by_class_name("btn") 
    dos = []
    for button in fake_buttons:

        xpath = driver.execute_script("return getXPath(arguments[0])", button) 
        do = {'function_id': '',
              'event': 'click',
              'id': button.get_attribute('id'),
              'tag': 'a',
              'addr': xpath,
              'class': 'btn'}
        dos.append(do)

    return dos


def extract_events(driver):
    # Use JavaScript to find events
    resps = driver.execute_script("return catch_properties()")
    todo = json.loads(resps)

    # From event listeners
    resps = driver.execute_script("return JSON.stringify(added_events)")
    todo += json.loads(resps)

    # From data-toggle
    resps = extract_data_toggle(driver)
    todo += resps


    # Only works in Chrome DevTools
    # resps = driver.execute_script("catch_event_listeners()");
    # todo += resps

    # From fake buttons class="btn"
    resps = extract_fake_buttons(driver)
    todo += resps

    resps = extract_inputs(driver)
    todo += resps

    #for do in todo:
    #    print(do)

    events = set()
    for do in todo:
        event = Classes.Event(do['function_id'], 
                      do['event'],
                      do['id'],
                      do['tag'],
                      do['addr'],
                      do['class'])
        events.add(event)

    return events


