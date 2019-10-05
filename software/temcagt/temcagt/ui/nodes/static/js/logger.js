logger = function () {
    var instance = {};

    instance.level = 0;

    instance.CRITICAL = 50;
    instance.ERROR = 40;
    instance.WARNING = 30;
    instance.INFO = 20;
    instance.DEBUG = 10;
    
    level_names = {};
    level_names[instance.CRITICAL] = 'CRITICAL'
    level_names[instance.ERROR] = 'ERROR'
    level_names[instance.WARNING] = 'WARNING'
    level_names[instance.INFO] = 'INFO'
    level_names[instance.DEBUG] = 'DEBUG'

    instance.set_level = function (level) {
        instance.level = level;
    };

    instance.write = function (msg, level) {
        if (level < instance.level) return;
        name = level_names[level] || 'UNDEFINED';
        console.log(name, msg);
    };

    instance.critical = function (msg) {
        return instance.write(msg, instance.CRITICAL);
    };

    instance.warning = function (msg) {
        return instance.write(msg, instance.WARNING);
    };

    instance.info = function (msg) {
        return instance.write(msg, instance.INFO);
    };

    instance.debug = function (msg) {
        return instance.write(msg, instance.DEBUG);
    };

    instance.error = function (msg) {
        return instance.write(msg, instance.ERROR);
    };

    return instance;
}();
