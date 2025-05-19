// static/game_texts.js

const GAME_TEXTS = {
    PLAYER_MOVE: [ 
        "Tome traces your path: You move to ({x}, {y}), now facing {direction}.",
        "The weave shifts as you step to ({x}, {y}), oriented {direction}.",
        "Your journey continues to ({x}, {y}), gaze fixed {direction}.",
        "With a soft rustle of reality, you find yourself at ({x}, {y}), looking {direction}."
    ],
    PLAYER_TURN: [ 
        "Tome observes: You turn to face {direction} at ({x},{y}).",
        "Your gaze shifts {direction} from your position at ({x},{y}).",
        "Oriented {direction}, you survey your surroundings from ({x},{y})."
    ],
    ACTION_SENT_FEEDBACK: { 
        ACTION_QUEUED: [
            "Tome confirms: Your will has been noted. Awaiting cosmic alignment...",
            "The Ethereal Plane acknowledges your intent. Processing...",
            "Your command is recorded in the echoes of time.",
            "Patience, wizard. The threads of fate are being woven..."
        ],
        ACTION_FAILED_UNKNOWN_COMMAND: [
            "Tome seems puzzled: Your will \"{actionWord}\" is indecipherable. (Perhaps 'help' will illuminate the path?)",
            "The ancient script offers no translation for \"{actionWord}\". Try 'help'.",
            "Confusion clouds the Tome's pages. The command \"{actionWord}\" is not recognized."
        ],
        SPELL_FIZZLE_NO_MANA: [
            "Your spell fizzles, your mana reserves too low for such an incantation.",
            "A pathetic spark is all you can muster; more mana is required."
        ],
        CANNOT_DRINK_NOTHING: [
            "You try to drink, but have nothing suitable in hand.",
            "Thirst quencher needed, wizard, but what?"
        ]
    },
    LORE: { 
        CONNECTION_ESTABLISHED: [
            "Tome hums: Connection to the Ethereal Plane established.",
            "The ethereal link solidifies. You are connected.",
            "A bridge forms across the aether. Connection successful."
        ],
        WELCOME: ["Tome: You have materialized. Your essence is bound to ID: {playerId}. {fallback} {observer}"],
        WELCOME_INITIAL: ["Tome unfurls its pages: Welcome, Wizard. The Ethereal Waves await your command."],
        INITIAL_RAIN: ["Tome notes: A chilling rain falls from the slate-grey sky."],
        POTION_DRINK_SUCCESS: [
            "Tome notes: You drink a potion, feeling invigorated!",
            "A warmth spreads through you as the potion takes effect.",
            "The vial empties, and a surge of energy courses through your veins."
        ],
        POTION_DRINK_FAIL_EMPTY: [
            "Tome sighs: Your satchel is empty of potions.",
            "You reach for a potion, but find only air.",
            "Alas, no potions remain."
        ],
        SCENE_TRANSITION_WEST: [
            "Tome scribbles: You emerge on the western edge of a new area ({scene_x},{scene_y}).",
            "The landscape shifts, revealing the western entry to area ({scene_x},{scene_y}).",
            "Westward, the world changes. You are now in ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_EAST: [
            "Tome scribbles: You emerge on the eastern edge of a new area ({scene_x},{scene_y}).",
            "To the east, a new horizon: area ({scene_x},{scene_y}).",
            "Eastward, the path unfolds into ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_NORTH: [
            "Tome scribbles: You emerge on the northern edge of a new area ({scene_x},{scene_y}).",
            "Northward you have traveled, to area ({scene_x},{scene_y}).",
            "The northern winds carry you to ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_SOUTH: [
            "Tome scribbles: You emerge on the southern edge of a new area ({scene_x},{scene_y}).",
            "The southern path leads you to area ({scene_x},{scene_y}).",
            "South you venture, into the lands of ({scene_x},{scene_y})."
        ],
        VOICE_BOOM_SHOUT: [
            "Tome notes: Your voice booms, costing {manaCost} mana!",
            "The air trembles with your shout, draining {manaCost} mana.",
            "A thundering call echoes, consuming {manaCost} of your essence."
        ],
        LACK_MANA_SHOUT: [ 
            "Tome warns: You lack the {manaCost} mana to project your voice so powerfully.",
            "A mere whisper escapes; you need {manaCost} mana for such a shout.",
            "Your throat strains, but the arcane energies are insufficient. ({manaCost} mana required)."
        ],
        PLAYER_ARRIVES: ["Tome notes: {playerName} arrives in this area."],
        PLAYER_DEPARTS: ["Tome records: {playerName} has departed this area."],
        DISCONNECTED: ["Tome wails: Disconnected! Reason: {reason}. The weave unravels!"],
        CORRUPT_MANIFESTATION_SERVER: ["Tome warns: Corrupted manifestation data from the server."],
        MANIFESTATION_FAILED_NO_PLAYER_DATA: ["Tome warns: Manifestation failed (missing player data)."],
        FONT_SORCERY_FAILED: ["Tome sighs: Font sorcery failed. Visuals may be askew."],
        CENTERING_ERROR: ["Tome struggles: The world's perspective is lost! (Centering Error)"],
        FONT_AND_DATA_ERROR: ["Tome wails: The world's very fabric is unstable! (Font & Data Error)"],
        CHAT_SAY: ["[ {senderName} says ]: "], 
        CHAT_SHOUT: ["[ SHOUT from {senderName} at {sceneCoords} ]: "],
        ACTION_BLOCKED_WALL: [
            "Tome groans: You run face-first into a solid wall!",
            "The way is blocked by an unyielding stone barrier.",
            "Oof! That wall wasn't there a moment ago... or was it?"
        ],
        BUILD_FAIL_OUT_OF_BOUNDS: [
            "Tome advises: You cannot build beyond the known world.",
            "The aether resists your construction at these coordinates."
        ],
        BUILD_FAIL_OBSTRUCTED: [
            "Tome shakes its pages: You cannot build there, something is in the way.",
            "The space is already occupied. Choose another location."
        ],
        BUILD_FAIL_NO_MATERIALS: [
            "Tome sighs: You lack the stone and mortar (wall items) to construct this.",
            "Your satchel is empty of building supplies."
        ],
        BUILD_SUCCESS: [
            "Tome records: With effort, you erect a sturdy wall. ({walls} wall items remaining)",
            "A new barrier rises from the ground at your command! ({walls} left)"
        ],
        DESTROY_FAIL_OUT_OF_BOUNDS: [
            "Tome queries: Destroy what? There is nothing but void there.",
            "You reach into the unknown, but find no wall to dismantle."
        ],
        DESTROY_FAIL_NO_WALL: [
            "Tome seems confused: There is no wall there to destroy.",
            "Your efforts are wasted on empty space."
        ],
        DESTROY_FAIL_NO_MANA: [
            "Tome warns: You lack the {manaCost} mana to deconstruct this barrier.",
            "Your will is strong, but your essence is weak. ({manaCost} mana needed)"
        ],
        DESTROY_SUCCESS: [
            "Tome exclaims: The wall crumbles to dust! You reclaim its essence. ({walls} wall items, {manaCost} mana spent)",
            "With a surge of power, the barrier is unmade. ({walls} items, {manaCost} mana)"
        ],
        BECAME_WET_WATER: [
            "Tome ripples: You step into the water, a chilling splash against your robes!",
            "A shiver runs down your spine as you tread through the water.",
            "The water soaks your boots and hem."
        ],
        BECAME_WET_RAIN: [
            "Tome dampens: The persistent rain has soaked you to the bone.",
            "You feel the cold seep in as the rain continues its downpour.",
            "Drenched by the rain, you long for shelter."
        ],
        BECAME_DRY: [
            "Tome feels lighter: You finally feel dry again.",
            "The moisture evaporates from your robes, a welcome relief.",
            "Warmth returns as the dampness leaves you."
        ],
        // NPC Related Lore
        PIXIE_MOVED_AWAY: [
            "Tome observes: {pixieName} flits out of your path with a faint chime.",
            "The air shimmers as {pixieName} dodges your approach.",
            "{pixieName} zips aside, its wings a blur."
        ],
        PIXIE_BLOCKED_PATH: [
            "Tome notes: {pixieName} hovers defiantly, somehow blocking your way.",
            "Despite its size, {pixieName} holds its ground, and you cannot pass."
        ],
        PIXIE_MANA_BOOST: [
            "Tome glows faintly: Nearby pixies hum, and you feel your mana replenish by {amount}!",
            "A spark of aether from a pixie invigorates you, restoring {amount} mana.",
            "The pixies' presence seems to quicken your mana regeneration by {amount}."
        ],
        SEES_PIXIE_NEARBY: [ // For the 'look' command
            "Tome notes: A tiny, shimmering Mana Pixie ({pixieName}) darts nearby.",
            "You catch a glimpse of {pixieName}, a Mana Pixie, flitting through the air.",
            "The air around {pixieName}, a Mana Pixie, seems to crackle with faint energy."
        ],
        LOOK_DIRECTION_EMPTY: [
            "Tome shows: You peer {direction}, but see nothing of particular interest.",
            "Gazing {direction}, the area seems quiet.",
            "The way {direction} appears clear."
        ],
        LOOK_AROUND_EMPTY: [
            "Tome reflects: You survey your immediate surroundings. Nothing seems out of the ordinary.",
            "A quick scan reveals no immediate points of interest."
        ]
    },
    GENERIC: { 
        LORE: ["{message}"], 
        SYSTEM: ["{message}"], 
        EVENT_GOOD: ["{message}"], 
        EVENT_BAD: ["{message}"]
    }
};

function getRandomGameText(mainKey, subKey, placeholders = {}) {
    let textsArray;
    let actualKeyForLog = mainKey + (subKey ? "." + subKey : "");

    if (mainKey && GAME_TEXTS[mainKey]) {
        if (subKey && typeof GAME_TEXTS[mainKey] === 'object' && GAME_TEXTS[mainKey][subKey] && Array.isArray(GAME_TEXTS[mainKey][subKey])) {
            textsArray = GAME_TEXTS[mainKey][subKey];
        } else if (Array.isArray(GAME_TEXTS[mainKey])) { 
            textsArray = GAME_TEXTS[mainKey];
        }
    }

    if (!textsArray) {
        if (mainKey && GAME_TEXTS.GENERIC && GAME_TEXTS.GENERIC[mainKey.toUpperCase()] && Array.isArray(GAME_TEXTS.GENERIC[mainKey.toUpperCase()])) {
            textsArray = GAME_TEXTS.GENERIC[mainKey.toUpperCase()];
            if (!(placeholders && typeof placeholders.message === 'string' && placeholders.message.trim() !== "")) {
                console.warn(`Generic key ${mainKey.toUpperCase()} used, but no valid 'message' in placeholders:`, placeholders);
                return `Text error for generic type ${mainKey.toUpperCase()} (message content missing/empty)`;
            }
        } 
        else if (placeholders && typeof placeholders.message === 'string' && placeholders.message.trim() !== "") {
            return placeholders.message; 
        } 
        else {
            console.warn(`No texts found for key: ${actualKeyForLog}. Placeholders:`, placeholders);
            return `Missing text definition or content for: ${actualKeyForLog}`;
        }
    }
    
    if (!textsArray || textsArray.length === 0) { 
        console.warn(`Empty text array for key: ${actualKeyForLog}`);
        return `No text variants for: ${actualKeyForLog}`;
    }

    const randomIndex = Math.floor(Math.random() * textsArray.length);
    let selectedText = textsArray[randomIndex];

    for (const placeholder in placeholders) {
        if (placeholders.hasOwnProperty(placeholder) && typeof placeholders[placeholder] !== 'undefined') {
             selectedText = selectedText.replace(new RegExp(`{${placeholder}}`, 'g'), placeholders[placeholder]);
        }
    }
    
    if (selectedText.includes("{") && selectedText.includes("}")) { 
        selectedText = selectedText.replace(/{[a-zA-Z0-9_]+}/g, (match) => {
            if (match === "{message}" && textsArray === GAME_TEXTS.GENERIC[mainKey.toUpperCase()]) {
                return ""; 
            }
            return ""; 
        }).trim();
    }
    
    return selectedText;
}