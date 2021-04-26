(function(proxied) {
  window.alert = function() { };
})(window.alert);

(function(proxied) {
  window.confirm = function() { return true; };
})(window.confirm);
