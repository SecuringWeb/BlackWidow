# Functions.py contains general purpose functions can be utilized by
# the crawler.

from selenium import webdriver
from selenium.webdriver.support.select import Select
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, UnexpectedAlertPresentException, NoSuchFrameException, NoAlertPresentException, ElementNotVisibleException, InvalidElementStateException
from selenium.webdriver.common.by import By
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
import operator

import Classes
from extractors.Events import extract_events
from extractors.Forms import extract_forms, parse_form
from extractors.Urls import extract_urls
from extractors.Iframes import extract_iframes


# From: https://stackoverflow.com/a/47298910
def send(driver, cmd, params={}):
  resource = "/session/%s/chromium/send_command_and_get_result" % driver.session_id
  url = driver.command_executor._url + resource
  body = json.dumps({'cmd': cmd, 'params': params})
  response = driver.command_executor._request('POST', url, body)
  if "status" in response:
    logging.error(response)

def add_script(driver, script):
  send(driver, "Page.addScriptToEvaluateOnNewDocument", {"source": script})


# Changes the address from the row to the first cell
# Only modifies if it is a table row
# In:  /html/body/table/tbody/tr[4]
# Out: /html/body/table/tbody/tr[4]/td[1]
def xpath_row_to_cell(addr):
    # It seems impossible to click (and do other actions)
    # on a <tr> (Table row).
    # Instead, the onclick applies to all cells in the row.
    # Therefore, we pick the first cell.
    parts = addr.split("/")
    if(parts[-1][:2] == "tr"):
        addr += "/td[1]"
    return addr

def remove_alerts(driver):
    # Try to clean up alerts
    try:
        alert = driver.switch_to.alert
        alert.dismiss()
    except NoAlertPresentException:
        pass



def depth(edge):
    depth = 1
    while edge.parent:
        depth = depth + 1
        edge = edge.parent
    return depth

def dom_depth(edge):
    depth = 1
    while edge.parent and edge.value.method == "event":
        depth = depth + 1
        edge = edge.parent
    return depth

# Execute the path necessary to reach the state
def find_state(driver, graph, edge):
    path = rec_find_path(graph, edge)

    for edge_in_path in path:
        method = edge_in_path.value.method
        method_data = edge_in_path.value.method_data
        logging.info("find_state method %s" % method)

        if allow_edge(graph, edge_in_path):
            if method == "get":
                driver.get(edge_in_path.n2.value.url)
            elif method == "form":
                form = method_data
                try:
                    form_fill(driver, form)
                except Exception as e:
                    print(e)
                    print(traceback.format_exc())
                    logging.error(e)
                    return False
            elif method == "ui_form":
                ui_form = method_data
                try:
                    ui_form_fill(driver, ui_form)
                except Exception as e:
                    print(e)
                    print(traceback.format_exc())
                    logging.error(e)
                    return False
            elif method == "event":
                event = method_data
                execute_event(driver, event)
                remove_alerts(driver)
            elif method == "iframe":
                enter_status = enter_iframe(driver, method_data)
                if not enter_status:
                    logging.error("could not enter iframe (%s)" % method_data)
                    return False
            elif method == "javascript":
                # The javascript code is stored in the to-node
                # "[11:]" gives everything after "javascript:"
                js_code = edge_in_path.n2.value.url[11:]
                try:
                    driver.execute_script(js_code)
                except Exception as e:
                    print(e)
                    print(traceback.format_exc())
                    logging.error(e)
                    return False
            else:
                raise Exception( "Can't handle method (%s) in find_state" % method )

    return True


# Recursively follows parent until a stable node is found.
# Stable in this case would be defined as a GET
def rec_find_path(graph, edge):
    path = []
    method = edge.value.method
    parent = edge.parent

    # This is the base case since the first request is always get.
    if method == "get":
        return path + [edge]
    else:
        return rec_find_path(graph, parent) + [edge]


def edge_sort(edge):
    if edge.value[0] == "form":
        return 0
    else:
        return 1


# Check if we should follow edge
# Could be based on SOP, number of reqs, etc.
def check_edge(driver, graph, edge):
    logging.info("Check edge: " + str(edge) )
    method = edge.value.method
    method_data = edge.value.method_data

    # TODO use default FALSE/TRUE
    if method == "get":
        if allow_edge(graph, edge):
            purl = urlparse(edge.n2.value.url)
            if not purl.path in graph.data['urls']:
                graph.data['urls'][purl.path] = 0
            graph.data['urls'][purl.path] += 1

            if graph.data['urls'][purl.path] > 120:
                return False
            else:
                return True
        else:
            logging.warning("Not allow to get %s" % str(edge.n2.value))
            return False
    elif method == "form":
        purl = urlparse(method_data.action)
        if not purl.path in graph.data['form_urls']:
            graph.data['form_urls'][purl.path] = 0
        graph.data['form_urls'][purl.path] += 1

        if graph.data['form_urls'][purl.path] > 10:
            logging.info("FROM ACTION URL (path) %s, visited more than 10 times, mark as done" % str(edge.n2.value.url))
            return False
        else:
            return True
    elif method == "event":
        if dom_depth(edge) > 10:
            logging.info("Dom depth (10) reached! Discard edge %s " % ( str(edge) ) )
            return False
        else:
            return True
    else:
        return True




def follow_edge(driver, graph, edge):

    logging.info("Follow edge: " + str(edge) )
    method = edge.value.method
    method_data = edge.value.method_data
    if method == "get":
        driver.get(edge.n2.value.url)
    elif method == "form":
        logging.info("Form, do find_state")
        if not find_state(driver, graph, edge):
            logging.warning("Could not find state %s" % str(edge))
            edge.visited = True
            return None
    elif method == "event":
        logging.info("Event, do find_state")
        if not find_state(driver, graph, edge):
            logging.warning("Could not find state %s" % str(edge))
            edge.visited = True
            return None
    elif method == "iframe":
        logging.info("iframe, do find_state")
        if not find_state(driver, graph, edge):
            logging.warning("Could not find state %s" % str(edge))
            edge.visited = True
            return None
    elif method == "javascript":
        logging.info("Javascript, do find_state")
        if not find_state(driver, graph, edge):
            logging.warning("Could not find state %s" % str(edge))
            edge.visited = True
            return None
    elif method == "ui_form":
        logging.info("ui_form, do find_state")
        if not find_state(driver, graph, edge):
            logging.warning("Could not find state %s" % str(edge))
            edge.visited = True
            return None
    else:
        raise Exception( "Can't handle method (%s) in next_unvisited_edge " % method )

    # Success
    return True




# Checks if two URLs target the same origin
def same_origin(u1, u2):
    p1 = urlparse(u1)
    p2 = urlparse(u2)

    return (    p1.scheme == p2.scheme
            and p1.netloc == p2.netloc )

def allow_edge(graph, edge):

    crawl_edge = edge.value

    if crawl_edge.method == "get":
        to_url = edge.n2.value.url
    elif crawl_edge.method == "form":
        to_url = crawl_edge.method_data.action
    elif crawl_edge.method == "iframe":
        to_url = crawl_edge.method_data.src
    elif crawl_edge.method == "event":
        ignore = ["onerror"] # Some events that we can't/don't trigger
        return not (crawl_edge.method_data.event in ignore)
    else:
        logging.info("Unsure about method %s, will allow." % crawl_edge.method)
        return True

    from_url = graph.nodes[1].value.url

    parsed_to_url = urlparse(to_url)

    # Relative links are fine. (Not sure about // links)
    if not parsed_to_url.scheme:
        return True

    # If the sceme is javascript we can't know to final destination, so we allow.
    if parsed_to_url.scheme == "javascript":
        return True


    so = same_origin(from_url, to_url)

    # TODO: More general solutions ? e.g regex patterns, counts etc.
    blacklisted_terms = []
    # For example
    # blacklisted_terms.extend( ["logout"] )
    if blacklisted_terms:
        logging.warning("Using blacklisted terms!")

    if to_url:
        bl = any([bt in to_url for bt in blacklisted_terms])
    else:
        bl = False

    # If we are in the same origin AND the request is not blacklisted
    # (Could just return (so and not bl) but this is clearer imho)
    if so and not bl:
        return True
    else:
        logging.debug("Different origins %s and %s" % (str(from_url), str(to_url)))
        return False






def execute_event(driver, do):
    logging.info("We need to trigger [" +  do.event + "] on " + do.addr)

    do.addr = xpath_row_to_cell(do.addr)

    try:
        if   do.event == "onclick" or do.event == "click":
            web_element =  driver.find_element(By.XPATH, By.XPATH, do.addr)
            logging.info("Click on %s" % web_element )

            if web_element.is_displayed():
                web_element.click()
            else:
                logging.warning("Trying to click on invisible element. Use JavaScript")
                driver.execute_script("arguments[0].click()", web_element)
        elif do.event == "ondblclick" or do.event == "dblclick":
            web_element =  driver.find_element(By.XPATH, do.addr)
            logging.info("Double click on %s" % web_element )
            ActionChains(driver).double_click(web_element).perform()
        elif do.event == "onmouseout":
            logging.info("Mouseout on %s" %  driver.find_element(By.XPATH, do.addr) )
            driver.find_element(By.XPATH, do.addr).click()
            el = driver.find_element(By.XPATH, do.addr)
            # TODO find first element in body
            body = driver.find_element(By.XPATH, "/html/body")
            ActionChains(driver).move_to_element(el).move_to_element(body).perform()
        elif do.event == "onmouseover":
            logging.info("Mouseover on %s" %  driver.find_element(By.XPATH, do.addr) )
            el = driver.find_element(By.XPATH, do.addr)
            ActionChains(driver).move_to_element(el).perform()
        elif  do.event == "onmousedown":
            logging.info("Click (mousedown) on %s" %  driver.find_element(By.XPATH, do.addr) )
            driver.find_element(By.XPATH, do.addr).click()
        elif  do.event == "onmouseup":
            logging.info("Mouseup on %s" %  driver.find_element(By.XPATH, do.addr) )
            el = driver.find_element(By.XPATH, do.addr)
            ActionChains(driver).move_to_element(el).release().perform()
        elif  do.event == "change" or do.event == "onchange":
            el = driver.find_element(By.XPATH, do.addr)
            logging.info("Change %s" %  driver.find_element(By.XPATH, do.addr) )
            if el.tag_name == "select":
                # If need to change a select we try the different
                # options
                opts = el.find_elements(By.TAG_NAME, "option")
                for opt in opts:
                    try:
                        opt.click()
                    except UnexpectedAlertPresentException:
                        print("Alert detected")
                        alert = driver.switch_to.alert
                        alert.dismiss()
            else:
                # If ot a <select> we try to write
                el = driver.find_element(By.XPATH, do.addr)
                el.clear()
                el.send_keys("jAEkPot")
                el.send_keys(Keys.RETURN)
        elif  do.event == "input" or do.event == "oninput":
            el = driver.find_element(By.XPATH, do.addr)
            el.clear()
            el.send_keys("jAEkPot")
            el.send_keys(Keys.RETURN)
            logging.info("oninput %s" %  driver.find_element(By.XPATH, do.addr) )

        elif  do.event == "compositionstart":
            el = driver.find_element(By.XPATH, do.addr)
            el.clear()
            el.send_keys("jAEkPot")
            el.send_keys(Keys.RETURN)
            logging.info("Composition Start %s" %  driver.find_element(By.XPATH, do.addr) )

        else:
            logging.warning("Warning Unhandled event %s " % str(do.event) )
    except Exception as e:
        print("Error", do)
        print(e)





def form_fill_file(filename):
    dirname = os.path.dirname(__file__)
    path = os.path.join(dirname, 'form_files', filename)

    if filename != "jaekpot.jpg":
        path = os.path.join(dirname, 'form_files', 'dynamic', filename)
        dynamic_file = open(path, "w+")
        # Could it be worth to add a file content payload?
        dynamic_file.write(filename)
        dynamic_file.close()

    return path



# The problem is that equality does not cover both cases
# Different values => Different Edges           (__eq__)
# Different values => Same form on the webpage  (fuzzy)
# Highly dependent on __eq__ for each element
def fuzzy_eq(form1, form2):
    if form1.action != form2.action:
        return False
    if form1.method != form2.method:
        return False
    for el1 in form1.inputs.keys():
        if not (el1 in form2.inputs):
            return False
    return True

def update_value_with_js(driver, web_element, new_value):
    try:
        new_value = new_value.replace("'", "\\'")
        driver.execute_script("arguments[0].value = '"+new_value+"'", web_element)
    except Exception as e:
        logging.error(e)
        logging.error(traceback.format_exc())
        logging.error("faild to update with JS " + str(web_element)  )

def form_fill(driver, target_form):
    logging.debug("Filling "+ str(target_form))

    # Ensure we don't have any alerts before filling in form
    try:
        alert = driver.switch_to.alert
        alertText = alert.text
        logging.info("Removed alert: " +  alertText)
        alert.accept();
    except:
        logging.info("No alert removed (probably due to there not being any)")
        pass

    elem = driver.find_elements(By.TAG_NAME, "form")
    for el in elem:
        current_form = parse_form(el, driver)

        submit_buttons = []

        if( not fuzzy_eq(current_form, target_form) ):
            continue

        # TODO handle each element
        inputs = el.find_elements(By.TAG_NAME, "input")
        if not inputs:
            inputs = []
            logging.warning("No inputs founds, falling back to JavaScript")
            resps = driver.execute_script("return get_forms()")
            js_forms = json.loads(resps)
            for js_form in js_forms:
                current_form = Classes.Form()
                current_form.method = js_form['method'];
                current_form.action = js_form['action'];

                # TODO Need better COMPARE!
                if( current_form.action == target_form.action and current_form.method ==  target_form.method ):
                    for js_el in js_form['elements']:
                        web_el = driver.find_element(By.XPATH, js_el['xpath'])
                        inputs.append(web_el)
                    break



        buttons = el.find_elements(By.TAG_NAME, "button")
        inputs.extend(buttons)

        for iel in inputs:
            try:
                iel_type = empty2none(iel.get_attribute("type"))
                iel_name = empty2none(iel.get_attribute("name"))
                iel_value = empty2none(iel.get_attribute("value"))
                if iel.get_attribute("type") == "radio":
                    # RadioElement has a different equal function where value is important
                    form_iel = Classes.Form.RadioElement(
                                                     iel_type,
                                                     iel_name,
                                                     iel_value
                                                     )
                elif iel.get_attribute("type") == "checkbox":
                    form_iel = Classes.Form.CheckboxElement(
                                                     iel_type,
                                                     iel_name,
                                                     iel_value,
                                                     None)
                elif iel.get_attribute("type") == "submit":
                    form_iel = Classes.Form.SubmitElement(
                                                     iel_type,
                                                     iel_name,
                                                     iel_value,
                                                     None)
                else:
                    form_iel = Classes.Form.Element(
                                                     iel_type,
                                                     iel_name,
                                                     iel_value
                                                     )
                    logging.warning("Default handling for %s " % str(form_iel))

                if form_iel in target_form.inputs:
                    i = target_form.inputs[form_iel]

                    if iel.get_attribute("type") == "submit" or iel.get_attribute("type") == "image":
                        submit_buttons.append( (iel, i) )
                    elif iel.get_attribute("type") == "file":
                        if "/" in i.value:
                            logging.info("Cannot have slash in filename")
                        else:
                            try:
                                iel.send_keys( form_fill_file(i.value) )
                            except Exception as e:
                                logging.warning("[inputs] Failed to upload file " + str(i.value) + " in " + str(form_iel)  )
                    elif iel.get_attribute("type") == "radio":
                        if i.override_value:
                            update_value_with_js(driver, iel, i.override_value)
                        if i.click:
                            iel.click()
                    elif iel.get_attribute("type") == "checkbox":
                        if i.override_value:
                            update_value_with_js(driver, iel, i.override_value)
                        if i.checked and not iel.get_attribute("checked"):
                            iel.click()
                    elif iel.get_attribute("type") == "hidden":
                        print("IGNORE HIDDEN")
                        #update_value_with_js(driver, iel, i.value)
                    elif iel.get_attribute("type") in ["text", "email", "url"]:
                        if iel.get_attribute("maxlength"):
                            try:
                                driver.execute_script("arguments[0].removeAttribute('maxlength')", iel)
                            except Exception as e:
                                logging.warning("[inputs] faild to change maxlength " + str(form_iel)  )
                        try:
                            iel.clear()
                            iel.send_keys(i.value)
                        except Exception as e:
                            logging.warning("[inputs] faild to send keys to " + str(form_iel) + " Trying javascript" )
                            try:
                                driver.execute_script("arguments[0].value = '"+str(i.value)+"'", iel)
                            except Exception as e:
                                logging.error(e)
                                logging.error(traceback.format_exc())
                                logging.error("[inputs] also faild with JS " + str(form_iel)  )
                    elif iel.get_attribute("type") == "password":
                        try:
                            iel.clear()
                            iel.send_keys(i.value)
                        except Exception as e:
                            logging.warning("[inputs] faild to send keys to " + str(form_iel) + " Trying javascript" )
                            update_value_with_js(driver, iel, i.value)
                    else:
                        logging.warning("[inputs] using default clear/send_keys for " + str(form_iel) )
                        try:
                            iel.clear()
                            iel.send_keys(i.value)
                        except Exception as e:
                            logging.warning("[inputs] faild to send keys to " + str(form_iel) + " Trying javascript" )
                            update_value_with_js(driver, iel, i.value)
                else:
                    logging.warning("[inputs] could NOT FIND " + str(form_iel) )
                    logging.warning("--" + str(target_form.inputs))
                logging.info("Filling in input " + iel.get_attribute("name") )

            except Exception as e:
                logging.error("Could not fill in form")
                logging.error(e)
                logging.error(traceback.format_exc())

        # <select>
        selects = el.find_elements(By.TAG_NAME, "select")
        for select in selects:
            form_select = Classes.Form.SelectElement( "select", select.get_attribute("name") )
            if form_select in target_form.inputs:
                i = target_form.inputs[form_select]
                selenium_select = Select( select )
                options = selenium_select.options
                if i.override_value and options:
                    update_value_with_js(driver, options[0], i.override_value)
                else:
                    for option in options:
                        if option.get_attribute("value") == i.selected:
                            try:
                                option.click()
                            except Exception as e:
                                logging.error("Could not click on " + str(form_select) + ", trying JS")
                                update_value_with_js(driver, select, i.selected)
                            break
            else:
                logging.warning("[selects] could NOT FIND " + str(form_select) )



        # <textarea>
        textareas = el.find_elements(By.TAG_NAME, "textarea")
        for ta in textareas:
            form_ta = Classes.Form.Element( ta.get_attribute("type"),
                                            ta.get_attribute("name"),
                                            ta.get_attribute("value") )
            if form_ta in target_form.inputs:
                i = target_form.inputs[form_ta]
                try:
                    ta.clear()
                    ta.send_keys(i.value)
                except Exception as e:
                    logging.info("[inputs] faild to send keys to " + str(form_iel) + " Trying javascript" )
                    update_value_with_js(driver, ta, i.value)
            else:
                logging.warning("[textareas] could NOT FIND " + str(form_ta) )

        # <iframes>
        iframes = el.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            form_iframe = Classes.Form.Element("iframe", iframe.get_attribute("id"), "")


            if form_iframe in target_form.inputs:
                i = target_form.inputs[form_iframe]
                try:
                    iframe_id =  i.name
                    driver.switch_to.frame(iframe_id)
                    iframe_body = driver.find_element(By.TAG_NAME, "body")
                    if(iframe_body.get_attribute("contenteditable") == "true"):
                        iframe_body.clear()
                        iframe_body.send_keys(i.value)
                    else:
                        logging.error("Body not contenteditable, was during parse")

                    driver.switch_to.default_content();


                except InvalidElementStateException as e:
                    logging.error("Could not clear " + str(form_ta))
                    logging.error(e)
            else:
                logging.warning("[iframes] could NOT FIND " + str(form_ta) )

        # submit
        if submit_buttons:
            logging.info("form_fill Clicking on submit button")

            for submit_button in submit_buttons:
                (selenium_submit, form_submit) = submit_button

                if form_submit.use:
                    try:
                        selenium_submit.click()
                        break
                    except ElementNotVisibleException as e:
                        logging.warning("Cannot click on invisible submit button: " + str(submit_button) + str(target_form) + " trying JavaScript click")
                        logging.info("form_fill Javascript submission of form after failed submit button click")

                        driver.execute_script("arguments[0].click()", selenium_submit)

                        # Also try submitting the full form, shouldn't be needed
                        try:
                            el.submit()
                        except Exception as e:
                            logging.info("Could not submit form, could be good!")

                    except Exception as e:
                        logging.warning("Cannot click on submit button: " + str(submit_button) + str(target_form))
                        logging.info("form_fill Javascript submission of form after failed submit button click")
                        el.submit()

                # Some forms show an alert with a confirmation
                try:
                    alert = driver.switch_to.alert
                    alertText = alert.text
                    logging.info("Removed alert: " +  alertText)
                    alert.accept();
                except:
                    logging.info("No alert removed (probably due to there not being any)")
                    pass
        else:
            logging.info("form_fill Javascript submission of form")
            el.submit()


        # Check if submission caused an "are you sure" alert
        try:
            alert = driver.switch_to.alert
            alertText = alert.text
            logging.info("Removed alert: " +  alertText)
            alert.accept();
        except:
            logging.info("No alert removed (probably due to there not being any)")

        # End of form fill if everything went well
        return True

    logging.error("error no form found (url:%s, form:%s)" % (driver.current_url, target_form) )
    return False
    #raise Exception("error no form found (url:%s, form:%s)" % (driver.current_url, target_form) )


def ui_form_fill(driver, target_form):
    logging.debug("Filling ui_form "+ str(target_form))

    # Ensure we don't have any alerts before filling in form
    try:
        alert = driver.switch_to.alert
        alertText = alert.text
        logging.info("Removed alert: " +  alertText)
        alert.accept();
    except:
        logging.info("No alert removed (probably due to there not being any)")
        pass


    for source in target_form.sources:
        web_element =  driver.find_element(By.XPATH, source['xpath'])

        if web_element.get_attribute("maxlength"):
            try:
                driver.execute_script("arguments[0].removeAttribute('maxlength')", web_element)
            except Exception as e:
                logging.warning("[inputs] faild to change maxlength " + str(web_element)  )

        input_value = source['value']
        try:
            web_element.clear()
            web_element.send_keys(input_value)
        except Exception as e:
            logging.warning("[inputs] faild to send keys to " + str(input_value) + " Trying javascript" )
            try:
                driver.execute_script("arguments[0].value = '"+input_value+"'", web_element)
            except Exception as e:
                logging.error(e)
                logging.error(traceback.format_exc())
                logging.error("[inputs] also faild with JS " + str(web_element)  )


    submit_element =  driver.find_element(By.XPATH, target_form.submit)
    submit_element.click()

def set_standard_values(old_form):
    form = copy.deepcopy(old_form)
    first_radio = True

    for form_el in form.inputs.values():
        if form_el.itype == "file":
            form_el.value = "jaekpot.jpg"
        elif form_el.itype == "radio":
            if first_radio:
                form_el.click = True
                first_radio = False
            # else dont change the value
        elif form_el.itype == "checkbox":
            # Just activate all checkboxes
            form_el.checked = True
        elif form_el.itype == "submit" or form_el.itype == "image":
            form_el.use = False
        elif form_el.itype == "select":
            if form_el.options:
                form_el.selected = form_el.options[0]
            else:
                logging.warning( str(form_el) + " has no options" )
        elif form_el.itype == "text":
            if form_el.value and form_el.value.isdigit():
                form_el.value = 1
            elif form_el.name == "email":
                form_el.value = "jaekpot@localhost.com"
            else:
                form_el.value = "jAEkPot"
        elif form_el.itype == "textarea":
            form_el.value = "jAEkPot"
        elif form_el.itype == "email":
            form_el.value = "jaekpot@localhost.com"
        elif form_el.itype == "hidden":
            pass
        elif form_el.itype == "password":
            form_el.value = "jAEkPot"
            #form_el.value = "jAEkPot1"
        elif form_el.itype == "number":
            # TODO Look at min/max/step/maxlength to pick valid numbers
            form_el.value = "1"
        elif form_el.itype == "iframe":
            form_el.value = "jAEkPot"
        elif form_el.itype == "button":
            pass
        else:
            logging.warning( str(form_el) + " was handled by default")
            form_el.value = "jAEkPot"

    return form

def set_submits(forms):
    new_forms = set()
    for form in forms:
        submits = set()
        for form_el in form.inputs.values():
            if form_el.itype == "submit" or form_el.itype == "image":
                submits.add(form_el)

        if len(submits) > 1:
            for submit in submits:
                new_form = copy.deepcopy(form)
                for new_form_el in new_form.inputs.values():
                    if new_form_el.itype == "submit" and new_form_el == submit:
                        new_form_el.use = True

                new_forms.add(new_form)
        elif len(submits) == 1:
            submits.pop().use = True
            new_forms.add(form)

    return new_forms

def set_checkboxes(forms):
    new_forms = set()
    for form in forms:
        new_form = copy.deepcopy(form)
        for new_form_el in new_form.inputs.values():
            if new_form_el.itype == "checkbox":
                new_form_el.checked = False
                new_forms.add(form)
                new_forms.add(new_form)
    return new_forms

def set_form_values(forms):
    logging.info("set_form_values got " + str(len(forms)))
    new_forms = set()
    # Set values for forms.
    # Could also create copies of forms to test different values
    for old_form in forms:
        new_forms.add( set_standard_values(old_form) )

    # Handle submits
    new_forms = set_submits(new_forms)
    new_checkbox_forms = set_checkboxes(new_forms)
    for checkbox_form in new_checkbox_forms:
        new_forms.add(checkbox_form)

    logging.info("set_form_values returned " + str(len(new_forms)))

    return new_forms


def enter_iframe(driver, target_frame):
    elem = driver.find_elements(By.TAG_NAME, "iframe")
    elem.extend( driver.find_elements(By.TAG_NAME, "frame") )

    for el in elem:
        try:
            src = None
            i = None

            if el.get_attribute("src"):
                src = el.get_attribute("src")
            if el.get_attribute("id"):
                i = el.get_attribute("i")

            current_frame = Classes.Iframe(i, src)
            if current_frame == target_frame:
                driver.switch_to.frame(el)
                return True

        except StaleElementReferenceException as e:
            logging.error("Stale pasta in from action")
            return False
        except Exception as e:
            logging.error("Unhandled error: " + str(e))
            return False
    return False

def find_login_form(driver, graph, early_state=False):
    forms = extract_forms(driver)
    for form in forms:
        for form_input in form.inputs:
            if form_input.itype == "password":
                max_input_for_login = 10
                if len(form.inputs) > max_input_for_login:
                    logging.info("Too many inputs for a login form, " + str(form))
                    continue

                # We need to make sure that the form is part of the graph
                logging.info("NEED TO LOGIN FOR FORM: " + str(form))
                return form


def linkrank(link_edges, visited_list):
    tups = []
    for edge in link_edges:
        url = edge.n2.value.url
        purl = urlparse(edge.n2.value.url)

        queries = len(purl.query.split("&"))
        depth = len(purl.path.split("/"))

        visited = 0
        if purl.path in visited_list:
            visited = 1

        tups.append( (edge, (visited, depth, queries)) )

    tups.sort(key = operator.itemgetter(1))

    return [edge for (edge, _) in tups]

def new_files(link_edges, visited_list):
    tups = []
    for edge in link_edges:
        url = edge.n2.value.url
        purl = urlparse(edge.n2.value.url)
        path = purl.path

        if path not in visited_list:
            print("New file/path: ", path)

        tups.append( (edge, (path in visited_list, path)) )

    tups.sort(key = operator.itemgetter(1))
    print(tups)
    input("OK tups?")

    return [edge for (edge, _) in tups]


# Returns None if the string is empty, otherwise just the string
def empty2none(s):
    if not s:
        return None
    else:
        return s
