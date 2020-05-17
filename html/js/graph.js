var svg = {};

var duration = 600;

var width = 800,
    height = 400,
    radius = Math.min(width,height) / 2;

var pie = d3.layout.pie()
    .sort(null)
    .value(function(d) {
        return d.value;
    });

var arc = d3.svg.arc()
    .outerRadius(radius * 1.0)
    .innerRadius(radius * 0.4);

var outerArc = d3.svg.arc()
    .innerRadius(radius * 0.5)
    .outerRadius(radius * 1);

function buildGraph(name, full) {
    if ( full ) {
        svg[name] = d3.select("#" + name)
            .append("svg").attr("class", "wheel").attr("style", "width:100%;height:100%")
            .append("g")
    } else {
        svg[name] = d3.select("#" + name)
            .append("svg").attr("class", "wheel")
            .append("g")
    }
    //svg[name]
    //svg[name].style.display = "inline";

    svg[name].append("g")
        .attr("class", "slices");
    svg[name].append("g")
        .attr("class", "labels");
    svg[name].append("g")
        .attr("class", "lines");

    svg[name].attr("transform", "translate(" + width / 2 + "," + height / 2 + ")");
}

var key = function(d){ return d.data.label; };

var color = d3.scale.category20()
    .domain(["Assigned", "Complete", "Overdue", "Terminated", "Awaiting Review", "Attached"])
    .range(["#1abc9c", "#27ae60", "#e74c3c", "#f1c40f", "#34495e", "#3498db", "#8e44ad"]);

function randomData (){
    var labels = color.domain();
    return labels.map(function(label){
        return { label: label, value: Math.random() }
    }).filter(function() {
        return Math.random() > .5;
    }).sort(function(a,b) {
        return d3.ascending(a.label, b.label);
    });
}

d3.select(".randomize")
    .on("click", function(){
        var rndm = randomData();
        sDumper(rndm);
        change(randomData());
    });

function mergeWithFirstEqualZero(first, second){
    var secondSet = d3.set(); second.forEach(function(d) { secondSet.add(d.label); });

    var onlyFirst = first
        .filter(function(d){ return !secondSet.has(d.label) })
        .map(function(d) { return {label: d.label, value: 0}; });
    return d3.merge([ second, onlyFirst ])
        .sort(function(a,b) {
            return d3.ascending(a.label, b.label);
        });
}

function change(data, name) {

    var data0 = svg[name].select(".slices").selectAll("path.slice")
        .data().map(function(d) { return d.data });
    if (data0.length == 0) data0 = data;
    var was = mergeWithFirstEqualZero(data, data0);
    var is = mergeWithFirstEqualZero(data0, data);

    /* ------- SLICE ARCS -------*/

    var slice = svg[name].select(".slices").selectAll("path.slice")
        .data(pie(was), key);

    slice.enter()
        .insert("path")
        .attr("class", "slice")
        .style("fill", function(d) { return color(d.data.label); })
        .each(function(d) {
            this._current = d;
        });

    slice = svg[name].select(".slices").selectAll("path.slice")
        .data(pie(is), key);

    slice
        .transition().duration(duration)
        .attrTween("d", function(d) {
            var interpolate = d3.interpolate(this._current, d);
            var _this = this;
            return function(t) {
                _this._current = interpolate(t);
                return arc(_this._current);
            };
        });

    slice = svg[name].select(".slices").selectAll("path.slice")
        .data(pie(data), key);

    slice
        .exit().transition().delay(duration).duration(0)
        .remove();

    /* ------- TEXT LABELS -------*/

    var text = svg[name].select(".labels").selectAll("text")
        .data(pie(was), key);

    text.enter()
        .append("text")
        .attr("dy", ".35em")
        .style("opacity", 0)
        .text(function(d) {
            return d.data.label;
        })
        .each(function(d) {
            this._current = d;
        });

    function midAngle(d){
        return d.startAngle + (d.endAngle - d.startAngle)/2;
    }

    text = svg[name].select(".labels").selectAll("text")
        .data(pie(is), key);

    text.transition().duration(duration)
        .style("opacity", function(d) {
            return d.data.value == 0 ? 0 : 1;
        })
        .attrTween("transform", function(d) {
            var interpolate = d3.interpolate(this._current, d);
            var _this = this;
            return function(t) {
                var d2 = interpolate(t);
                _this._current = d2;
                var pos = outerArc.centroid(d2);
                pos[0] = radius * (midAngle(d2) < Math.PI ? 1 : -1);
                return "translate("+ pos +")";
            };
        })
        .styleTween("text-anchor", function(d){
            var interpolate = d3.interpolate(this._current, d);
            return function(t) {
                var d2 = interpolate(t);
                return midAngle(d2) < Math.PI ? "start":"end";
            };
        });

    text = svg[name].select(".labels").selectAll("text")
        .data(pie(data), key);

    text
        .exit().transition().delay(duration)
        .remove();

    /* ------- SLICE TO TEXT POLYLINES -------*/

    var polyline = svg[name].select(".lines").selectAll("polyline")
        .data(pie(was), key);

    polyline.enter()
        .append("polyline")
        .style("opacity", 0)
        .each(function(d) {
            this._current = d;
        });

    polyline = svg[name].select(".lines").selectAll("polyline")
        .data(pie(is), key);

    polyline.transition().duration(duration)
        .style("opacity", function(d) {
            return d.data.value == 0 ? 0 : 1;
        })
        .attrTween("points", function(d){
            this._current = this._current;
            var interpolate = d3.interpolate(this._current, d);
            var _this = this;
            return function(t) {
                var d2 = interpolate(t);
                _this._current = d2;
                var pos = outerArc.centroid(d2);
                pos[0] = radius * 0.95 * (midAngle(d2) < Math.PI ? 1 : -1);
                return [arc.centroid(d2), outerArc.centroid(d2), pos];
            };
        });

    polyline = svg[name].select(".lines").selectAll("polyline")
        .data(pie(data), key);

    polyline
        .exit().transition().delay(duration)
        .remove();
};
