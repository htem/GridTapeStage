/************ Example usage *************
        var roi_definer;
        $(function() {
            roi_definer = new ROIDefiner('body');
            $(roi_definer).on('new_position', function (e, x, y) {
                roi_definer.set_position(x, y);
            });

            $(roi_definer).on('set_roi', function (e, x, y, landmark) {
            });

            // drop-down for action selection
            $('#roi_action').change(function () {
                action = $(this).val();
                switch (action) {
                    case 'move':
                        roi_definer.click_action = 'move';
                        roi_definer.landmark = '';
                        break;
                    case 'left':
                    case 'right':
                    case 'top':
                    case 'bottom':
                    case 'top_left':
                    case 'top_right':
                    case 'bottom_left':
                    case 'bottom_right':
                        roi_definer.click_action = 'set_roi';
                        roi_definer.landmark = action;
                        break;
                    default:
                };
            });
        });
    <select id="roi_action">
        <option value="move" selected="selected">Move</option>
        <option value="left">Left</option>
        <option value="right">Right</option>
        <option value="top">Top</option>
        <option value="bottom">Bottom</option>
        <option value="top_left">Top Left</option>
        <option value="top_right">Top Right</option>
        <option value="bottom_left">Bottom Left</option>
        <option value="bottom_right">Bottom Right</option>
    </select>
******************************************/
ROIResolver = function () {
    
    resolvers = {};

    resolvers['left'] = function (roi) {
        if (roi['width'] != undefined) {
            if (roi['right'] != undefined) return roi['right'] - roi['width'];
            if (roi['center'] != undefined) return roi['center'][0] - roi['width'] / 2.;
        };
        return null;
    };

    resolvers['right'] = function(roi) {
        if (roi['width'] != undefined) {
            if (roi['left'] != undefined) return roi['left'] + roi['width'];
            if (roi['center'] != undefined) return roi['center'][0] + roi['width'] / 2.;
        };
        return null;
    };

    resolvers['top'] = function (roi) {
        if (roi['height'] != undefined) {
            if (roi['bottom'] != undefined) return roi['bottom'] - roi['height'];
            if (roi['center'] != undefined) return roi['center'][1] - roi['height'] / 2.;
        };
        return null;
    };

    resolvers['bottom'] = function (roi) {
        if (roi['height'] != undefined) {
            if (roi['top'] != undefined) return roi['top'] + roi['height'];
            if (roi['center'] != undefined) return roi['center'][1] + roi['height'] / 2.;
        };
        return null;
    };

    resolvers['width'] = function (roi) {
        if ((roi['left'] == undefined) || (roi['right'] == undefined)) return null;
        return roi['right'] - roi['left'];
    };

    resolvers['height'] = function (roi) {
        if ((roi['top'] == undefined) || (roi['bottom'] == undefined)) return null;
        return roi['bottom'] - roi['top'];
    };

    resolvers['center'] = function (roi) {
        throw "Not yet implemented";
    };

    function resolve(landmark, roi) {
        if (roi[landmark] != undefined) {
            return roi[landmark];
        }
        return resolvers[landmark](roi);
    };

    return {
        'resolve': resolve
    };
}();


function ROIDefiner(selector, width, height, xdomain, ydomain) {
    var self = this;
    var instance = {};
    instance.n_images = 100;

    var width = width || 500;
    var height = height || 500;
    var xdomain = xdomain || [-1000000, 1000000];
    var ydomain = ydomain || [1000000, -1000000];
    
    var svg = d3.select(selector).append('svg');
    var canvas = svg.append('g');
    var images = canvas.append('g');
    var tiles = canvas.append('g');
    var rois = canvas.append('g');
    var slot = canvas.append('g');
    var position = canvas.append('g');
    var margin;

    var xscale = d3.scale.linear();
    var ixscale = d3.scale.linear();
    var yscale = d3.scale.linear();
    var iyscale = d3.scale.linear();

    var xaxis = d3.svg.axis();
    var yaxis = d3.svg.axis();

    var fov = [15250, 15250];
    var xjog = 15250;
    var yjog = 15250;
    var shift_scale = 5;
    var alt_scale = 0.2;
    var last = {};

    instance.click_action = 'new_position';
    instance.tiles = [];
    instance._tile_id = 0;
    instance._image_id = 0;
    instance.landmark = '';  // used for set_roi
    //var xscale = d3.scale.linear().domain([0, 8]).range([0, width]);
    //var yscale = d3.scale.linear().domain([0, 8]).range([0, height]);

    instance.resize = function (graph_xdomain, graph_ydomain, graph_width, graph_height, margins) {
        width = graph_width || width;
        height = graph_height || height;
        xdomain = graph_xdomain || xdomain;
        ydomain = graph_ydomain || ydomain;
        if (margins == undefined) {
            margins = {
                top: height * 0.1,
                bottom: height * 0.1,
                left: width * 0.1,
                right: width * 0.1
            };
        };
        margin = margins;
        svg.attr('width', width + margin.left + margin.right)
            .attr('height', height + margin.top + margin.bottom)
            .style('background', 'gray');
        canvas.attr('width', width)
            .attr('height', height)
            .attr('transform', 'translate(' + margin.left + ', ' + margin.top + ')');
        xscale.domain(xdomain).range([0, width]);
        yscale.domain(ydomain).range([0, height]);
        ixscale.domain([0, width]).range(xdomain);
        iyscale.domain([0, height]).range(ydomain);
        xaxis.scale(xscale)
            .ticks(8)
            .tickSize(-height)
            .tickFormat(function (d) { return '' + d / 1000000; });
        yaxis.scale(yscale)
            .ticks(8)
            .tickSize(-width)
            .orient('right')
            .tickFormat(function (d) { return '' + d / 1000000; });
        // remove old axis
        canvas.select('.xaxis').remove();
        // set height by order
        canvas.insert('g', ':first-child')
            .attr('class', 'xaxis axis')
            .attr('transform', 'translate(0, ' + height + ')')
            .call(xaxis);
        canvas.select('.yaxis').remove();
        canvas.insert('g', ':first-child')
            .attr('class', 'yaxis axis')
            .attr('transform', 'translate(' + width + ', 0)')
            .call(yaxis);
        if (last.position != undefined) instance.set_position(last.position[0], last.position[1]);
        if (last.tiles != undefined) instance.set_tiles(last.tiles, true);
        if (last.rois != undefined) instance.set_rois(last.rois);
        if (last.slot != undefined) instance.set_slot(last.slot);
        if (last.images != undefined) instance.set_images(last.images, true);
    };

    function move(x, y, jog) {
        x = ixscale(x - margin.left);
        y = iyscale(y - margin.top);
        if ((jog) && (last.position != undefined)) {
            x -= last.position[0];
            y -= last.position[1];
            if (Math.abs(x) > Math.abs(y)) {
                x = x > 0 ? xjog : -xjog;
                x += last.position[0];
                y = null;
            } else { // y < x
                x = null;
                y = y > 0 ? yjog : -yjog;
                y += last.position[1];
            };
        };
        logger.debug({'x': x, 'y': y});
        $(instance).trigger(instance.click_action, [x, y, instance.landmark]);
    };
 
    svg.on('mousedown', function () {
        // don't click on drags
        if (d3.event.defaultPrevented) return;
        if (d3.event.button != 0) return;
        m = d3.mouse(this);
        // check if in canvas
        if ((m[0] < margin.left) || (m[0] > (margin.left + width)) ||
            (m[1] < margin.top) || (m[1] > (margin.top + height))) return;
        d3.event.preventDefault();
        logger.debug({'click': d3.event, 'm': m});
        if (instance.click_action == 'new_position') {
            move(m[0], m[1], !d3.event.shiftKey);
        } else {
            move(m[0], m[1], false);
        };
    });

    var drag_distance = null;
    var drag_button = null;
    svg.on('mousewheel', function () {
        d3.event.preventDefault();
        if (drag_distance != null) return;
        logger.debug({'mousewheel': d3.event});
        z = 0;
        if (d3.event.wheelDelta > 0) {
            // zoom in
            z = 0.5;
        } else if (d3.event.wheelDelta < 0) {
            // zoom out
            z = 2.0;
        };
        if (z != 0) {
            a = xdomain[0];
            b = xdomain[1];
            c = (a + b) / 2.;
            d = b - a;
            d *= z;
            xdomain = [c - d / 2., c + d / 2.];
            a = ydomain[0];
            b = ydomain[1];
            c = (a + b) / 2.;
            d = b - a;
            d *= z;
            ydomain = [c - d / 2., c + d / 2.];
            instance.resize();
        };
    });

    var drag = d3.behavior.drag()
        //.origin(function(d) { return d; })
        .on("dragstart", dragstarted)
        .on("drag", dragged)
        .on("dragend", dragended);

    svg.call(drag);

    function dragstarted (d) {
        logger.debug({'dragstarted': d3.event});
        if ((d3.event.sourceEvent.which == 1) &&
            (!d3.event.sourceEvent.shiftKey)) return;
        if (d3.event.sourceEvent.which == 3) return;
        drag_button = d3.event.sourceEvent.which;
        drag_distance = [0, 0];
    };


    function pan_center_pixels(x, y, update_images) {
        a = xdomain[0];
        b = xdomain[1];
        c = (a + b) / 2. + ixscale(0) - ixscale(x); 
        d = b - a;
        xdomain = [c - d / 2., c + d / 2.];
        a = ydomain[0];
        b = ydomain[1];
        c = (a + b) / 2. + iyscale(0) - iyscale(y);
        d = b - a;
        ydomain = [c - d / 2., c + d / 2.];
        update_images = (update_images == undefined) ? true: update_images;
        console.log({"update_images": update_images});
        if (update_images) {
            instance.resize();
        } else {
            i = last.images;
            last.images = [];
            instance.resize();
            last.images = i;
        };
    };

    function dragged (d) {
        if (drag_distance == null) return;
        logger.debug({'dragged': d3.event, 'button': drag_button});
        drag_distance[0] += d3.event.dx;
        drag_distance[1] += d3.event.dy;
        // the thresholds here are to throttle writes to the server
        // low values mean more writes, high mean less responsive ui
        if ((Math.abs(drag_distance[0]) > 5) ||
            (Math.abs(drag_distance[1]) > 5)) {
            if (drag_button == 2) {
                pan_center_pixels(drag_distance[0], drag_distance[1], false);
            } else if (drag_button == 1) {
                m = d3.mouse(this);
                move(m[0], m[1], false);
            };
            drag_distance = [0, 0];
        };
    };

    function dragended (d) {
        if (drag_distance == null) return;
        logger.debug({'dragended': d3.event, 'button': drag_button});
        if (drag_button == 2) {
            pan_center_pixels(drag_distance[0], drag_distance[1], true);
        } else if (drag_button == 1) {
            m = d3.mouse(this);
            move(m[0], m[1], false);
        };
        drag_distance = null;
    };


    instance.resize([-1000000, 1000000], [-1000000, 1000000], width, height);

    instance.set_slot = function (d) {
        s = slot.selectAll('rect').data([d, ]);

        s.enter().append('rect')
            .attr('class', 'slot')
            .attr('x', function(d) {
                return xscale(d['x'] - 1000000); })
            .attr('y', function(d) {
                return yscale(d['y'] - 750000); })
            .attr('rx', function(d) {
                return Math.abs(xscale(0) - xscale(500000)); })
            .attr('ry', function(d) {
                return Math.abs(yscale(0) - yscale(500000)); })
            .attr('width', function(d) {
                return Math.abs(xscale(0) - xscale(2000000)); })
            .attr('height', function(d) {
                return Math.abs(yscale(0) - yscale(1500000)); });

        s.attr('x', function(d) {
                return xscale(d['x'] - 1000000); })
            .attr('y', function(d) {
                return yscale(d['y'] - 750000); })
            .attr('rx', function(d) {
                return Math.abs(xscale(0) - xscale(500000)); })
            .attr('ry', function(d) {
                return Math.abs(yscale(0) - yscale(500000)); })
            .attr('width', function(d) {
                return Math.abs(xscale(0) - xscale(2000000)); })
            .attr('height', function(d) {
                return Math.abs(yscale(0) - yscale(1500000)); });

        s.exit().remove();
        last.slot = d;
    };

    instance.set_rois = function (d) {
        /*
        Update the controls with the current rois
        d should be a list of lists of [left, top, width, height]
        */
        // TODO draw invalid rois?
        s = rois.selectAll('rect').data(d);
        // enter
        s.enter().append('rect')
            .attr('class', 'roi')
            .attr('x', function (d) {
                return xscale(ROIResolver.resolve('left', d)); })
            .attr('y', function (d) {
                return yscale(ROIResolver.resolve('top', d)); })
            .attr('width', function (d) {
                return Math.abs(xscale(0) - xscale(ROIResolver.resolve('width', d))); })
            .attr('height', function (d) {
                return Math.abs(yscale(0) - yscale(ROIResolver.resolve('height', d))); });

        // update
        s.attr('x', function (d) {
                return xscale(ROIResolver.resolve('left', d)); })
            .attr('y', function (d) {
                return yscale(ROIResolver.resolve('top', d)); })
            .attr('width', function (d) {
                return Math.abs(xscale(0) - xscale(ROIResolver.resolve('width', d))); })
            .attr('height', function (d) {
                return Math.abs(yscale(0) - yscale(ROIResolver.resolve('height', d))); });

        // remove
        s.exit().remove();
        last.rois = d;
    };

    instance.set_position = function (x, y) {
        /*
        Update the control with the current position
        */
        d = [[x, y]];
        s = position.selectAll('circle').data(d);

        // enter
        s.enter().append('circle')
            .attr('class', 'position')
            .attr('cx', function(d) { return xscale(d[0]); })
            .attr('cy', function(d) { return yscale(d[1]); })
            .attr('r', 4);

        // update
        s.attr('cx', function(d) { return xscale(d[0]); })
            .attr('cy', function(d) { return yscale(d[1]); });

        // remove
        s.exit().remove();

        s = position.selectAll('rect').data(d);

        s.enter().append('rect')
            .attr('class', 'fov')
            .attr('x', function (d) { return xscale(d[0] - fov[0] / 2.); })
            .attr('y', function (d) { return yscale(d[1] - fov[1] / 2.); })
            .attr('width', function (d) { return Math.abs(xscale(0) - xscale(fov[0])); })
            .attr('height', function (d) { return Math.abs(yscale(0) - yscale(fov[1])); });

        s.attr('x', function (d) { return xscale(d[0] - fov[0] / 2.); })
            .attr('y', function (d) { return yscale(d[1] - fov[1] / 2.); })
            .attr('width', function (d) { return Math.abs(xscale(0) - xscale(fov[0])); })
            .attr('height', function (d) { return Math.abs(yscale(0) - yscale(fov[1])); });

        s.exit().remove();

        last.position = [x, y];
    };

    instance.add_tile = function (d) {
        if (d.length == 0) {
            instance.tiles = [];
        } else {
            d['index'] = instance._tile_id;
            instance._tile_id += 1;
            instance.tiles.push(d);
        };
        instance.set_tiles(instance.tiles);
    };

    instance.set_tiles = function (d, update) {
        /*
        Update the control with the current acquired tiles
        d should be a list of 'tiles' made up of
        [x, y, w, h]
        */
        s = tiles.selectAll('rect').data(d, function (d) { return d.index; });
        // enter
        s.enter().append('rect')
            .attr('class', 'tile')
            .attr('x', function (d) { return xscale(d.meta.x - fov[0] / 2.); })
            .attr('y', function (d) { return yscale(d.meta.y - fov[1] / 2.); })
            .attr('stroke', function (d) {
                //if (!d.vetoed.every(function(e) {return e == false})) return 'red';
                if (d.vetoed) return 'red';
                if (d.regrabs) return 'darkorange';
                return 'black';
            })
            .attr('width', function (d) { return Math.abs(xscale(0) - xscale(fov[0])); })
            .attr('height', function (d) { return Math.abs(yscale(0) - yscale(fov[1])); });
        // update
        if (update) {
            s.attr('x', function (d) { return xscale(d.meta.x - fov[0] / 2.); })
                .attr('y', function (d) { return yscale(d.meta.y - fov[1] / 2.); })
                .attr('width', function (d) { return Math.abs(xscale(0) - xscale(fov[0])); })
                .attr('height', function (d) { return Math.abs(yscale(0) - yscale(fov[1])); });
        };
        // remove
        s.exit().remove();
        if (d.length > 0) {
            last_tile = d[d.length - 1];
            logger.debug({'last_tile': last_tile});
            instance.set_position(last_tile.meta.x, last_tile.meta.y);
        };
        last.tiles = d;
    };

    instance.clear_tiles = function () {
        instance.set_tiles([]);
    };

    instance.set_images = function (new_images, update) {
        s = images.selectAll('image').data(
            new_images, function (d) { return d.index; });
        s.enter().append('image')
            .attr('x', function (d) { return xscale(d.x); })
            .attr('y', function (d) { return yscale(d.y); })
            .attr('width', function (d) { return Math.abs(xscale(0) - xscale(d.w)); })
            .attr('height', function (d) { return Math.abs(yscale(0) - yscale(d.h)); })
            .attr('xlink:href', function (d) { return d.src; });
        if (update) {
            s.attr('x', function (d) { return xscale(d.x); })
                .attr('y', function (d) { return yscale(d.y); })
                .attr('width', function (d) { return Math.abs(xscale(0) - xscale(d.w)); })
                .attr('height', function (d) { return Math.abs(yscale(0) - yscale(d.h)); });
                //.attr('xlink:href', function (d) { return d.src; });
        };
        s.exit().remove()
        last.images = new_images;
    };

    instance.set_image = function (img, x, y, w, h) {
        if (x == undefined) x = last.position[0];
        if (y == undefined) y = last.position[1];
        if (w == undefined) w = fov[0];
        if (h == undefined) h = fov[1];
        x = x - w / 2.;
        y = y - h / 2.;
        image = {
            'src': img,
            'x': x,
            'y': y,
            'w': w,
            'h': h,
            'index': instance._image_id,
        };
        instance._image_id += 1;
        if (last.images == undefined) last.images = [];
        last.images.push(image);
        while (last.images.length > instance.n_images) {
            last.images.shift();
        };
        instance.set_images(last.images);
    };

    instance.clear_images = function () {
        images.selectAll('image').remove();
        last.images = [];
    };

    instance.connect = function (socket, actions) {
        /*
        Connect to a rpc web socket of a control node

        - listen for roi changes
        - listen for position changes
        - listen for tile changes
        - setup set_position
        - setup set_roi
        - setup set width/height [need to add to ui]
        */
        if (actions == undefined) {
            actions = ['position', 'tiles', 'rois'];
        };

        if (actions.indexOf('position') != -1) {
            $(instance).on('new_position', function (e, x, y) {
                logger.debug({'move': [x, y]});
                socket.call('move', [x, y]);
            });
            $(socket).on('new_position', function (e, p) {
                logger.debug({'new_position': [e, p]});
                instance.set_position(p.x, p.y);
            });
            socket.call('poll_position');
        };

        if (actions.indexOf('rois') != -1) {
            $(instance).on('set_roi', function (e, x, y, landmark) {
                logger.debug({'set_roi': [landmark, x, y]});
                socket.call('set_roi', [landmark, x, y]);
            });
            
            $(socket).on('config_changed', function (e, cfg) {
                instance.set_rois([cfg.montage.roi,]);
                instance.set_slot(cfg.slot_center);
            });
        };

        if (actions.indexOf('tiles') != -1) {
            socket.signal('new_tile.connect', function (r) {
                logger.debug({'set_tiles': r[0][0]});
                instance.add_tile(r[0][0]);
                //instance.set_tiles(r[0][0]);
            });
            $(socket).on('config_changed', function (e, cfg) {
                fov = cfg.montage.fov;
                xjog = fov[0];
                yjog = fov[1];
                logger.debug({'new fov': fov});
            });
        };

        socket.fetch_config();
    };

    instance.bind_arrow_keys = function () {
        d3.select('body').on('keydown', function () {
            // make sure it's an arrow key
            // 37 = left, 38 = up, 39 = right, 40 = down
            if (document.activeElement.nodeName != 'BODY') return;
            if (last.position != undefined) {
                x = null;
                y = null;
                scale = d3.event.altKey ? alt_scale : 1.0;
                scale *= d3.event.shiftKey ? shift_scale: 1.0;
                switch (d3.event.keyCode) {
                    case 37: // 65: // 37: // left
                        x = -xjog * scale;
                        break;
                    case 39: // 68: // 39: // right
                        x = xjog * scale;
                        break;
                    case 38: // 87: // 38: // up
                        y = -yjog * scale;
                        break;
                    case 40: // 83: // 40: // down
                        y = yjog * scale;
                        break;
                };
                if ((x == null) & (y == null)) return;
                if (y != null) y += last.position[1];
                if (x != null) x += last.position[0];
                d3.event.preventDefault();
                logger.debug({'x': x, 'y': y});
                //$(instance).trigger(instance.click_action, [x, y, instance.landmark]);
                $(instance).trigger('new_position', [x, y, instance.landmark]);
            };
            // modifier keys for larger/smaller moves?
        });
    };

    return instance;
};

