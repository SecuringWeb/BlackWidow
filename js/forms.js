
function get_forms() {
  var forms = document.forms;
  var obj_forms = [];
  for(var i = 0; i < forms.length; i++) {
      form = {"action": forms[i].action,
              "method": forms[i].method,
              "elements": []};
      els = forms[i].elements;
      for(var j = 0; j < els.length; j++) {
        form.elements.push( {"name": els[j].name,
                             "type": els[j].type, 
                             "xpath": getXPath(els[j])} );
      }
      obj_forms.push(form);
  }
  return JSON.stringify(obj_forms);
}
