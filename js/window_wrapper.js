

//timingCallbackWrap(window, "open", 0, openWrapper);

window["open"] = function() {
    openWrapper(this, arguments);
}



//timingCallbackWrap(window, "setInterval", 0, intervallWrapper);
