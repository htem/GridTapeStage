// must be included after knockoutjs

(function (ko) {
    ko.extenders.min = function (target, option) {
        var result = ko.computed({
            read: target,
            write: function (new_value) {
                cv = target();
                v = parseFloat(new_value);
                if ((v === Number(new_value)) & (v >= option)) {
                    if (v !== cv) {
                        target(v);
                        return;
                    };
                };
                target.notifySubscribers(cv);
            },
        }).extend({notify: 'always'});
        result(target());
        return result;
    };

    ko.extenders.max = function (target, option) {
        var result = ko.computed({
            read: target,
            write: function (new_value) {
                cv = target();
                v = parseFloat(new_value);
                if ((v === Number(new_value)) & (v <= option)) {
                    if (v !== cv) {
                        target(v);
                        return;
                    };
                };
                target.notifySubscribers(cv);
            },
        }).extend({notify: 'always'});
        result(target());
        return result;
    };
    return ko;
})(ko);
