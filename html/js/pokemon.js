"use strict"; // perl ftw.

const inputFields = [];
const ONE_DAY_IN_SECONDS = 86400;

const lowestStartDate = new Date("07/06/2016").getTime();
const dateRegex = /^(?:0[1-9]|1[0-2])\/(?:0[1-9]|1\d|2\d|3[01])\/20\d{2}$/;

var validDate = false;

const mapping = {
    pokestopsVisited: {
        mult: 50,
        label: "Pokestops"
    },
    pokemonCaught: {
        mult: 250,
        label: "Caught"
    },
    scientist: {
        mult: 500,
        label: "Evolved",
        checkMult: 90
    },
    breeder: {
        mult: 500, // 2k = 200xp, 5k = 500xp, 10k = 1000xp, assume the midpoint
        label: "Eggs",
        checkMult: 25
    },
    battleGirl: {
        mult: 100,
        label: "Fighting"
    },
    idol: {
        mult: 163000, // best=100k, ultra=50k, great=10k, good=3k
        label: "Friends",
        checkMult: 50
    },
    champion: {
        mult: 4000, // tier1=3000, tier2=3500, tier3=4000, tier4=5000
        label: "Raid"
    },
    battleLegend: {
        mult: 10000,
        label: "Tier5Raid",
        checkMult: 50
    },
    // XXX TODO
    giftsSent: {
        mult: 200,
        label: "GiftsSent" // assume 45 gifts sent out of the 90 days it gets to best friend
    }
}

function computeInputFields() {
    $("input").each(function(idx){
        const current = $(this);
        inputFields.push(current.context.id);
    });
}

function setupBindings() {
    $(":text").keyup(function(evt){
        if ( evt.srcElement.id == "startDate" ) {
            if ( validateDate() ) {
                recalculate();
            }
            return;
        }

        if ( isNaN(evt.srcElement.value) ) {
            evt.srcElement.value = "";
        } else {
            recalculate();
        }
    });
    $(":checkbox").change(function(evt) {
        recalculate();
    });
}

function getCurrentValues() {
    const values = {};
    for ( const inputField of inputFields ) {
        const inputElem = $("#" + inputField);
        if ( inputField == "startDate" ) {
            values[inputField] = inputElem.val();
        } else if ( inputElem.prop('type') == 'text' ) {
            values[inputField] = +inputElem.val();
        } else if ( inputElem.prop('type') == 'checkbox') {
            values[inputField] = inputElem.prop('checked');
        }
    }
    return values;
}

function calculateDays(values) {
    const today = new Date().getTime();
    const start = new Date(values.startDate).getTime();
    values.daysPlaying = Math.floor(( (today - start) / ONE_DAY_IN_SECONDS ) / 1000);
    $("#daysPlaying").html(values.daysPlaying);
    $("#xpPerDay").html(Math.floor(values.totalXP / values.daysPlaying));
    // TODO average raids per day (take into account the first day raids were possible)
    // TODO average legendary raids per day (go fest 2017 - July 22)
}

function computePercentage(label, name, values, mult, res, checkMult) {
    if ( name in values && values[name] ) {
        var exp = +( values[name] * mult );
        if ( values[name + "Check"] ) {
            exp = exp + ( exp * ( checkMult / 100 ) );
        }
        const value = exp / values.totalXP;
        res.push( { label, value } );
        return exp;
    } else {
        return 0;
    }
}

function calculateTableEntries(values) {
    if ( values.battleLegend && values.champion && values.daysPlaying ) {
        $("#raidsPerDay").html(( values.battleLegend + values.champion ) / values.daysPlaying);
    }
}

function recalculate() {
    var values = getCurrentValues();
    console.log(values);

    if ( values.totalXP && values.pokemonCaught && values.pokestopsVisited && validDate ) {

        calculateDays(values);

        var res = [];

        var accountedFor = 0;
        for ( const name of Object.keys(mapping) ) {
            accountedFor += computePercentage(mapping[name].label, name, values, mapping[name].mult, res, mapping[name].checkMult);
        }
        const unaccountedFor = (values.totalXP - accountedFor) / values.totalXP;
        res.push( { label: "Unaccounted", value: unaccountedFor });

        calculateTableEntries(values);

        change(res, "myGraph");

        $("#dataTable").css("display", "block");
    } else {
        console.log("totalXP = " + values.totalXP);
        console.log("pokemonCaught = " + values.pokemonCaught);
        console.log("pokestopsVisited = " + values.pokestopsVisited);
        console.log("startDate = " + values.startDate + ", validDate=" + validDate);
    }
}

function validateDate() {
    const startDateElem = $("#startDate");
    const validDateStr = startDateElem.val();

    if ( ! dateRegex.test(validDateStr) ) {
        startDateElem.css("background-color", "pink");
        validDate = false;
        return;
    }

    if ( new Date(validDateStr).getTime() > lowestStartDate ) {
        startDateElem.css("background-color", "lightgreen");
        validDate = true;
        return true;
    }
}

$(document).ready(function(){
    computeInputFields();
    setupBindings();
    validateDate();

    buildGraph("myGraph", true);
});

function setRyan() {
    $("#totalXP").val(72726389);
    $("#pokemonCaught").val(85874);
    $("#pokestopsVisited").val(51401);
    $("#startDate").val("07/10/2016");
    $("#scientist").val(9985);
    $("#breeder").val(2342);
    $("#battleGirl").val(7826);
    $("#idol").val(76);
    $("#champion").val(277);
    $("#battleLegend").val(494);

    $("#battleLegendCheck").prop("checked", true);
    $("#idolCheck").prop("checked", true);
    $("#scientistCheck").prop("checked", true);

    validateDate();

    recalculate();
}
