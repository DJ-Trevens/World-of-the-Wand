// static/game_texts.js

const GAME_TEXTS = {
    PLAYER_MOVE: [ // Client-side interpretation of server state change
        "Tome traces your path: You move to ({x}, {y}), now facing {direction}.",
        "The weave shifts as you step to ({x}, {y}), oriented {direction}.",
        "Your journey continues to ({x}, {y}), gaze fixed {direction}.",
        "With a soft rustle of reality, you find yourself at ({x}, {y}), looking {direction}."
    ],
    PLAYER_TURN: [ // Client-side interpretation of server state change
        "Tome observes: You turn to face {direction} at ({x},{y}).",
        "Your gaze shifts {direction} from your position at ({x},{y}).",
        "Oriented {direction}, you survey your surroundings from ({x},{y})."
    ],
    ACTION_SENT_FEEDBACK: { // For 'action_feedback' event from server
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
        // Example for other action feedbacks (server would send these keys)
        SPELL_FIZZLE_NO_MANA: [
            "Your spell fizzles, your mana reserves too low for such an incantation.",
            "A pathetic spark is all you can muster; more mana is required."
        ],
        CANNOT_DRINK_NOTHING: [
            "You try to drink, but have nothing suitable in hand.",
            "Thirst quencher needed, wizard, but what?"
        ]
    },
    LORE: { // For 'lore_message' event from server (server sends the key)
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
        LACK_MANA_SHOUT: [ // Corrected key name
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
        CHAT_SAY: ["[ {senderName} says ]: "], // These are prefixes, message is appended
        CHAT_SHOUT: ["[ SHOUT from {senderName} at {sceneCoords} ]: "]
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
    let actualKeyForLog = mainKey + (subKey ? "." + subKey : ""); // For logging

    if (mainKey && GAME_TEXTS[mainKey]) {
        if (subKey && typeof GAME_TEXTS[mainKey] === 'object' && GAME_TEXTS[mainKey][subKey] && Array.isArray(GAME_TEXTS[mainKey][subKey])) {
            textsArray = GAME_TEXTS[mainKey][subKey];
        } else if (Array.isArray(GAME_TEXTS[mainKey])) { // If mainKey itself points to an array (e.g., PLAYER_MOVE)
            textsArray = GAME_TEXTS[mainKey];
        }
    }

    if (!textsArray) {
        // Fallback 1: Try GENERIC based on mainKey (if server sends a generic type as mainKey)
        if (mainKey && GAME_TEXTS.GENERIC && GAME_TEXTS.GENERIC[mainKey.toUpperCase()] && Array.isArray(GAME_TEXTS.GENERIC[mainKey.toUpperCase()])) {
            textsArray = GAME_TEXTS.GENERIC[mainKey.toUpperCase()];
            if (!(placeholders && typeof placeholders.message === 'string' && placeholders.message.trim() !== "")) {
                console.warn(`Generic key ${mainKey.toUpperCase()} used, but no valid 'message' in placeholders:`, placeholders);
                return `Text error for generic type ${mainKey.toUpperCase()} (message content missing/empty)`;
            }
        } 
        // Fallback 2: If a raw message was passed in placeholders and no key matched
        else if (placeholders && typeof placeholders.message === 'string' && placeholders.message.trim() !== "") {
            return placeholders.message; 
        } 
        // Fallback 3: No matching key and no usable raw message
        else {
            console.warn(`No texts found for key: ${actualKeyForLog}. Placeholders:`, placeholders);
            return `Missing text definition or content for: ${actualKeyForLog}`;
        }
    }
    
    if (!textsArray || textsArray.length === 0) { // Should ideally be caught by above, but as a safeguard
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
    
    // Clean up any remaining unfilled placeholders like {some_unfilled_placeholder}
    // but be careful not to remove if the template itself IS just "{message}" and it was filled.
    if (selectedText.includes("{") && selectedText.includes("}")) { // Only run regex if placeholders might exist
        selectedText = selectedText.replace(/{[a-zA-Z0-9_]+}/g, (match) => {
            // If the entire string was just "{message}" and it was a GENERIC fallback, 
            // it means placeholders.message was already used. If it's some other placeholder,
            // it means it wasn't supplied, so remove it or indicate it's missing.
            if (match === "{message}" && textsArray === GAME_TEXTS.GENERIC[mainKey.toUpperCase()]) {
                return ""; // Already handled by the template
            }
            // For other unfilled placeholders, you might want to indicate they were missing
            // console.warn(`Unfilled placeholder: ${match} in text for ${actualKeyForLog}`);
            return ""; // Or return match to show it like {unfilled_placeholder}
        }).trim();
    }
    
    return selectedText;
}