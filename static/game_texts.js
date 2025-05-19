// static/game_texts.js

const GAME_TEXTS = {
    // For successful player actions derived from server game_update
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
    // For client-side feedback when an action is sent to the server
    ACTION_SENT_FEEDBACK: { // Used by 'action_feedback' from server if 'messageKey' matches
        ACTION_QUEUED: [ // Server would send messageKey: "ACTION_QUEUED"
            "Tome confirms: Your will has been noted. Awaiting cosmic alignment...",
            "The Ethereal Plane acknowledges your intent. Processing...",
            "Your command is recorded in the echoes of time.",
            "Patience, wizard. The threads of fate are being woven..."
        ],
        ACTION_FAILED_UNKNOWN_COMMAND: [ // Server would send messageKey: "ACTION_FAILED_UNKNOWN_COMMAND", placeholders: {actionWord: "..."}
            "Tome seems puzzled: Your will \"{actionWord}\" is indecipherable. (Perhaps 'help' will illuminate the path?)",
            "The ancient script offers no translation for \"{actionWord}\". Try 'help'.",
            "Confusion clouds the Tome's pages. The command \"{actionWord}\" is not recognized."
        ],
        // Add more specific failure keys if needed
    },
    // Specific lore/event messages triggered by server (server sends messageKey)
    LORE: {
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
            "The landscape shifts, revealing the western entry to area ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_EAST: [
            "Tome scribbles: You emerge on the eastern edge of a new area ({scene_x},{scene_y}).",
            "To the east, a new horizon: area ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_NORTH: [
            "Tome scribbles: You emerge on the northern edge of a new area ({scene_x},{scene_y}).",
            "Northward you have traveled, to area ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_SOUTH: [
            "Tome scribbles: You emerge on the southern edge of a new area ({scene_x},{scene_y}).",
            "The southern path leads you to area ({scene_x},{scene_y})."
        ],
        VOICE_BOOM_SHOUT: [
            "Tome notes: Your voice booms, costing {manaCost} mana!",
            "The air trembles with your shout, draining {manaCost} mana."
        ],
        LACK_MANA_SHOUT: [
            "Tome warns: You lack the {manaCost} mana to project your voice so powerfully.",
            "A mere whisper escapes; you need {manaCost} mana for such a shout."
        ]
    },
    // Fallbacks for generic messages from server (if server sends a direct message instead of a key)
    // The 'message' placeholder will be filled by the server's direct message.
    GENERIC: {
        LORE: ["{message}"],
        SYSTEM: ["{message}"],
        EVENT_GOOD: ["{message}"],
        EVENT_BAD: ["{message}"]
    }
};

/**
 * Selects a random text string for a given event key and fills placeholders.
 * @param {String} mainKey - The main category in GAME_TEXTS (e.g., 'PLAYER_MOVE', 'LORE', 'ACTION_SENT_FEEDBACK').
 * @param {String} [subKey] - Optional sub-category (e.g., 'POTION_DRINK_SUCCESS' if mainKey is 'LORE').
 * @param {Object} [placeholders] - An object with key-value pairs for placeholder replacement (e.g., {x: 10, y: 5}).
 * @returns {String} The formatted, randomized text string.
 */
function getRandomGameText(mainKey, subKey, placeholders = {}) {
    let textsArray;

    if (mainKey && GAME_TEXTS[mainKey]) {
        if (subKey && typeof GAME_TEXTS[mainKey] === 'object' && GAME_TEXTS[mainKey][subKey] && Array.isArray(GAME_TEXTS[mainKey][subKey])) {
            textsArray = GAME_TEXTS[mainKey][subKey];
        } else if (Array.isArray(GAME_TEXTS[mainKey])) {
            textsArray = GAME_TEXTS[mainKey]; // mainKey itself is the array (e.g., PLAYER_MOVE)
        }
    }

    if (!textsArray) {
        // Fallback if the specific key isn't found, try a generic message within the mainKey category
        if (mainKey && GAME_TEXTS.GENERIC && GAME_TEXTS.GENERIC[mainKey.toUpperCase()]) {
            textsArray = GAME_TEXTS.GENERIC[mainKey.toUpperCase()];
        } else if (placeholders && placeholders.message) { // If a raw message was passed
            return placeholders.message;
        } else {
            console.warn(`No texts found for key: ${mainKey}${subKey ? '.'+subKey : ''}. Using raw input or default error.`);
            return `Missing text for: ${mainKey}${subKey ? '.'+subKey : ''}` + (placeholders.message ? `: ${placeholders.message}` : '');
        }
    }

    if (!textsArray || textsArray.length === 0) {
        console.warn(`Empty text array for key: ${mainKey}${subKey ? '.'+subKey : ''}`);
        return `No text variants for: ${mainKey}${subKey ? '.'+subKey : ''}`;
    }

    const randomIndex = Math.floor(Math.random() * textsArray.length);
    let selectedText = textsArray[randomIndex];

    // Replace placeholders like {x}, {y}, {direction}, {message}
    for (const placeholder in placeholders) {
        selectedText = selectedText.replace(new RegExp(`{${placeholder}}`, 'g'), placeholders[placeholder]);
    }
    return selectedText;
}